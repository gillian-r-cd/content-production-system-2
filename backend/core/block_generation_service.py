# backend/core/block_generation_service.py
# 功能: 统一内容块生成与依赖解析底层服务，供块 API 和项目级调度器复用
# 主要函数: get_ready_block_ids, generate_block_content_sync
# 数据结构: ContentBlock / Project / GenerationLog

"""
内容块生成服务

目标：
- 收敛 ready 判定逻辑
- 收敛依赖解析和非流式生成逻辑
- 让项目级调度器直接复用正式 service，而不是调 HTTP 或复制逻辑
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.llm import ainvoke_with_retry, get_chat_model, parse_llm_error
from core.llm_compat import normalize_content, resolve_model
from core.dependency_regeneration_service import finalize_block_content_change
from core.models import ContentBlock, GenerationLog, Project, generate_uuid
from core.pre_question_utils import iter_answered_pre_question_items, list_missing_required_pre_questions
from core.prompt_engine import GoldenContext
from core.locale_text import markdown_instructions, rt
from core.localization import DEFAULT_LOCALE, normalize_locale


def update_parent_status(parent_id: str, db: Session):
    """根据子级状态自动更新父级，并递归向上同步。"""
    parent = db.query(ContentBlock).filter(
        ContentBlock.id == parent_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if not parent:
        return

    children = db.query(ContentBlock).filter(
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    if not children:
        return

    all_completed = all(child.status == "completed" for child in children)
    any_in_progress = any(child.status == "in_progress" for child in children)
    if all_completed:
        parent.status = "completed"
    elif any_in_progress:
        parent.status = "in_progress"
    else:
        completed_count = sum(1 for child in children if child.status == "completed")
        parent.status = "in_progress" if completed_count > 0 else "pending"

    db.commit()
    if parent.parent_id:
        update_parent_status(parent.parent_id, db)


def resolve_dependencies(
    block: ContentBlock,
    db: Session,
    *,
    locale: str = DEFAULT_LOCALE,
) -> tuple[list[ContentBlock], str, Optional[str]]:
    """
    智能解析依赖关系并修复失效 depends_on。
    返回：(resolved_deps, dependency_content, error_msg)
    """
    if not block.depends_on:
        return [], "", None

    active_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    active_by_id = {item.id: item for item in active_blocks}
    active_by_name = {item.name: item for item in active_blocks if item.id != block.id}

    resolved_deps: list[ContentBlock] = []
    updated_depends_on: list[str] = []
    needs_update = False

    for dep_id in block.depends_on:
        dep_block = active_by_id.get(dep_id)
        if dep_block:
            resolved_deps.append(dep_block)
            updated_depends_on.append(dep_id)
            continue

        old_block = db.query(ContentBlock).filter(ContentBlock.id == dep_id).first()
        dep_name = old_block.name if old_block else dep_id
        replacement = active_by_name.get(dep_name)
        if replacement:
            resolved_deps.append(replacement)
            updated_depends_on.append(replacement.id)
            needs_update = True
        else:
            needs_update = True

    if needs_update:
        block.depends_on = updated_depends_on
        db.flush()

    not_ready = [
        dep for dep in resolved_deps
        if (
            not dep.content
            or not dep.content.strip()
            or dep.status != "completed"
            or bool(getattr(dep, "needs_regeneration", False))
        )
    ]
    if not_ready:
        return resolved_deps, "", rt(
            locale,
            "block.dependencies_not_ready",
            missing_labels="、".join(dep.name for dep in not_ready),
        )

    dependency_content = "\n\n".join(
        f"## {dep.name}\n{dep.content}"
        for dep in resolved_deps
        if dep.content
    )
    return resolved_deps, dependency_content, None


def build_generation_system_prompt(
    *,
    block: ContentBlock,
    project: Project,
    dependency_content: str,
    extra_instruction: str = "",
) -> str:
    """构建内容块生成 prompt。"""
    locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))
    creator_profile_text = ""
    if project.creator_profile:
        creator_profile_text = project.creator_profile.to_prompt_context(locale=locale)

    gc = GoldenContext(creator_profile=creator_profile_text, locale=locale)

    pre_answers_text = ""
    answers = [
        f"- {item['question']}: {answer}"
        for item, answer in iter_answered_pre_question_items(
            block.pre_questions or [],
            block.pre_answers or {},
        )
    ]
    if answers:
        pre_answers_text = rt(locale, "block.pre_answers_header", answers="\n".join(answers))

    ai_prompt = block.ai_prompt or rt(locale, "fallback.generate_content")
    format_instructions = markdown_instructions(locale)
    has_placeholders = "{creator_profile}" in ai_prompt or "{dependencies}" in ai_prompt
    if has_placeholders:
        system_prompt = ai_prompt
        system_prompt = system_prompt.replace("{creator_profile}", creator_profile_text or rt(locale, "fallback.no_creator_profile"))
        system_prompt = system_prompt.replace("{dependencies}", dependency_content or rt(locale, "fallback.no_dependencies"))
        system_prompt += pre_answers_text
        if extra_instruction.strip():
            system_prompt += rt(locale, "block.extra_instruction_header", instruction=extra_instruction)
        system_prompt += rt(locale, "block.markdown_tail", instructions=format_instructions)
        return system_prompt

    extra_instruction_text = ""
    if extra_instruction.strip():
        extra_instruction_text = rt(locale, "block.extra_instruction_header", instruction=extra_instruction)

    return f"""{gc.to_prompt()}

