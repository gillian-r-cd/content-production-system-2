# backend/core/agent_tools.py
# 功能: LangGraph Agent 的工具定义层
# 主要导出: AGENT_TOOLS (list[BaseTool]) — 注册到 Agent 的全部 @tool
#           PENDING_SUGGESTIONS (dict) — 未确认的 SuggestionCard 内存缓存
#           PRODUCE_TOOLS (set) — 直接写 DB 的工具名集合（前端据此刷新）
# 安全机制:
#   - _is_structured_handler(): 阻止纯文本工具覆写结构化内容块（含父块继承）
#   - _is_explicit_rewrite_intent(): 双重守护（用户消息 + LLM instruction）
#   - rewrite_field: 走 SuggestionCard 确认流程，不直接写 DB
#   - generate_field_content: 对已有内容拒绝覆写，除非用户明确要求重新生成
# 设计原则:
#   1. 每个 @tool 是现有 tool 模块的薄包装，复用已有逻辑
#   2. docstring 是 LLM 选择工具的唯一依据（通过 bind_tools → JSON Schema）
#   3. project_id 从 RunnableConfig 获取（LangGraph 自动透传）
#   4. DB session 在工具内部创建，不从 State 传递
#   5. propose_edit 只生成预览不写 DB，修改由 Confirm API 执行

"""
Agent 工具定义

使用 LangChain @tool 装饰器，让 LLM 通过 Tool Calling 自动选择。
每个工具的 docstring 会被 bind_tools() 提取为 function calling 的 description。

用法:
    from core.agent_tools import AGENT_TOOLS
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)
"""

import json
import logging
import re
from typing import Optional, List, Annotated

from pydantic import BaseModel, Field
from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from core.llm_compat import normalize_content, get_stop_reason

logger = logging.getLogger("agent_tools")


# ============== Pydantic 模型（让 bind_tools 生成精确 JSON Schema） ==============

class EditOperation(BaseModel):
    """单条编辑操作"""
    type: str = Field(description="操作类型: replace | insert_after | delete")
    anchor: str = Field(description="原文中精确存在的文本片段，用于定位修改位置。必须是原文的精确子串。")
    new_text: str = Field(description="替换后的新文本。delete 操作时传空字符串 ''。")


# ============== 辅助函数 ==============

def _get_project_id(config: RunnableConfig) -> str:
    """从 RunnableConfig 提取 project_id"""
    if not config:
        raise ValueError("config is required — project_id must be in configurable")
    return config.get("configurable", {}).get("project_id", "")


def _get_db():
    """获取 DB session (短生命周期，用完必须 close)"""
    from core.database import get_db
    return next(get_db())


def _find_block(db, project_id: str, name: str):
    """
    根据名称查找 ContentBlock。
    返回 ContentBlock 或 None。
    """
    from core.models.content_block import ContentBlock

    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name == name,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()


def _save_version(db, entity_id: str, old_content: str, source: str):
    """保存内容版本快照（覆写前调用）— 代理到 version_service"""
    from core.version_service import save_content_version
    save_content_version(db, entity_id, old_content, source)


def _json_ok(target_field: str, status: str, summary: str, **extra) -> str:
    """标准成功 JSON 响应"""
    return json.dumps(
        {"status": status, "target_field": target_field, "summary": summary, **extra},
        ensure_ascii=False,
    )


def _json_err(message: str) -> str:
    """标准错误 JSON 响应"""
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def _set_content_status(entity) -> None:
    """根据 need_review 设置内容块状态。
    
    - need_review=True → in_progress（等待用户确认）
    - need_review=False → completed（自动完成）
    """
    if hasattr(entity, "need_review") and entity.need_review:
        entity.status = "in_progress"
    else:
        entity.status = "completed"


# 使用结构化 JSON 内容的 special_handler 集合。
# 这些内容块有专用 UI 和专用工具，不能被纯文本工具（rewrite_field / generate_field_content）覆写。
_STRUCTURED_HANDLERS = frozenset({
    "research",            # 消费者调研（结构化 JSON，必须走 run_research）
    "eval_persona_setup",   # 目标消费者画像 → manage_persona
    "eval_task_config",     # 评估任务配置 → 前端专用 UI
    "eval_report",          # 评估报告 → run_evaluation
})


def _is_structured_handler(entity) -> bool:
    """判断内容块是否使用结构化 JSON 格式，不能被纯文本工具覆写。

    直接检查 entity.special_handler。子 field 块在创建时已从父 phase 块
    继承 special_handler（见 phase_template.py::apply_to_project + migrate_special_handler.py）。
    """
    handler = getattr(entity, "special_handler", None)
    return handler in _STRUCTURED_HANDLERS


def _is_explicit_rewrite_intent(instruction: str) -> bool:
    """是否为明确的全文重写指令（运行时保险丝，避免误触发 rewrite_field）。"""
    text = (instruction or "").strip().lower()
    if not text:
        return False
    # 只要出现"局部编辑/小改"语义，直接判定不是全文重写
    partial_hints = (
        "改一下", "优化一下", "微调", "润色", "局部", "一句", "一段", "开头", "结尾",
        "replace", "edit", "small change",
    )
    if any(h in text for h in partial_hints):
        return False

    rewrite_keywords = (
        "重写", "全文", "整篇", "通篇", "从头写", "从头改", "完全重做", "整体改写", "整体调整",
        "rewrite", "rewrite all", "rewrite whole", "from scratch",
    )
    if any(k in text for k in rewrite_keywords):
        return True

    # 兜底：包含"风格/语气" + 全局范围词，也视为全文重写
    style_terms = ("风格", "语气", "口吻", "style", "tone")
    global_scope_terms = ("整体", "全文", "整篇", "全篇", "通篇", "all", "whole")
    return any(s in text for s in style_terms) and any(g in text for g in global_scope_terms)


