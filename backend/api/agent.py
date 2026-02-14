# backend/api/agent.py
# 功能: Agent 对话 API，支持 SSE 流式输出、对话历史、编辑重发、多模式切换
# 主要路由: /stream, /chat, /history, /retry, /advance
# 架构: stream_chat 使用 LangGraph astream_events，所有模式统一走 Agent Graph
# 日志: GenerationLog 由 GenerationLogCallback 自动记录（不在此文件手动创建）

"""
Agent 对话 API

核心改动（LangGraph 迁移）：
- /stream → agent_graph.astream_events(version="v2")
- 取消 route_intent + if/elif 手动分发
- 所有路由由 LLM Tool Calling 自动决定
- SSE 事件从 LangGraph 事件流映射
"""

import json
import asyncio
import logging
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Project, ChatMessage,
    ContentVersion, AgentMode, generate_uuid,
)
from core.models.content_block import ContentBlock
from core.orchestrator import get_agent_graph
from core.agent_tools import PRODUCE_TOOLS

router = APIRouter()
logger = logging.getLogger("agent")


# ============== Helpers ==============

async def _extract_and_save_memories(
    project_id: str, mode: str, phase: str, messages: list[dict],
):
    """后台异步任务：从对话中提炼记忆并保存（M2 Memory System）"""
    try:
        from core.memory_service import extract_memories, save_memories
        extracted = await extract_memories(project_id, mode, phase, messages)
        if extracted:
            saved = await save_memories(project_id, mode, phase, extracted)
            if saved:
                logger.info("[memory] 提炼并保存了 %d 条记忆 (project=%s)", saved, project_id)
    except Exception as e:
        logger.warning("[memory] 记忆提炼后台任务失败: %s", e)


def _save_version_before_overwrite(
    db: Session, entity_id: str, old_content: str,
    source: str, source_detail: str = None,
):
    """Agent 覆写前保存旧内容为版本 — 代理到 version_service"""
    from core.version_service import save_content_version
    save_content_version(db, entity_id, old_content, source, source_detail)