---

{rt(locale, "block.task_header")}
{ai_prompt}
{pre_answers_text}
{extra_instruction_text}

{f'---{chr(10)}{rt(locale, "block.reference_header")}{chr(10)}{dependency_content}' if dependency_content else ''}

---
{format_instructions}
"""


def list_ready_block_ids(
    *,
    project_id: str,
    db: Session,
    mode: str,
    exclude_ids: Optional[set[str]] = None,
) -> list[str]:
    """
    统一 ready 判定。

    mode:
    - auto_trigger: 仅扫描 auto_generate=True 的 ready 块（含首次生成与依赖失效后的重生成）
    - start_all_ready: 忽略 auto_generate，扫描所有 ready 块（含手动批量重生成）
    """
    exclude_ids = exclude_ids or set()
    all_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    blocks_by_id = {block.id: block for block in all_blocks}

    eligible_ids: list[str] = []
    for block in all_blocks:
        if block.id in exclude_ids:
            continue
        if block.block_type != "field":
            continue
        if mode == "auto_trigger" and not getattr(block, "auto_generate", False):
            continue
        has_content = bool(block.content and block.content.strip())
        is_initial_candidate = block.status in ("pending", "failed") and not has_content
        is_regeneration_candidate = bool(getattr(block, "needs_regeneration", False))
        if not is_initial_candidate and not is_regeneration_candidate:
            continue

        deps = block.depends_on or []
        if deps:
            all_deps_ready = True
            for dep_id in deps:
                dep = blocks_by_id.get(dep_id)
                if (
                    not dep
                    or not dep.content
                    or not dep.content.strip()
                    or dep.status != "completed"
                    or bool(getattr(dep, "needs_regeneration", False))
                ):
                    all_deps_ready = False
                    break
            if not all_deps_ready:
                continue

        if list_missing_required_pre_questions(block.pre_questions or [], block.pre_answers or {}):
            continue

        eligible_ids.append(block.id)

    return eligible_ids


def ensure_required_pre_questions_answered(block: ContentBlock, *, locale: str = DEFAULT_LOCALE) -> None:
    missing_items = list_missing_required_pre_questions(
        block.pre_questions or [],
        block.pre_answers or {},
    )
    if missing_items:
        delimiter = "、" if normalize_locale(locale) == "ja-JP" else "、"
        missing_labels = delimiter.join(item["question"] for item in missing_items)
        raise HTTPException(
            status_code=400,
            detail=rt(locale, "pre_questions.missing_required", missing_labels=missing_labels),
        )


async def generate_block_content_sync(
    *,
    block_id: str,
    db: Session,
    extra_instruction: str = "",
    config=None,
) -> dict:
    """非流式生成单个内容块，供项目级调度器和普通生成接口复用。"""
    from core.config import validate_llm_config
    from langchain_core.messages import HumanMessage, SystemMessage

    config_error = validate_llm_config()
    if config_error:
        raise HTTPException(status_code=422, detail=config_error)

    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")

    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))

    ensure_required_pre_questions_answered(block, locale=locale)

    _, dependency_content, dep_error = resolve_dependencies(block, db, locale=locale)
    if dep_error:
        raise HTTPException(status_code=400, detail=dep_error)

    system_prompt = build_generation_system_prompt(
        block=block,
        project=project,
        dependency_content=dependency_content,
        extra_instruction=extra_instruction,
    )

    effective_model = resolve_model(model_override=getattr(block, "model_override", None))
    chat_model = get_chat_model(model=effective_model)

    from core.version_service import save_content_version

    was_stale = bool(getattr(block, "needs_regeneration", False))
    save_content_version(db, block.id, block.content, "ai_regenerate", "重新生成前的版本")
    block.status = "in_progress"
    block.needs_regeneration = False
    db.commit()

    try:
        invoke_kwargs = {"config": config} if config is not None else {}
        response = await ainvoke_with_retry(chat_model, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=rt(locale, "block.generate.human", name=block.name)),
        ], **invoke_kwargs)

        generated_content = normalize_content(response.content)
        block.content = generated_content
        block.status = "completed" if not block.need_review else "in_progress"
        finalize_block_content_change(block=block, db=db)

        usage = getattr(response, "usage_metadata", {}) or {}
        db.add(GenerationLog(
            id=generate_uuid(),
            project_id=block.project_id,
            field_id=block.id,
            phase=block.parent_id or "content_block",
            operation=f"block_generate_{block.name}",
            model=effective_model,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            duration_ms=0,
            prompt_input=system_prompt,
            prompt_output=generated_content,
            cost=GenerationLog.calculate_cost(
                effective_model,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            ),
            status="success",
        ))
        db.commit()

        if block.parent_id:
            update_parent_status(block.parent_id, db)

        return {
            "block_id": block.id,
            "content": generated_content,
            "status": block.status,
            "tokens_in": usage.get("input_tokens", 0),
            "tokens_out": usage.get("output_tokens", 0),
            "cost": 0.0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        block.status = "failed"
        block.needs_regeneration = was_stale
        db.commit()
        raise HTTPException(status_code=500, detail=parse_llm_error(exc)) from exc