# ============== Suggestion Card 缓存 ==============
# M1: 内存字典缓存未确认的 SuggestionCard（M5 迁移到 DB）
# key = suggestion_id (UUID), value = SuggestionCard dict
PENDING_SUGGESTIONS: dict[str, dict] = {}


# ============== 0. propose_edit ==============

@tool
async def propose_edit(
    target_field: str,
    summary: str,
    reason: str,
    edits: List[EditOperation],
    group_id: str = "",
    group_summary: str = "",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """向用户提出内容修改建议，展示修改预览供用户确认。不会直接执行修改。

    CRITICAL 粒度规则: 每次调用产生一张 SuggestionCard = 用户的一个独立决策单元。
    - 多条逻辑独立的建议，即使针对同一内容块，也应分多次调用（每次一张卡片），让用户可以分别接受/拒绝。
    - 只有当多条 edits 之间存在逻辑依赖（如改了标题就必须同步改正文引用）时，才合并到一次调用。
    - 典型示例: 你有3条独立改进建议 → 调用3次 propose_edit，每次1-2个 edits → 用户看到3张可独立操作的卡片。
    - 反例: 把3条独立建议塞进1次调用的 edits 列表 → 用户只能整体接受/拒绝，失去细粒度控制。

    何时使用:
    - 你分析后认为某个内容块需要修改，且有具体的修改方案
    - 用户说"帮我改一下 XX"（默认走确认流程）
    - 评估/批评后有具体的可操作改进点
    - 一句话能说清楚"改什么"和"为什么改"

    何时不使用:
    - 还在讨论方向，不确定该怎么改 -> 文本对话
    - 有多种修改方向需要用户选择 -> 文本对话，列出选项
    - 修改范围太大（整篇重写） -> generate_field_content
    - 全文重写、风格调整 -> rewrite_field

    CRITICAL: anchor 必须是目标内容块中精确存在的文本片段。不确定时先用 read_field 查看原文。

    Args:
        target_field: 目标内容块名称
        summary: 一句话描述这张卡片的修改内容（如"加强开头的吸引力"）
        reason: 这张卡片的修改原因（如"当前开头过于平淡，缺少 hook"）
        edits: 这张卡片包含的编辑操作（通常1-2个紧密相关的操作）
        group_id: 多字段修改的组 ID（可选）
        group_summary: 整组修改的总体说明（仅首次调用时提供）
    """
    from core.edit_engine import apply_edits, generate_revision_markdown
    from core.models import generate_uuid

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        entity = _find_block(db, project_id, target_field)
        if not entity:
            return _json_err(f"找不到内容块「{target_field}」")

        # 防护：结构化 special_handler 块不能被纯文本编辑
        if _is_structured_handler(entity):
            return _json_err(
                f"内容块「{target_field}」是结构化数据块（{entity.special_handler}），"
                f"不能使用 propose_edit 修改。请使用对应的专用工具。"
            )

        original_content = entity.content or ""
        if not original_content.strip():
            return _json_err(f"内容块「{target_field}」为空，请使用 generate_field_content 生成内容")

        # Pydantic 模型转 dict 供 edit_engine 使用
        edits_dicts = [e.model_dump() for e in edits]

        # 调用 edit_engine 生成预览
        modified_content, changes = apply_edits(original_content, edits_dicts)

        # 检查是否有任何编辑成功应用
        applied = [c for c in changes if c["status"] == "applied"]
        failed = [c for c in changes if c["status"] == "failed"]

        if not applied and failed:
            # 所有编辑都失败了 — fallback: 用全文 diff
            fail_reasons = "; ".join(
                f"anchor '{c.get('anchor', '')[:30]}...' -> {c['reason']}" for c in failed
            )
            logger.warning(f"[propose_edit] 所有 edits 失败: {fail_reasons}")
            return _json_err(f"编辑定位失败: {fail_reasons}。请使用 read_field 查看原文后重试。")

        # 生成 diff 预览
        diff_preview = generate_revision_markdown(original_content, modified_content)

        # 构造 SuggestionCard
        suggestion_id = generate_uuid()
        card = {
            "id": suggestion_id,
            "card_type": "anchor_edit",
            "group_id": group_id or None,
            "group_summary": group_summary or None,
            "target_field": target_field,
            "target_entity_id": entity.id,
            "summary": summary,
            "reason": reason,
            "edits": edits_dicts,
            "changes": changes,
            "diff_preview": diff_preview,
            "original_content": original_content,
            "modified_content": modified_content,
            "status": "pending",
            "source_mode": config.get("configurable", {}).get("thread_id", "").split(":")[-1] or "assistant",
        }

        # 缓存到内存字典
        PENDING_SUGGESTIONS[suggestion_id] = card
        logger.info(f"[propose_edit] 缓存建议 {suggestion_id[:8]}... 目标={target_field}, "
                     f"edits={len(edits)}, applied={len(applied)}, failed={len(failed)}")

        # 返回结构化 JSON — SSE 层会解析这个输出
        return json.dumps({
            "status": "suggestion",
            "id": suggestion_id,
            "group_id": group_id or None,
            "group_summary": group_summary or None,
            "target_field": target_field,
            "target_entity_id": entity.id,
            "summary": summary,
            "reason": reason,
            "diff_preview": diff_preview,
            "edits_count": len(edits),
            "applied_count": len(applied),
            "failed_count": len(failed),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"propose_edit error: {e}", exc_info=True)
        return _json_err(str(e))
    finally:
        db.close()


# ============== 1. rewrite_field (原 modify_field) ==============

@tool
async def rewrite_field(
    field_name: str,
    instruction: str,
    reference_fields: Optional[List[str]] = None,
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """重写整个内容块。用 LLM 重新生成全文内容，直接写入数据库。

    适用于 anchor-based 局部编辑无法覆盖的场景：全文重写、风格/语气调整、大范围改写。

    何时使用:
    - 用户说"重写""从头写""整体调整语气""改成更口语化的风格"
    - 修改范围覆盖整篇内容（不适合用 anchor 逐一定位）
    - 用户要求大范围改变写作风格或结构

    何时不使用:
    - 局部修改（改一段、改一句、改几个词） -> propose_edit
    - 用户说"帮我改一下" -> propose_edit（默认走确认流程）
    - 内容块为空需首次生成 -> generate_field_content
    - 创建新内容块 -> manage_architecture

    典型用法:
    - "把 @场景库 整个重写，风格更活泼一些" -> rewrite_field("场景库", "重写，风格更活泼")
    - "参考 @用户画像 重写 @传播策略" -> rewrite_field("传播策略", "重写", ["用户画像"])
    - "把 @开头 改成更口语化的风格" -> rewrite_field("开头", "改成口语化风格")

    Args:
        field_name: 要重写的目标内容块名称
        instruction: 用户的具体重写指令
        reference_fields: 需要参考的其他内容块名称列表
    """
    return await _rewrite_field_impl(field_name, instruction, reference_fields or [], config)


async def _rewrite_field_impl(
    field_name: str,
    instruction: str,
    reference_fields: List[str],
    config: RunnableConfig,
) -> str:
    from core.llm import llm
    from langchain_core.messages import SystemMessage, HumanMessage

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        # 指令级守护：检查 LLM 构造的 instruction 是否有明确的全文重写意图
        # 即使被绕过，rewrite_field 现在也走 SuggestionCard 确认流程（用户有最终决定权）
        if not _is_explicit_rewrite_intent(instruction):
            return _json_err(
                "rewrite_field 仅用于明确的全文重写。当前指令更像局部修改，"
                "请改用 propose_edit（Suggestion Card）以降低误改风险。"
            )

        entity = _find_block(db, project_id, field_name)
        if not entity:
            return _json_err(f"找不到内容块「{field_name}」")

        # 防护：结构化 special_handler 块不能用纯文本重写，应使用专用工具
        if _is_structured_handler(entity):
            return _json_err(
                f"内容块「{field_name}」是结构化数据块（{entity.special_handler}），"
                f"不能使用 rewrite_field 修改。请使用对应的专用工具（如 run_research / manage_persona）。"
            )

        current_content = entity.content or ""
        if not current_content.strip():
            return _json_err(f"内容块「{field_name}」为空，请使用 generate_field_content 生成内容")

        # 读取参考内容
        ref_ctx = ""
        for ref_name in reference_fields:
            ref_entity = _find_block(db, project_id, ref_name)
            if ref_entity and ref_entity.content:
                ref_ctx += f"\n\n### 参考内容块「{ref_name}」\n{ref_entity.content[:2000]}"

        system_prompt = f"""你是一个专业的内容修改助手。请根据指令修改以下内容块，保持原有风格和结构。

## 当前内容块：{field_name}
{current_content}
{f"## 参考内容{ref_ctx}" if ref_ctx else ""}

## 修改要求
{instruction}

请直接输出修改后的完整内容，不要添加任何解释或前缀。"""

        # ⚠️ 传 config 给 LLM 调用，确保 astream_events 能捕获工具内 LLM 的流式 token
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请按要求修改「{field_name}」的内容。"),
        ], config=config)

        new_content = normalize_content(response.content)

        reason, truncated = get_stop_reason(response)
        if truncated:
            logger.warning(f"[rewrite_field] 输出被截断（{reason}），不保存，内容 {len(new_content)} 字")
            return _json_err(f"修改内容被截断（{len(new_content)} 字），内容过长。建议拆分内容块或使用更简洁的指令。")

        # 走 SuggestionCard 确认流程，不直接写 DB
        from core.edit_engine import generate_revision_markdown
        from core.models import generate_uuid

        diff_preview = generate_revision_markdown(current_content, new_content)

        suggestion_id = generate_uuid()
        card = {
            "id": suggestion_id,
            "card_type": "full_rewrite",
            "group_id": None,
            "group_summary": None,
            "target_field": field_name,
            "target_entity_id": entity.id,
            "summary": f"全文重写「{field_name}」",
            "reason": instruction,
            "edits": [],
            "changes": [],
            "diff_preview": diff_preview,
            "original_content": current_content,
            "modified_content": new_content,
            "status": "pending",
            "source_mode": config.get("configurable", {}).get("thread_id", "").split(":")[-1] or "assistant",
        }

        PENDING_SUGGESTIONS[suggestion_id] = card
        logger.info(f"[rewrite_field] 生成重写建议卡片 {suggestion_id[:8]}..., 目标={field_name}, {len(new_content)} 字")

        return json.dumps({
            "status": "suggestion",
            "id": suggestion_id,
            "target_field": field_name,
            "target_entity_id": entity.id,
            "summary": f"全文重写「{field_name}」",
            "reason": instruction,
            "diff_preview": diff_preview,
            "edits_count": 1,
            "applied_count": 1,
            "failed_count": 0,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"rewrite_field error: {e}", exc_info=True)
        db.rollback()
        return _json_err(str(e))
    finally:
        db.close()


# ============== 2. generate_field_content ==============

@tool
async def generate_field_content(
    field_name: str,
    instruction: str = "",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """为空白内容块首次生成内容。

    何时使用:
    - 内容块当前为空，需要首次生成
    - 用户说"生成XX""帮我写XX"（且内容块当前为空）

    何时不使用:
    - 内容块已有内容 → 一律拒绝。局部修改用 propose_edit，全文重写用 rewrite_field
    - 用户想看已有内容 → read_field
    - 用户想改项目结构 → manage_architecture

    典型场景:
    - "生成场景库" → generate_field_content("场景库")
    - "帮我写一个详细的意图分析" → generate_field_content("意图分析", "详细的")

    Args:
        field_name: 要生成内容的内容块名称
        instruction: 额外的生成指令或要求
    """
    return await _generate_field_impl(field_name, instruction, config)


async def _generate_field_impl(
    field_name: str,
    instruction: str,
    config: RunnableConfig,
) -> str:
    from core.llm import llm
    from langchain_core.messages import SystemMessage, HumanMessage
    from core.models import Project

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        entity = _find_block(db, project_id, field_name)
        if not entity:
            return _json_err(f"找不到内容块「{field_name}」")

        # 防护：结构化 special_handler 块不能用纯文本生成，应使用专用工具
        if _is_structured_handler(entity):
            return _json_err(
                f"内容块「{field_name}」是结构化数据块（{entity.special_handler}），"
                f"不能使用 generate_field_content 生成。请使用对应的专用工具（如 run_research / manage_persona）。"
            )

        # 防护：已有内容的块不能用 generate（直接写 DB）覆写
        # 局部修改 → propose_edit（确认流程），全文重写 → rewrite_field（确认流程）
        if entity.content and entity.content.strip():
            return _json_err(
                f"内容块「{field_name}」已有内容（{len(entity.content)} 字）。"
                f"generate_field_content 仅用于空块的首次生成。"
                f"如需局部修改请使用 propose_edit，如需全文重写请使用 rewrite_field。"
            )

        project = db.query(Project).filter(Project.id == project_id).first()
        creator_ctx = ""
        if project and project.creator_profile:
            creator_ctx = project.creator_profile.to_prompt_context()

        ai_prompt = getattr(entity, "ai_prompt", "") or ""

        # 收集依赖内容（depends_on 是 block ID 列表）
        deps_ctx = ""
        depends_on = getattr(entity, "depends_on", None) or []
        if depends_on and isinstance(depends_on, list):
            from core.models.content_block import ContentBlock as CB
            for dep_id in depends_on:
                dep_block = db.query(CB).filter(
                    CB.id == dep_id,
                    CB.deleted_at == None,  # noqa: E711
                ).first()
                if dep_block and dep_block.content:
                    deps_ctx += f"\n### {dep_block.name}\n{dep_block.content[:2000]}"

        sections = [f"你是一个专业的内容创作助手。请为「{field_name}」生成高质量的内容。"]
        if creator_ctx:
            sections.append(f"## 创作者信息\n{creator_ctx}")
        if ai_prompt:
            sections.append(f"## 内容块要求\n{ai_prompt}")
        if deps_ctx:
            sections.append(f"## 依赖内容（作为参考）{deps_ctx}")
        if instruction:
            sections.append(f"## 额外指令\n{instruction}")
        sections.append("请直接输出内容，不要添加前缀或解释。")
        system_prompt = "\n\n".join(sections)

        # ⚠️ 传 config 给 LLM 调用，确保 astream_events 能捕获工具内 LLM 的流式 token
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请生成「{field_name}」的内容。"),
        ], config=config)

        new_content = normalize_content(response.content)

        reason, truncated = get_stop_reason(response)
        if truncated:
            logger.warning(f"[generate_field_content] 输出被截断 ({reason}), {len(new_content)} 字")
            return _json_err(f"生成内容被截断（{len(new_content)} 字），内容过长。建议拆分内容块。")

        if entity.content and entity.content.strip():
            _save_version(db, entity.id, entity.content, "agent")
        entity.content = new_content
        _set_content_status(entity)
        db.commit()

        logger.info(f"[generate_field_content] 已生成「{field_name}」, {len(new_content)} 字")
        return _json_ok(field_name, "generated", f"✅ 已生成「{field_name}」的内容")

    except Exception as e:
        logger.error(f"generate_field_content error: {e}", exc_info=True)
        db.rollback()
        return _json_err(str(e))
    finally:
        db.close()


# ============== 3. query_field ==============

@tool
async def query_field(
    field_name: str,
    question: str,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """查询内容块并回答相关问题。用 LLM 分析内容后回答，而非直接返回原文。

    何时使用:
    - 用户问关于某个内容块的具体问题："XX写了什么""XX怎么样""总结一下XX"
    - 需要对内容进行分析、评价、摘要

    何时不使用:
    - 需要获取原文用于 propose_edit 的 anchor 定位 → read_field
    - 用户明确说"让我看看原文" → read_field
    - 用户想修改内容 → propose_edit 或 rewrite_field

    典型场景:
    - "@逐字稿1 这个怎么样" → query_field("逐字稿1", "这个怎么样")
    - "意图分析里写了什么？" → query_field("意图分析", "写了什么")

    Args:
        field_name: 要查询的内容块名称
        question: 用户的具体问题
    """
    return await _query_field_impl(field_name, question, config)


async def _query_field_impl(field_name: str, question: str, config: RunnableConfig) -> str:
    from core.llm import llm
    from langchain_core.messages import SystemMessage, HumanMessage

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        entity = _find_block(db, project_id, field_name)
        if not entity:
            return f"找不到内容块「{field_name}」"

        content = entity.content or ""
        if not content.strip():
            return f"内容块「{field_name}」为空，还没有生成内容。"

        # ⚠️ 传 config 给 LLM 调用
        response = await llm.ainvoke([
            SystemMessage(content=f"你是内容分析助手。以下是内容块「{field_name}」的内容：\n\n{content[:4000]}"),
            HumanMessage(content=question),
        ], config=config)
        return normalize_content(response.content)
    except Exception as e:
        return f"查询失败: {e}"
    finally:
        db.close()


# ============== 4. read_field ==============

@tool
def read_field(field_name: str, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """读取指定内容块的完整原始内容并返回。不经过 LLM 处理，直接返回原文。

    何时使用:
    - 在调用 propose_edit 之前，需要确认原文中有哪些 anchor 可用
    - 用户说"看看场景库""让我看一下原文"
    - 需要获取完整内容供自己分析或回复引用

    何时不使用:
    - 用户想让你分析/总结/评价内容 → query_field（会用 LLM 分析后回答）
    - 用户想修改内容 → propose_edit 或 rewrite_field（它们内部会自动读取）
    - 只需要看摘要 → 直接看 field_index 中的摘要即可

    Args:
        field_name: 要读取的内容块名称
    """
    project_id = _get_project_id(config)
    db = _get_db()
    try:
        entity = _find_block(db, project_id, field_name)
        if not entity:
            return f"找不到内容块「{field_name}」"
        content = entity.content or ""
        return content if content.strip() else f"内容块「{field_name}」为空。"
    finally:
        db.close()


# ============== 5. update_field ==============

@tool
def update_field(field_name: str, content: str, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """直接用给定内容完整覆写指定内容块。仅当用户提供了完整的新内容要求直接替换时使用。

    何时使用:
    - 用户提供了完整的新内容文本，要求直接替换
    - 用户粘贴了一段内容说"把XX替换成这个"

    何时不使用:
    - 局部修改 → propose_edit（默认）或 rewrite_field（全文重写）
    - 让 AI 生成内容 → generate_field_content
    - Agent 自主判断需要更新 → propose_edit

    典型场景:
    - 用户粘贴一大段内容："把场景库改成这个：[内容]" → update_field("场景库", "[内容]")

    Args:
        field_name: 要更新的内容块名称
        content: 新的完整内容（将替换全部现有内容）
    """
    project_id = _get_project_id(config)
    db = _get_db()
    try:
        entity = _find_block(db, project_id, field_name)
        if not entity:
            return _json_err(f"找不到内容块「{field_name}」")

        # 防护：结构化 special_handler 块不能被纯文本覆写
        if _is_structured_handler(entity):
            return _json_err(
                f"内容块「{field_name}」是结构化数据块（{entity.special_handler}），"
                f"不能使用 update_field 覆写。请使用对应的专用工具。"
            )

        if entity.content and entity.content.strip():
            _save_version(db, entity.id, entity.content, "agent")
        entity.content = content
        _set_content_status(entity)
        db.commit()

        return _json_ok(field_name, "updated", f"已更新「{field_name}」")
    except Exception as e:
        db.rollback()
        return _json_err(str(e))
    finally:
        db.close()


# ============== 6. manage_architecture ==============

@tool
def manage_architecture(
    operation: str,
    target: str,
    details: str = "",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """管理项目结构：添加/删除/移动内容块或组。当用户要求改变项目的结构时使用。

    何时使用:
    - 用户要求添加、删除、移动内容块或组
    - 用户说"帮我加一个XX""删掉XX""把XX移到YY组"

    何时不使用:
    - 改内容块里的文字 → propose_edit 或 rewrite_field
    - 生成内容 → generate_field_content
    - 推进项目阶段 → advance_to_phase

    典型场景:
    - "帮我加一个新内容块叫XX" → manage_architecture("add_field", "XX", '{"phase":"design_inner"}')
    - "删掉场景库" → manage_architecture("remove_field", "场景库")
    - "新增一个组叫测试" → manage_architecture("add_phase", "test", '{"display_name":"测试"}')

    Args:
        operation: 操作类型 — add_field / remove_field / move_field / add_phase / remove_phase
        target: 操作目标（内容块名或组名）
        details: 操作详情（JSON 字符串，如 {"phase":"design_inner","ai_prompt":"..."} 或 {"display_name":"..."} 或 {"target_phase":"..."}）
    """
    from core.tools.architecture_writer import (
        add_phase, remove_phase, add_field, remove_field, move_field,
    )

    project_id = _get_project_id(config)

    # 解析 details
    try:
        params = json.loads(details) if details else {}
    except json.JSONDecodeError:
        params = {"raw": details}

    try:
        if operation == "add_phase":
            display_name = params.get("display_name", target)
            position = params.get("position")
            result = add_phase(project_id, target, display_name, position)

        elif operation == "remove_phase":
            result = remove_phase(project_id, target)

        elif operation == "add_field":
            phase = params.get("phase", "")
            ai_prompt = params.get("ai_prompt", "")
            depends_on = params.get("depends_on")
            if not phase:
                return _json_err("添加内容块需要指定所属组 (phase)，请在 details 中提供 {\"phase\": \"组名\"}")
            result = add_field(project_id, phase, target, ai_prompt, depends_on)

        elif operation == "remove_field":
            result = remove_field(project_id, target)

        elif operation == "move_field":
            target_phase = params.get("target_phase", "")
            if not target_phase:
                return _json_err("移动内容块需要指定目标组 (target_phase)")
            result = move_field(project_id, target, target_phase)

        else:
            return _json_err(f"未知操作: {operation}。支持: add_field / remove_field / move_field / add_phase / remove_phase")

        return result.message if result.success else _json_err(result.error or result.message)

    except Exception as e:
        logger.error(f"manage_architecture error: {e}", exc_info=True)
        return _json_err(str(e))


# ============== 7. advance_to_phase ==============

@tool
def advance_to_phase(target_phase: str = "", *, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """推进项目到下一组或跳转到指定组。

    何时使用:
    - 用户说"继续""下一步""进入XX阶段"
    - 当前组的内容已完成，用户准备进入下一阶段

    何时不使用:
    - 用户想修改当前组的内容 → propose_edit 或 rewrite_field
    - 用户想添加新组 → manage_architecture("add_phase", ...)
    - 用户只是在讨论流程，还没决定推进 → 文本对话

    典型场景:
    - "进入外延设计" → advance_to_phase("design_outer")
    - "继续" → advance_to_phase("")

    Args:
        target_phase: 目标组名称（如 "research"、"design_inner"）。为空表示自动下一组。
    """
    from core.models import Project
    from core.phase_service import advance_phase

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return "项目不存在"

        result = advance_phase(project, target_phase)
        if not result.success:
            return result.error

        db.commit()
        return f"✅ 已进入组【{result.next_phase}】"

    except Exception as e:
        db.rollback()
        return f"推进组失败: {e}"
    finally:
        db.close()


# ============== 8. run_research ==============

@tool
async def run_research(
    query: str,
    research_type: str = "consumer",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """执行调研。分析目标用户或调研特定主题。

    何时使用:
    - 用户说"开始消费者调研""帮我调研XX"
    - 项目需要用户画像数据或市场信息

    何时不使用:
    - 用户想管理已有的消费者画像 → manage_persona
    - 用户想查看已有的调研报告 → read_field("消费者调研")
    - 用户在讨论内容修改 → propose_edit 或 rewrite_field

    典型场景:
    - "开始消费者调研" → run_research("消费者调研", "consumer")
    - "调研一下AI教育市场" → run_research("AI教育市场", "generic")

    Args:
        query: 调研主题或查询内容
        research_type: "consumer"（消费者调研）或 "generic"（通用深度调研）
    """
    return await _run_research_impl(query, research_type, config)


async def _run_research_impl(query: str, research_type: str, config: RunnableConfig) -> str:
    from core.tools.deep_research import deep_research
    from core.tools.architecture_reader import get_intent_and_research
    from core.models import Project
    from core.models.content_block import ContentBlock

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        # 获取项目意图
        deps = get_intent_and_research(project_id)
        intent = deps.get("intent", query)

        report = await deep_research(
            query=query or ("目标消费者深度调研" if research_type == "consumer" else query),
            intent=intent,
            research_type=research_type,
            config=config,
        )

        report_json = report.model_dump_json(indent=2, ensure_ascii=False)
        saved = False

        # 1. 保存到 ContentBlock — 优先找 field 子块（如"消费者调研报告"），
        #    避免 .first() 匹配到 phase 块（"消费者调研"本身）
        research_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name.in_(["消费者调研报告", "消费者调研"]),
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        # fallback: 旧项目可能只有 phase 块
        if not research_block:
            research_block = db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.name.in_(["消费者调研报告", "消费者调研"]),
                ContentBlock.deleted_at == None,  # noqa: E711
            ).first()
        if research_block:
            if research_block.content:
                _save_version(db, research_block.id, research_block.content, "agent")
            research_block.content = report_json
            _set_content_status(research_block)
            db.flush()
            saved = True

        # NOTE: ProjectField 保存路径已移除（P0-1 统一到 ContentBlock）

        if saved:
            db.commit()

        summary = report.summary[:500] if hasattr(report, "summary") else str(report)[:500]
        return json.dumps({
            "status": "completed",
            "target_field": "消费者调研",
            "summary": f"✅ 调研完成。{summary}",
            "research_type": research_type,
            "sources": list(getattr(report, "sources", []) or []),
            "search_queries": list(getattr(report, "search_queries", []) or []),
            "content_length": int(getattr(report, "content_length", 0) or 0),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"run_research error: {e}", exc_info=True)
        return f"❌ 调研执行失败（工具错误）: {e}"
    finally:
        db.close()


# ============== 9. manage_persona ==============

@tool
async def manage_persona(
    operation: str,
    persona_data: str = "",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """管理消费者画像/角色。创建、查看、更新、删除消费者画像。

    何时使用:
    - 用户说"创建一个画像""分析一下我的目标用户" → generate
    - 用户说"看看有哪些画像" → list
    - 用户说"更新画像的职业信息" → update
    - 用户说"删掉这个画像" → delete

    何时不使用:
    - 用户在讨论内容修改 → propose_edit 或 rewrite_field
    - 用户想看消费者调研报告 → read_field("消费者调研")
    - 用户说"帮我做消费者调研" → run_research

    Args:
        operation: list（查看所有画像）/ create（手动创建）/ generate（AI生成）/ update（更新）/ delete（删除）
        persona_data: 角色描述或数据（JSON 字符串，create/generate/update 时需要）
    """
    return await _manage_persona_impl(operation, persona_data, config)


async def _manage_persona_impl(operation: str, persona_data: str, config: RunnableConfig) -> str:
    from core.tools.persona_manager import (
        manage_persona as pm_manage,
        PersonaOperation,
    )

    project_id = _get_project_id(config)

    # 将字符串操作转为枚举
    try:
        op_enum = PersonaOperation(operation.lower())
    except ValueError:
        return f"未知操作: {operation}。支持: list / create / generate / update / delete"

    # 解析 persona_data 为 dict
    params = {}
    if persona_data:
        try:
            params = json.loads(persona_data)
        except json.JSONDecodeError:
            # 纯文本描述
            params = {"description": persona_data, "name": persona_data[:20]}

    result = await pm_manage(
        project_id=project_id,
        operation=op_enum,
        params=params,
    )

    return result.message if result.success else f"操作失败: {result.message}"


# ============== 10. run_evaluation ==============

@tool
async def run_evaluation(
    field_names: Optional[List[str]] = None,
    grader_name: Optional[str] = None,
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """运行 Eval V2 多角色模拟评估流水线（高成本操作：多轮 LLM 对话 × 多角色并行）。

    CRITICAL: 此工具会启动完整的 Eval V2 流水线（教练审查 + 编辑审查 + 专家审查 + 消费者多轮对话 + 销售多轮对话），
    消耗大量 token 且执行时间长。结果数据设计为在 EvalPanel 中展示，Agent 只返回简短摘要。

    何时使用（必须同时满足以下全部条件）:
    1. 用户明确说出"评估""运行评估""跑一下评估"等指向 Eval V2 流水线的关键词
    2. 用户提供了明确的评估目标字段名称（field_names 不能为空）
    3. 用户知道这是一个模拟评估流水线（区别于"审查""批评""看看质量"）

    何时不使用:
    - 用户说"审查一下""帮我看看质量""检查一下" → 直接用 read_field + 文本分析（这是审稿/批评，不是 Eval V2）
    - 用户说"评价一下" 但没有指定具体字段名 → 先询问要评估哪些字段
    - critic/审稿人模式下做内容审查 → 用 read_field 读内容后直接给出文本反馈
    - 内容块还没有生成内容 → 先 generate_field_content
    - 用户想修改内容 → propose_edit 或 rewrite_field
    - 用户只是想看内容 → read_field 或 query_field

    反例（NEVER 这样做）:
    - 审稿人模式下用户说"帮我审查一下内容" → NEVER 调用 run_evaluation（应该用 read_field + 文本分析）
    - 用户说"看看这个内容怎么样" → NEVER 调用 run_evaluation（应该用 query_field 或 read_field）
    - 用户说"评估一下" 但没说具体评估什么字段 → 先询问，NEVER 直接调用

    典型用法（注意：必须有用户明确指定的 field_names）:
    - "对场景库运行评估" → run_evaluation(field_names=["场景库"])
    - "用原创性 grader 评价场景库" → run_evaluation(field_names=["场景库"], grader_name="原创性")

    Args:
        field_names: 要评估的内容块名称列表。CRITICAL: 必须由用户明确提供，不能为空。
        grader_name: 指定使用的评估维度/Grader 名称。为空时使用全部评估维度。
    """
    # 运行时安全检查：必须提供 field_names
    if not field_names:
        return ("⚠️ 请指定要评估的内容块名称。run_evaluation 是 Eval V2 多角色模拟流水线（高成本），"
                "需要用户明确指定评估目标。\n\n"
                "如果你只是想审查/检查内容质量，请使用 read_field 读取内容后直接给出分析反馈。")
    return await _run_evaluation_impl(field_names, grader_name, config)


async def _run_evaluation_impl(
    target_field_names: List[str],
    grader_name: Optional[str],
    config: RunnableConfig,
) -> str:
    from core.tools.eval_engine import run_eval
    from core.tools.architecture_reader import get_intent_and_research
    from core.models import Project, ContentBlock

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return "项目不存在。"

        # 获取上下文
        deps = get_intent_and_research(project_id)
        intent = deps.get("intent", "")
        creator_profile = ""
        if project.creator_profile:
            creator_profile = project.creator_profile.to_prompt_context()

        # 收集内容
        blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.content != None,  # noqa: E711
            ContentBlock.deleted_at == None,  # noqa: E711
        ).all()

        # 按名称筛选（如果指定了 field_names）
        if target_field_names:
            blocks = [b for b in blocks if b.name in target_field_names]

        content = "\n\n".join(f"## {b.name}\n{b.content}" for b in blocks if b.content)
        field_names = [b.name for b in blocks if b.content]

        if not content.strip():
            target_desc = "、".join(target_field_names) if target_field_names else "项目"
            return f"{target_desc}还没有生成任何内容，无法评估。"

        # 运行评估
        trial_results, diagnosis = await run_eval(
            content=content,
            creator_profile=creator_profile,
            intent=intent,
            content_field_names=field_names,
        )

        # 返回摘要
        overall = diagnosis.get("overall_score", 0)
        summary = diagnosis.get("summary", "评估完成。")
        target_desc = "、".join(target_field_names) if target_field_names else "全部内容"
        grader_desc = f"（{grader_name}维度）" if grader_name else ""
        return f"✅ {target_desc}{grader_desc}评估完成。综合评分: {overall}/10\n{summary}"

    except Exception as e:
        logger.error(f"run_evaluation error: {e}", exc_info=True)
        return f"评估失败: {e}"
    finally:
        db.close()


# ============== 11. generate_outline ==============

@tool
async def generate_outline(topic: str = "", *, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """生成内容大纲/结构规划。帮助创作者规划内容的整体架构。

    何时使用:
    - 用户说"帮我设计大纲""规划一下内容结构"
    - 项目初期需要内容架构规划

    何时不使用:
    - 用户想修改已有内容 → propose_edit 或 rewrite_field
    - 用户想改项目结构（增删内容块）→ manage_architecture
    - 用户想生成具体内容块的内容 → generate_field_content

    典型场景:
    - "帮我设计一下大纲" → generate_outline()
    - "做一个关于AI培训的课程大纲" → generate_outline("AI培训课程")

    Args:
        topic: 大纲主题（为空则基于项目意图自动规划）
    """
    return await _generate_outline_impl(topic, config)


async def _generate_outline_impl(topic: str, config: RunnableConfig) -> str:
    from core.tools.outline_generator import generate_outline as og_generate

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        outline = await og_generate(
            project_id=project_id,
            content_type="",  # 自动推断
            structure_hint=topic,
            db=db,
        )

        if outline:
            parts = [f"✅ 大纲已生成：{outline.title}"]
            if hasattr(outline, "summary") and outline.summary:
                parts.append(outline.summary)
            if hasattr(outline, "nodes") and outline.nodes:
                parts.append(f"共 {len(outline.nodes)} 个章节")
            return "\n".join(parts)
        return "大纲生成失败"
    except Exception as e:
        logger.error(f"generate_outline error: {e}", exc_info=True)
        return f"大纲生成失败: {e}"
    finally:
        db.close()


# ============== 12. manage_skill ==============

@tool
async def manage_skill(
    operation: str,
    skill_name: str = "",
    target_field: str = "",
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """管理和使用写作技能/风格。查看可用技能、用特定风格重写内容。

    何时使用:
    - 用户说"有什么技能""看看可用的风格" → manage_skill("list")
    - 用户说"用XX风格帮我写/改" → manage_skill("apply", "XX", "目标内容块")

    何时不使用:
    - 用户想修改内容但没提到特定风格 → propose_edit 或 rewrite_field
    - 用户想从零生成内容 → generate_field_content
    - 用户在讨论风格方向但还没确定 → 文本对话

    典型场景:
    - "有什么技能可以用" → manage_skill("list")
    - "用专业文案帮我写场景库" → manage_skill("apply", "专业文案", "场景库")

    Args:
        operation: list（查看可用技能）/ apply（应用技能到内容）
        skill_name: 技能名称（apply 时必须）
        target_field: 要应用技能的内容块名称（apply 时必须）
    """
    return await _manage_skill_impl(operation, skill_name, target_field, config)


async def _manage_skill_impl(
    operation: str,
    skill_name: str,
    target_field: str,
    config: RunnableConfig,
) -> str:
    from core.tools.skill_manager import (
        manage_skill as sm_manage,
        SkillOperation,
    )

    try:
        op_enum = SkillOperation(operation.lower())
    except ValueError:
        return f"未知操作: {operation}。支持: list / apply"

    params = {}
    if skill_name:
        params["skill_name"] = skill_name
        params["name"] = skill_name  # some operations expect 'name'
    if target_field:
        params["target_field"] = target_field
        project_id = _get_project_id(config)
        params["project_id"] = project_id

    result = await sm_manage(operation=op_enum, params=params)

    if result.success:
        msg = result.message
        if result.output:
            msg += f"\n{result.output}"
        return msg
    return f"操作失败: {result.message}"


# ============== 跨模式对话查阅（M2 Memory System） ==============

@tool
async def read_mode_history(
    mode_name: str,
    limit: int = 10,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """查阅创作者在其他模式中的对话记录。

    何时使用:
    - 用户引用了其他模式的讨论："按之前和审稿人讨论的来"
    - 需要跨模式上下文来做出更好的决策

    何时不使用:
    - 查看当前模式的对话 → 已在上下文中，无需查阅
    - 查看内容块内容 → read_field
    - 查看项目记忆 → 记忆已在 system prompt 中

    典型场景:
    - 用户说"按审稿人之前的建议改" → read_mode_history("critic")
    - 用户说"之前策略顾问怎么说的" → read_mode_history("strategist")

    Args:
        mode_name: 模式名称，如 "assistant"、"strategist"、"critic"、"reader"、"creative"
        limit: 返回最近几条消息，默认10，最大20
    """
    project_id = _get_project_id(config)
    if not project_id:
        return "无法获取项目 ID"

    limit = min(max(limit, 1), 20)

    db = _get_db()
    try:
        from core.models.chat_history import ChatMessage
        messages = db.query(ChatMessage).filter(
            ChatMessage.project_id == project_id,
        ).order_by(ChatMessage.created_at.desc()).limit(limit * 3).all()

        # 从 metadata 中筛选目标模式的消息
        mode_msgs = []
        for msg in reversed(messages):  # 按时间正序
            meta = msg.message_metadata or {}
            msg_mode = meta.get("mode", "assistant")
            if msg_mode == mode_name:
                mode_msgs.append(msg)
            if len(mode_msgs) >= limit:
                break

        if not mode_msgs:
            return f"「{mode_name}」模式中暂无对话记录。"

        lines = []
        for msg in mode_msgs:
            role = "用户" if msg.role == "user" else "Agent"
            content = msg.content[:500] if msg.content else ""
            lines.append(f"[{role}] {content}")

        return f"「{mode_name}」模式最近 {len(mode_msgs)} 条对话：\n\n" + "\n\n".join(lines)
    finally:
        db.close()


# ============== 导出 ==============

# 所有工具列表 — 注册到 Agent Graph 的 bind_tools()
AGENT_TOOLS = [
    propose_edit,
    rewrite_field,
    generate_field_content,
    query_field,
    read_field,
    update_field,
    manage_architecture,
    advance_to_phase,
    run_research,
    manage_persona,
    run_evaluation,
    generate_outline,
    manage_skill,
    read_mode_history,
]

# 这些工具执行后表示产生了内容块更新，前端需要刷新
# 注意: propose_edit 和 rewrite_field 不在此列 — 它们只生成预览，不写 DB
PRODUCE_TOOLS = {
    "generate_field_content",
    "update_field",
}