def _resolve_references(
    db: Session, project_id: str, references: list[str],
) -> dict[str, str]:
    """统一的 @ 引用解析：ContentBlock → 方案JSON

    返回 {name: 完整上下文文本}，包含内容和配置信息（ai_prompt等），
    确保 Agent 能充分了解引用块的全貌。
    P0-1: 统一使用 ContentBlock，已移除 ProjectField 查询。
    """
    if not references:
        return {}

    result = {}

    # 1. ContentBlock
    ref_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name.in_(references),
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    for b in ref_blocks:
        result[b.name] = _build_ref_context(b)

    # 2. 方案引用（从 design_inner 阶段块中解析 JSON proposals）
    import re
    proposal_refs = [r for r in references if r not in result and r.startswith("方案")]
    if proposal_refs:
        design_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.special_handler == "design_inner",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        # 也尝试按名称查找
        if not design_block:
            design_block = db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.name.in_(["内涵设计", "design_inner"]),
                ContentBlock.deleted_at == None,  # noqa: E711
            ).first()
        if design_block and design_block.content:
            try:
                data = json.loads(design_block.content)
                proposals = data.get("proposals", [])
                if isinstance(proposals, list):
                    for ref_name in proposal_refs:
                        match = re.match(r"方案(\d+)[:：]?(.*)", ref_name)
                        if match:
                            idx = int(match.group(1)) - 1
                            if 0 <= idx < len(proposals):
                                result[ref_name] = json.dumps(
                                    proposals[idx], ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass

    return result


def _build_ref_context(entity) -> str:
    """将内容块/字段构建为 Agent 可理解的完整上下文。

    包含内容正文、AI 提示词和状态信息，确保即使内容为空时
    Agent 也能了解该块的配置和用途。
    """
    parts = []
    content = getattr(entity, "content", "") or ""
    ai_prompt = getattr(entity, "ai_prompt", "") or ""
    status = getattr(entity, "status", "") or ""

    if content.strip():
        parts.append(content)
    else:
        parts.append("（此内容块尚无正文内容）")

    if ai_prompt.strip():
        # 截取 AI 提示词的前 1000 字，避免过长
        parts.append(f"\n[该内容块的 AI 提示词配置]\n{ai_prompt[:1000]}")

    if status:
        parts.append(f"\n[状态: {status}]")

    return "\n".join(parts)


# _load_seed_history 已删除 — Checkpointer 改为 SqliteSaver 持久化后不再需要
# 服务重启后 LangGraph 自动从 data/agent_checkpoints.db 恢复完整对话状态


def sse_event(data: dict) -> str:
    """格式化 SSE 事件"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# _get_phase_field_name 已删除 — 阶段名称映射统一到 core/phase_service.PHASE_DISPLAY_NAMES


def _to_message_response(m: ChatMessage):
    return ChatMessageResponse(
        id=m.id,
        role=m.role,
        content=m.content,
        original_content=m.original_content or "",
        is_edited=m.is_edited or False,
        metadata=m.message_metadata or {},
        created_at=m.created_at.isoformat() if m.created_at else "",
    )


# ============== Schemas ==============

class ChatRequest(BaseModel):
    """对话请求"""
    project_id: str
    message: str
    current_phase: Optional[str] = None
    references: List[str] = []
    mode: str = "assistant"  # 模式名：assistant / strategist / critic / reader / creative / 自定义


class FieldUpdatedInfo(BaseModel):
    id: str
    name: str
    phase: str
    action: Optional[str] = None


class ChatResponseSchema(BaseModel):
    message_id: str
    message: str
    phase: str
    phase_status: Dict[str, str]
    waiting_for_human: bool
    field_updated: Optional[FieldUpdatedInfo] = None


class MessageUpdate(BaseModel):
    content: str


class ToolCallRequest(BaseModel):
    project_id: str
    tool_name: str
    parameters: dict = {}


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    original_content: str
    is_edited: bool
    metadata: dict
    created_at: str
    model_config = {"from_attributes": True}


class ChatResponseExtended(BaseModel):
    message_id: str
    message: str
    phase: str
    phase_status: Dict[str, str]
    waiting_for_human: bool
    field_updated: Optional[dict] = None
    project_updated: bool = False
    is_producing: bool = False


# ============== Routes ==============

@router.get("/history/{project_id}", response_model=List[ChatMessageResponse])
def get_chat_history(
    project_id: str,
    limit: int = 100,
    mode: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取项目的对话历史（可按 mode 过滤）"""
    query = db.query(ChatMessage).filter(ChatMessage.project_id == project_id)

    if mode:
        # message_metadata 是 JSON 字段，用 json_extract 按 mode 过滤（SQLite 兼容）
        from sqlalchemy import func, or_
        mode_expr = func.json_extract(ChatMessage.message_metadata, "$.mode")
        if mode == "assistant":
            # 向后兼容：M1 之前的旧消息没有 mode 字段，归属到 assistant
            query = query.filter(
                or_(mode_expr == mode, mode_expr.is_(None))
            )
        else:
            query = query.filter(mode_expr == mode)

    messages = (
        query.order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [_to_message_response(m) for m in messages]


@router.post("/chat", response_model=ChatResponseExtended, deprecated=True)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    ⚠️ DEPRECATED: 请使用 /stream (SSE) 端点。
    非流式对话。前端已不再调用此端点。
    P3-1: 已改为直接使用 agent_graph.ainvoke()。
    """
    from langchain_core.messages import HumanMessage, AIMessage

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = request.current_phase or project.current_phase

    # 查 AgentMode
    mode_name = request.mode or "assistant"
    mode_obj = db.query(AgentMode).filter(AgentMode.name == mode_name).first()
    mode_prompt = mode_obj.system_prompt if mode_obj else ""

    # 保存用户消息
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_metadata={"phase": current_phase, "mode": mode_name, "references": request.references},
    )
    db.add(user_msg)
    db.commit()

    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()

    try:
        # M2+M3: 加载项目记忆
        from core.memory_service import load_memory_context_async
        memory_ctx = await load_memory_context_async(request.project_id, mode_name, current_phase)

        state = {
            "messages": [HumanMessage(content=request.message)],
            "project_id": request.project_id,
            "current_phase": current_phase,
            "creator_profile": creator_profile_str,
            "mode": mode_name,
            "mode_prompt": mode_prompt,
            "memory_context": memory_ctx,
        }
        config = {
            "configurable": {
                "thread_id": f"{request.project_id}:{mode_name}",
                "project_id": request.project_id,
            }
        }
        _graph = await get_agent_graph()
        result = await asyncio.wait_for(
            _graph.ainvoke(state, config=config),
            timeout=300,
        )
    except asyncio.TimeoutError:
        error_msg = ChatMessage(
            id=generate_uuid(), project_id=request.project_id,
            role="assistant", content="⚠️ 处理超时，请稍后重试。",
            message_metadata={"phase": current_phase, "mode": mode_name, "error": "timeout"},
        )
        db.add(error_msg)
        db.commit()
        return JSONResponse(status_code=504, content={"detail": "Agent 处理超时"})
    except Exception as agent_err:
        error_msg = ChatMessage(
            id=generate_uuid(), project_id=request.project_id,
            role="assistant", content=f"⚠️ 处理失败: {str(agent_err)[:200]}",
            message_metadata={"phase": current_phase, "mode": mode_name, "error": str(agent_err)[:200]},
        )
        db.add(error_msg)
        db.commit()
        return JSONResponse(status_code=500, content={"detail": str(agent_err)[:200]})

    # 提取最后一条 AI 消息
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    last_ai = ai_messages[-1] if ai_messages else None
    agent_output = last_ai.content if last_ai else ""

    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=agent_output,
        message_metadata={"phase": current_phase, "mode": mode_name},
    )
    db.add(agent_msg)
    db.commit()

    return ChatResponseExtended(
        message_id=agent_msg.id,
        message=agent_output,
        phase=current_phase,
        phase_status=project.phase_status or {},
        waiting_for_human=False,
    )


@router.put("/message/{message_id}", response_model=ChatMessageResponse)
async def edit_message(
    message_id: str,
    update: MessageUpdate,
    db: Session = Depends(get_db),
):
    """编辑消息（用于编辑重发）"""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.role != "user":
        raise HTTPException(status_code=400, detail="Only user messages can be edited")
    if not msg.is_edited:
        msg.original_content = msg.content
    msg.content = update.content
    msg.is_edited = True
    db.commit()
    db.refresh(msg)
    return _to_message_response(msg)


@router.post("/retry/{message_id}", response_model=ChatResponseSchema)
async def retry_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    """重新生成 Assistant 响应"""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.role == "assistant":
        user_msg = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.project_id == msg.project_id,
                ChatMessage.role == "user",
                ChatMessage.created_at < msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if not user_msg:
            raise HTTPException(status_code=400, detail="No user message found to retry")
    else:
        user_msg = msg

    project = db.query(Project).filter(Project.id == user_msg.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()

    current_phase = (
        user_msg.message_metadata.get("phase", project.current_phase)
        if user_msg.message_metadata
        else project.current_phase
    )

    # 从原消息 metadata 中提取 mode，回退到 assistant
    mode_name = (
        (msg.message_metadata or {}).get("mode")
        or (user_msg.message_metadata or {}).get("mode")
        or "assistant"
    )

    # 查 AgentMode 获取 mode_prompt
    mode_obj = db.query(AgentMode).filter(AgentMode.name == mode_name).first()
    mode_prompt = mode_obj.system_prompt if mode_obj else ""

    from langchain_core.messages import HumanMessage, AIMessage

    # M2+M3: 加载项目记忆
    from core.memory_service import load_memory_context_async
    memory_ctx = await load_memory_context_async(user_msg.project_id, mode_name, current_phase)

    state = {
        "messages": [HumanMessage(content=user_msg.content)],
        "project_id": user_msg.project_id,
        "current_phase": current_phase,
        "creator_profile": creator_profile_str,
        "mode": mode_name,
        "mode_prompt": mode_prompt,
        "memory_context": memory_ctx,
    }
    config = {
        "configurable": {
            "thread_id": f"{user_msg.project_id}:{mode_name}",
            "project_id": user_msg.project_id,
        }
    }
    _graph = await get_agent_graph()
    result = await _graph.ainvoke(state, config=config)

    # 提取最后一条 AI 消息
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    last_ai = ai_messages[-1] if ai_messages else None
    agent_output = last_ai.content if last_ai else ""

    new_msg = ChatMessage(
        id=generate_uuid(),
        project_id=user_msg.project_id,
        role="assistant",
        content=agent_output,
        parent_message_id=message_id,
        message_metadata={
            "phase": current_phase,
            "mode": mode_name,
            "is_retry": True,
        },
    )
    db.add(new_msg)
    db.commit()

    return ChatResponseSchema(
        message_id=new_msg.id,
        message=agent_output,
        phase=current_phase,
        phase_status=project.phase_status or {},
        waiting_for_human=False,
    )


@router.post("/tool", response_model=ChatResponseSchema)
async def call_tool(
    request: ToolCallRequest,
    db: Session = Depends(get_db),
):
    """直接调用 Agent 工具（保留向后兼容）"""
    from core.agent_tools import AGENT_TOOLS

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 查找工具
    tool_map = {t.name: t for t in AGENT_TOOLS}
    tool_fn = tool_map.get(request.tool_name)
    if not tool_fn:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tool: {request.tool_name}. Available: {list(tool_map.keys())}",
        )

    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=f"调用工具: {request.tool_name}",
        message_metadata={
            "phase": project.current_phase,
            "mode": "assistant",  # /tool 端点默认归入 assistant 模式
            "tool_called": request.tool_name,
            "parameters": request.parameters,
        },
    )
    db.add(user_msg)

    try:
        # ainvoke 统一处理 sync/async 工具
        config = {"configurable": {"project_id": request.project_id}}
        output = await tool_fn.ainvoke(
            {**request.parameters}, config=config
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        output = f"工具执行失败: {str(e)}"

    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=str(output),
        message_metadata={
            "phase": project.current_phase,
            "mode": "assistant",  # /tool 端点默认归入 assistant 模式
            "tools_used": [request.tool_name],
        },
    )
    db.add(agent_msg)
    db.commit()

    return ChatResponseSchema(
        message_id=agent_msg.id,
        message=str(output),
        phase=project.current_phase,
        phase_status=project.phase_status or {},
        waiting_for_human=False,
    )


@router.delete("/message/{message_id}")
def delete_message(message_id: str, db: Session = Depends(get_db)):
    """删除消息"""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
    return {"message": "Deleted"}


# ============== SSE Stream Endpoint ==============

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    与 Agent 对话（SSE 流式输出）。

    架构（LangGraph 迁移版）：
    1. 保存用户消息 → yield user_saved
    2. 构建 AgentState + Checkpointer Bootstrap
    3. agent_graph.astream_events(version="v2") 遍历事件流
    4. 根据事件类型 yield SSE：token / tool_start / tool_end / done / error
    5. 保存 assistant 最终回复到 ChatMessage DB
    """
    from langchain_core.messages import HumanMessage, AIMessage

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = request.current_phase or project.current_phase

    # ---- 查 AgentMode（提前到保存用户消息之前，确保 mode_name 统一） ----
    mode_name = request.mode or "assistant"
    mode_obj = db.query(AgentMode).filter(AgentMode.name == mode_name).first()
    mode_prompt = mode_obj.system_prompt if mode_obj else ""

    # ---- 保存用户消息 ----
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_metadata={
            "phase": current_phase,
            "references": request.references,
            "mode": mode_name,
        },
    )
    db.add(user_msg)
    db.commit()
    saved_user_msg_id = user_msg.id

    # ---- 所有模式统一走 Agent Graph（已删除共创分流） ----

    # 处理 @ 引用：将引用内容追加到用户消息
    augmented_message = request.message
    if request.references:
        ref_contents = _resolve_references(db, request.project_id, request.references)
        if ref_contents:
            ref_text = "\n".join(
                f"【{name}】\n{content[:2000]}" for name, content in ref_contents.items()
            )
            augmented_message = (
                f"{request.message}\n\n---\n以下是用户引用的内容块：\n{ref_text}"
            )

    # Checkpointer 配置 + LLM 日志回调
    from core.llm_logger import GenerationLogCallback

    thread_id = f"{request.project_id}:{mode_name}"
    llm_log_cb = GenerationLogCallback(
        project_id=request.project_id,
        phase=current_phase,
        operation="agent_stream",
    )
    config = {
        "configurable": {
            "thread_id": thread_id,
            "project_id": request.project_id,
        },
        "callbacks": [llm_log_cb],
    }

    # SqliteSaver 持久化后不再需要 Bootstrap — checkpoint 跨重启自动恢复
    input_messages = [HumanMessage(content=augmented_message)]

    # 构建 AgentState
    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()

    # M2+M3: 加载项目记忆（超阈值时 LLM 预筛选）
    from core.memory_service import load_memory_context_async
    memory_ctx = await load_memory_context_async(request.project_id, mode_name, current_phase)

    input_state = {
        "messages": input_messages,
        "project_id": request.project_id,
        "current_phase": current_phase,
        "creator_profile": creator_profile_str,
        "mode": mode_name,
        "mode_prompt": mode_prompt,
        "memory_context": memory_ctx,
    }

    # ---- 产出类工具集（执行后前端需刷新左侧面板） ----
    produce_tools = PRODUCE_TOOLS | {
        "manage_architecture", "advance_to_phase", "execute_prompt_update",
        "run_research",
    }

    async def event_generator():
        try:
            # 1. 返回用户消息真实 ID
            yield sse_event({"type": "user_saved", "message_id": saved_user_msg_id})

            full_content = ""           # agent 节点的 LLM 输出（显示在聊天气泡）
            current_tool = None
            tools_used = []
            is_producing = False
            first_tool_sent = False     # 用于向前端发 route 事件（兼容）
            tool_chars = 0              # 工具内 LLM 输出的字符数（用于进度显示）
            event_count = 0             # 事件计数（调试用）

            logger.info("[stream] 开始 astream_events, project=%s, phase=%s",
                        request.project_id, current_phase)

            _graph = await get_agent_graph()
            async for event in _graph.astream_events(
                input_state, config=config, version="v2"
            ):
                kind = event["event"]
                event_count += 1

                # ---- Token 级流式 ----
                if kind == "on_chat_model_stream":
                    metadata = event.get("metadata", {})
                    langgraph_node = metadata.get("langgraph_node", "")
                    chunk = event["data"].get("chunk")

                    if not chunk or not hasattr(chunk, "content"):
                        continue

                    content_piece = chunk.content
                    if not content_piece:
                        continue

                    if langgraph_node == "agent":
                        # Agent 节点的 LLM 输出 → 流式发给前端聊天气泡
                        full_content += content_piece
                        yield sse_event({
                            "type": "token",
                            "content": content_piece,
                        })
                    elif current_tool:
                        # 工具内部 LLM 输出 → 发送进度事件
                        tool_chars += len(content_piece)
                        # 每 200 字发一次进度（避免事件过多）
                        if tool_chars % 200 < len(content_piece) or tool_chars < 50:
                            yield sse_event({
                                "type": "tool_progress",
                                "tool": current_tool,
                                "chars": tool_chars,
                            })
                    else:
                        # 未知来源（防御性）：仍然作为 token 发送
                        full_content += content_piece
                        yield sse_event({
                            "type": "token",
                            "content": content_piece,
                        })

                # ---- 工具开始 ----
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    current_tool = tool_name
                    tool_chars = 0  # 重置工具字符计数
                    tools_used.append(tool_name)
                    logger.info("[stream] tool_start: %s", tool_name)

                    # 向前端发送 route 事件（兼容旧前端）
                    if not first_tool_sent:
                        route_map = {
                            "run_research": "research",
                            "modify_field": "modify",
                            "generate_field_content": "generate_field",
                            "query_field": "query",
                            "run_evaluation": "evaluate",
                            "advance_to_phase": "advance_phase",
                            "manage_architecture": "generate_field",
                            "generate_outline": "generate_field",
                        }
                        route_name = route_map.get(tool_name, tool_name)
                        yield sse_event({
                            "type": "route",
                            "target": route_name,
                        })
                        first_tool_sent = True

                    yield sse_event({
                        "type": "tool_start",
                        "tool": tool_name,
                    })

                # ---- 工具结束 ----
                elif kind == "on_tool_end":
                    tool_output = event["data"].get("output", "")
                    if isinstance(tool_output, str):
                        output_str = tool_output
                    else:
                        output_str = str(tool_output)

                    field_updated = current_tool in produce_tools
                    if field_updated:
                        is_producing = True

                    logger.info("[stream] tool_end: %s, output=%d chars, field_updated=%s",
                                current_tool, len(output_str), field_updated)

                    # modify_field 特殊处理：解析 JSON 输出
                    if current_tool == "modify_field":
                        try:
                            result = json.loads(output_str)
                            if result.get("status") == "need_confirm":
                                yield sse_event({
                                    "type": "modify_confirm_needed",
                                    "target_field": result.get("target_field"),
                                    "edits": result.get("edits"),
                                    "summary": result.get("summary"),
                                })
                            elif result.get("status") == "applied":
                                yield sse_event({
                                    "type": "tool_end",
                                    "tool": current_tool,
                                    "output": result.get("summary", ""),
                                    "field_updated": True,
                                })
                            else:
                                yield sse_event({
                                    "type": "tool_end",
                                    "tool": current_tool,
                                    "output": result.get("summary", output_str[:500]),
                                    "field_updated": field_updated,
                                })
                        except (json.JSONDecodeError, TypeError):
                            yield sse_event({
                                "type": "tool_end",
                                "tool": current_tool,
                                "output": output_str[:500],
                                "field_updated": field_updated,
                            })
                    else:
                        yield sse_event({
                            "type": "tool_end",
                            "tool": current_tool,
                            "output": output_str[:500],
                            "field_updated": field_updated,
                        })

                    current_tool = None

            # ---- 图执行完毕 ----
            logger.info("[stream] 图执行完毕, events=%d, full_content=%d chars, tools=%s",
                        event_count, len(full_content), tools_used)

            # 如果没有从 on_chat_model_stream 收到任何 token（回退机制）：
            # 从最终 state 中提取 AI 消息内容
            if not full_content:
                try:
                    final_state = await _graph.aget_state(config)
                    if final_state and final_state.values:
                        msgs = final_state.values.get("messages", [])
                        # 取最后一条 AIMessage（非 ToolMessage）
                        for m in reversed(msgs):
                            if isinstance(m, AIMessage) and not m.tool_calls and m.content:
                                full_content = m.content
                                logger.warning(
                                    "[stream] 回退：从 state 中提取 AI 内容, %d chars",
                                    len(full_content),
                                )
                                # 一次性发送给前端
                                yield sse_event({
                                    "type": "token",
                                    "content": full_content,
                                })
                                break
                except Exception as fallback_err:
                    logger.warning("[stream] 回退提取失败: %s", fallback_err)

            # 保存 assistant 最终回复到 ChatMessage DB
            agent_msg = ChatMessage(
                id=generate_uuid(),
                project_id=request.project_id,
                role="assistant",
                content=full_content,
                message_metadata={
                    "phase": current_phase,
                    "mode": mode_name,
                    "tools_used": tools_used,
                },
            )
            db.add(agent_msg)

            # GenerationLog 由 GenerationLogCallback 自动记录（完整 messages + 不截断）
            # 不再手动创建重复日志

            db.commit()

            yield sse_event({
                "type": "done",
                "message_id": agent_msg.id,
                "is_producing": is_producing,
                "route": tools_used[0] if tools_used else "chat",
            })

            # M2: 异步触发记忆提炼（不阻塞 SSE 流）
            try:
                from core.memory_service import extract_memories, save_memories
                _conv = [
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": full_content},
                ]
                asyncio.create_task(_extract_and_save_memories(
                    request.project_id, mode_name, current_phase, _conv,
                ))
            except Exception as mem_err:
                logger.debug("[stream] 记忆提炼触发失败(可忽略): %s", mem_err)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error("[stream] EXCEPTION: %s\n%s", e, tb)
            yield sse_event({
                "type": "error",
                "error": str(e),
                "traceback": tb[:500],
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# _handle_cocreation_stream 已删除 — 所有模式统一走 Agent Graph


# ============== Advance Phase ==============

@router.post("/advance")
async def advance_phase(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """推进到下一阶段（用户点击确认按钮后调用）"""
    from core.phase_service import advance_phase as do_advance

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = do_advance(project)
    if not result.success:
        return ChatResponseExtended(
            message_id="", message=result.error,
            phase=project.current_phase, phase_status=project.phase_status or {},
            waiting_for_human=False,
        )

    db.commit()

    msg_content = f"✅ 已进入【{result.display_name}】阶段。"

    enter_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=msg_content,
        message_metadata={
            "phase": result.next_phase,
            "mode": request.mode or "assistant",
        },
    )
    db.add(enter_msg)
    db.commit()
    db.refresh(project)

    return ChatResponseExtended(
        message_id=enter_msg.id,
        message=msg_content,
        phase=result.next_phase,
        phase_status=project.phase_status or {},
        waiting_for_human=False,
        project_updated=True,
        is_producing=False,
    )
