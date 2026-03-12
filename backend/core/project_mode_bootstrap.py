# backend/core/project_mode_bootstrap.py
# 功能: 为项目补齐运行时 Agent 角色实例，统一复用系统模板并按 locale fallback 自动引导
# 主要函数: ensure_project_agent_modes
# 数据结构: AgentMode / Project

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.localization import DEFAULT_LOCALE, locale_fallback_chain, normalize_locale
from core.models import AgentMode, Project, generate_uuid


def _generate_internal_mode_name() -> str:
    return f"mode_{generate_uuid().replace('-', '')[:12]}"


def _resolve_template_modes(db: Session, locale: str) -> list[AgentMode]:
    seen_locales: set[str] = set()
    for candidate in locale_fallback_chain(locale):
        normalized_candidate = normalize_locale(candidate)
        if normalized_candidate in seen_locales:
            continue
        seen_locales.add(normalized_candidate)
        templates = db.query(AgentMode).filter(
            AgentMode.project_id.is_(None),
            AgentMode.is_template.is_(True),
            AgentMode.locale == normalized_candidate,
        ).order_by(AgentMode.sort_order, AgentMode.created_at).all()
        if templates:
            return templates

    return db.query(AgentMode).filter(
        AgentMode.project_id.is_(None),
        AgentMode.is_template.is_(True),
    ).order_by(AgentMode.sort_order, AgentMode.created_at).all()


def ensure_project_agent_modes(
    db: Session,
    project_id: str,
    locale: Optional[str] = None,
) -> list[AgentMode]:
    """确保项目拥有可运行的 Agent 角色；若缺失则按 locale 从系统模板克隆。"""
    existing = db.query(AgentMode).filter(
        AgentMode.project_id == project_id,
        AgentMode.is_template.is_(False),
    ).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    if existing:
        return existing

    project_locale = normalize_locale(locale)
    if locale is None:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return []
        project_locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))

    templates = _resolve_template_modes(db, project_locale)
    if not templates:
        return []

    created: list[AgentMode] = []
    for index, template in enumerate(templates):
        cloned = AgentMode(
            id=generate_uuid(),
            project_id=project_id,
            name=_generate_internal_mode_name(),
            stable_key=getattr(template, "stable_key", "") or template.name or template.display_name,
            locale=normalize_locale(getattr(template, "locale", project_locale)),
            display_name=template.display_name or template.name,
            description=template.description or "",
            system_prompt=template.system_prompt or "",
            icon=template.icon or "🤖",
            is_system=False,
            is_template=False,
            sort_order=index,
        )
        db.add(cloned)
        created.append(cloned)

    db.flush()
    return created
