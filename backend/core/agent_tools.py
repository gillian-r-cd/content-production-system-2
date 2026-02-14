# backend/core/agent_tools.py
# 功能: LangGraph Agent 的工具定义层
# 主要导出: AGENT_TOOLS (list[BaseTool]) — 注册到 Agent 的全部 @tool
# 设计原则:
#   1. 每个 @tool 是现有 tool 模块的薄包装，复用已有逻辑
#   2. docstring 是 LLM 选择工具的唯一依据（通过 bind_tools → JSON Schema）
#   3. project_id 从 RunnableConfig 获取（LangGraph 自动透传）
#   4. DB session 在工具内部创建，不从 State 传递

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
from typing import Optional, List, Annotated

from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger("agent_tools")


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


# ============== 1. modify_field ==============

@tool
async def modify_field(
    field_name: str,
    instruction: str,
    reference_fields: Optional[List[str]] = None,
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """修改指定内容块的已有内容。当用户要求修改、调整、重写、优化某个内容块的文本时使用。

    ⚠️ 这是修改【已有内容】（改文字），不是创建新内容块（改结构）。
    - 创建/删除/移动内容块 → 请用 manage_architecture
    - 内容块为空需要首次生成 → 请用 generate_field_content

    典型场景：
    - "@场景库 把5个模块改成7个" → modify_field("场景库", "把5个模块改成7个")
    - "参考 @用户画像 修改 @场景库" → modify_field("场景库", "修改描述", ["用户画像"])

    Args:
        field_name: 要修改的目标内容块名称
        instruction: 用户的具体修改指令
        reference_fields: 需要参考的其他内容块名称列表
    """
    return await _modify_field_impl(field_name, instruction, reference_fields or [], config)


async def _modify_field_impl(
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
        entity = _find_block(db, project_id, field_name)
        if not entity:
            return _json_err(f"找不到内容块「{field_name}」")

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

        new_content = response.content

        # 截断检测：如果 finish_reason == "length"，说明输出被截断，不保存
        finish_reason = (response.response_metadata or {}).get("finish_reason", "stop")
        if finish_reason == "length":
            logger.warning(f"[modify_field] 输出被截断（finish_reason=length），不保存，内容 {len(new_content)} 字")
            return _json_err(f"修改内容被截断（{len(new_content)} 字），内容过长。建议拆分内容块或使用更简洁的指令。")

        _save_version(db, entity.id, current_content, "agent")
        entity.content = new_content
        _set_content_status(entity)
        db.commit()

        logger.info(f"[modify_field] 已修改「{field_name}」, {len(new_content)} 字")
        return _json_ok(field_name, "applied", f"已修改「{field_name}」")

    except Exception as e:
        logger.error(f"modify_field error: {e}", exc_info=True)
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
    """为指定内容块生成内容（从零开始或全部重写）。

    与 modify_field 的区别：
    - generate = 从零生成（内容块为空或需要全部重写）
    - modify = 在已有内容基础上局部修改

    典型场景：
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

        new_content = response.content

        # 截断检测
        finish_reason = (response.response_metadata or {}).get("finish_reason", "stop")
        if finish_reason == "length":
            logger.warning(f"[generate_field_content] 输出被截断, {len(new_content)} 字")
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
    """查询内容块并回答相关问题。当用户想了解、分析、总结某个内容块时使用。

    与 read_field 的区别：query_field 会用 LLM 分析并回答，read_field 只返回原文。

    典型场景：
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
        return response.content
    except Exception as e:
        return f"查询失败: {e}"
    finally:
        db.close()


# ============== 4. read_field ==============

@tool
def read_field(field_name: str, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """读取指定内容块的完整原始内容并返回。

    典型场景：在修改前先读取当前内容、用户说"看看场景库"。

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

    ⚠️ 这会直接覆盖全部内容，没有预览和确认流程。
    - 局部修改 → 请用 modify_field
    - 让 AI 生成 → 请用 generate_field_content

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

        if entity.content and entity.content.strip():
            _save_version(db, entity.id, entity.content, "agent")
        entity.content = content
        _set_content_status(entity)
        db.commit()

        return _json_ok(field_name, "updated", f"✅ 已更新「{field_name}」")
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

    ⚠️ 这是改【项目结构】（增删内容块/组），不是改内容块里的文字。
    - 改文字内容 → 请用 modify_field

    典型场景：
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

    当用户说"继续"、"下一步"、"进入XX阶段"时使用。

    典型场景：
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
    """执行调研。

    两种类型：
    - consumer（消费者调研）：分析目标用户画像、痛点、需求
    - generic（通用深度调研）：搜索并整理特定主题的资料

    典型场景：
    - "开始消费者调研" → run_research("消费者调研", "consumer")
    - "调研一下AI教育市场" → run_research("AI教育市场", "generic")

    Args:
        query: 调研主题或查询内容
        research_type: "consumer" 或 "generic"
    """
    return await _run_research_impl(query, research_type, config)


async def _run_research_impl(query: str, research_type: str, config: RunnableConfig) -> str:
    from core.tools.deep_research import deep_research, quick_research
    from core.tools.architecture_reader import get_intent_and_research
    from core.models import Project
    from core.models.content_block import ContentBlock

    project_id = _get_project_id(config)
    db = _get_db()
    try:
        # 获取项目意图
        deps = get_intent_and_research(project_id)
        intent = deps.get("intent", query)

        if research_type == "consumer":
            report = await deep_research(
                query=query or "目标消费者深度调研",
                intent=intent,
            )
        else:
            report = await deep_research(
                query=query,
                intent=intent,
            )

        report_json = report.model_dump_json(indent=2, ensure_ascii=False)
        saved = False

        # 1. 尝试保存到 ContentBlock（灵活架构）
        research_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name.in_(["消费者调研", "消费者调研报告"]),
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
        return f"✅ 调研完成。\n{summary}"

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
    """管理消费者画像/角色。

    Args:
        operation: list / create / generate / update / delete
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
    """对项目内容执行质量评估，生成评估报告。

    当用户说「评估一下」「检查内容质量」「评价XX内容块」时使用。

    典型场景：
    - 「评估一下」→ run_evaluation()（全量评估）
    - 「评价一下场景库」→ run_evaluation(field_names=["场景库"])
    - 「用原创性 grader 评价场景库」→ run_evaluation(field_names=["场景库"], grader_name="原创性")
    - 「评估所有内涵设计的内容」→ run_evaluation(field_names=["主题表达", "价值主张", ...])

    参数：
    - field_names: 要评估的内容块名称列表。为空时评估全部有内容的内容块。
    - grader_name: 指定使用的评估维度/Grader 名称。为空时使用全部评估维度。
    """
    return await _run_evaluation_impl(field_names or [], grader_name, config)


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

    典型场景：
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

    典型场景：
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

    当你需要更多上下文来理解创作者之前的讨论时使用。
    例如：创作者说"按之前和审稿人讨论的来"，你可以查阅审稿人模式的对话。

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
    modify_field,
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
PRODUCE_TOOLS = {
    "modify_field",
    "generate_field_content",
    "update_field",
}
