# backend/api/agent.py
# 功能: Agent对话API，支持SSE流式输出、对话历史、编辑重发、Tool调用
# 主要路由: /chat, /stream, /history, /retry, /tool
# 数据结构: ChatRequest, ChatResponse, ChatMessage

"""
Agent 对话 API
支持普通响应和SSE流式输出
支持对话历史持久化、编辑重发、再试一次
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField, ChatMessage, GenerationLog, generate_uuid
from core.orchestrator import content_agent


router = APIRouter()


# ============== Schemas ==============

class ChatRequest(BaseModel):
    """对话请求"""
    project_id: str
    message: str
    current_phase: Optional[str] = None
    references: list[str] = []  # @引用的字段名列表


class ChatResponse(BaseModel):
    """对话响应"""
    message_id: str
    message: str
    phase: str
    phase_status: dict[str, str]
    waiting_for_human: bool


class MessageUpdate(BaseModel):
    """消息编辑"""
    content: str


class ToolCallRequest(BaseModel):
    """Tool调用请求"""
    project_id: str
    tool_name: str
    parameters: dict = {}


class ChatMessageResponse(BaseModel):
    """对话消息响应"""
    id: str
    role: str
    content: str
    original_content: str
    is_edited: bool
    metadata: dict
    created_at: str

    model_config = {"from_attributes": True}


# ============== Routes ==============

@router.get("/history/{project_id}", response_model=list[ChatMessageResponse])
def get_chat_history(
    project_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    获取项目的对话历史
    """
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [_to_message_response(m) for m in messages]


class ChatResponseExtended(BaseModel):
    """扩展的对话响应 - 包含字段更新"""
    message_id: str
    message: str
    phase: str
    phase_status: dict[str, str]
    waiting_for_human: bool
    field_updated: Optional[dict] = None  # 如果生成了字段内容
    project_updated: bool = False
    is_producing: bool = False  # 是否是产出模式（用于前端判断是否刷新中间栏）


@router.post("/chat", response_model=ChatResponseExtended)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    与Agent对话（非流式）
    
    核心改进：
    1. Agent输出自动保存为对应阶段的字段
    2. 自动记录GenerationLog
    3. 更新项目进度状态
    """
    from core.ai_client import ai_client
    
    # 获取项目
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_phase = request.current_phase or project.current_phase
    
    # 加载历史对话（在保存新消息之前）
    history_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == request.project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(50)  # 最近50条
        .all()
    )
    chat_history = [{"role": m.role, "content": m.content} for m in history_messages]
    
    # 保存用户消息
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_metadata={
            "phase": current_phase,
            "references": request.references,
        },
    )
    db.add(user_msg)
    db.commit()
    
    # 运行Agent（传递历史对话）
    result = await content_agent.run(
        project_id=request.project_id,
        user_input=request.message,
        current_phase=current_phase,
        golden_context=project.golden_context or {},
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
        chat_history=chat_history,  # 传递历史对话
    )
    
    agent_output = result.get("agent_output", "")
    result_phase = result.get("current_phase", current_phase)
    is_producing = result.get("is_producing", False)
    
    # ===== 核心逻辑：只有产出模式才保存为 ProjectField =====
    # 意图分析阶段：提问模式(is_producing=False)只显示在对话区
    #              产出模式(is_producing=True)才保存为字段显示在中间栏
    # 其他阶段：直接保存为字段（is_producing 默认 True）
    
    # 非意图阶段默认都是产出模式
    if result_phase != "intent":
        is_producing = True
    
    field_updated = None
    if agent_output and result_phase and is_producing:
        # 查找或创建该阶段的字段
        existing_field = (
            db.query(ProjectField)
            .filter(
                ProjectField.project_id == request.project_id,
                ProjectField.phase == result_phase,
                ProjectField.name == _get_phase_field_name(result_phase),
            )
            .first()
        )
        
        if existing_field:
            # 更新现有字段
            existing_field.content = agent_output
            existing_field.status = "completed"
            field_updated = {"id": existing_field.id, "name": existing_field.name, "phase": result_phase}
        else:
            # 创建新字段
            new_field = ProjectField(
                id=generate_uuid(),
                project_id=request.project_id,
                name=_get_phase_field_name(result_phase),
                phase=result_phase,
                content=agent_output,
                field_type="richtext",
                status="completed",
            )
            db.add(new_field)
            field_updated = {"id": new_field.id, "name": new_field.name, "phase": result_phase}
    
    # ===== 记录GenerationLog =====
    log_entry = GenerationLog(
        id=generate_uuid(),
        project_id=request.project_id,
        phase=result_phase,
        operation=f"agent_chat_{result_phase}",
        model=ai_client.model,
        prompt_input=request.message,
        prompt_output=agent_output,
        tokens_in=0,  # TODO: 从result获取实际token数
        tokens_out=0,
        duration_ms=0,
        cost=0.0,
        status="success",
    )
    db.add(log_entry)
    
    # 保存Agent响应到对话历史
    # 核心规则：产出模式下，聊天区只显示简短确认，完整内容在中间工作台
    if is_producing and field_updated:
        # 产出模式：聊天区显示简短确认
        phase_names = {
            "intent": "意图分析",
            "research": "消费者调研", 
            "design_inner": "内涵设计",
            "produce_inner": "内涵生产",
            "design_outer": "外延设计",
            "produce_outer": "外延生产",
            "simulate": "消费者模拟",
            "evaluate": "评估报告",
        }
        phase_name = phase_names.get(result_phase, result_phase)
        chat_content = f"✅ 已生成【{phase_name}】，请在左侧工作台查看和编辑。"
    else:
        # 对话模式：显示完整内容
        chat_content = agent_output
    
    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=chat_content,
        message_metadata={
            "phase": result_phase,
            "tool_used": result.get("tool_used"),
            "waiting_for_human": result.get("waiting_for_human", False),
            "field_id": field_updated.get("id") if field_updated else None,
            "is_producing": is_producing,  # 标记便于前端判断
        },
    )
    db.add(agent_msg)
    
    # 更新项目状态
    project_updated = False
    new_phase_status = result.get("phase_status", project.phase_status or {})
    
    # 确保当前阶段标记为进行中或已完成
    if result_phase and agent_output:
        new_phase_status[result_phase] = "in_progress"
        project_updated = True
    
    if new_phase_status != project.phase_status:
        project.phase_status = new_phase_status
        project_updated = True
    
    # 更新Golden Context
    if result.get("golden_context"):
        project.golden_context = result["golden_context"]
        project_updated = True
    
    # 更新当前阶段
    if result_phase != project.current_phase:
        project.current_phase = result_phase
        project_updated = True
    
    db.commit()
    
    return ChatResponseExtended(
        message_id=agent_msg.id,
        message=chat_content,  # 聊天区显示的内容（产出模式为简短确认）
        phase=result_phase,
        phase_status=new_phase_status,
        waiting_for_human=result.get("waiting_for_human", False),
        field_updated=field_updated,
        project_updated=project_updated,
        is_producing=is_producing,
    )


def _get_phase_field_name(phase: str) -> str:
    """获取阶段对应的默认字段名"""
    names = {
        "intent": "项目意图",
        "research": "消费者调研报告",
        "design_inner": "内涵设计方案",
        "produce_inner": "内涵生产内容",
        "design_outer": "外延设计方案",
        "produce_outer": "外延生产内容",
        "simulate": "消费者模拟结果",
        "evaluate": "项目评估报告",
    }
    return names.get(phase, f"{phase}_output")


@router.put("/message/{message_id}", response_model=ChatMessageResponse)
async def edit_message(
    message_id: str,
    update: MessageUpdate,
    db: Session = Depends(get_db),
):
    """
    编辑消息（用于编辑重发）
    """
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if msg.role != "user":
        raise HTTPException(status_code=400, detail="Only user messages can be edited")
    
    # 保存原始内容
    if not msg.is_edited:
        msg.original_content = msg.content
    
    msg.content = update.content
    msg.is_edited = True
    
    db.commit()
    db.refresh(msg)
    
    return _to_message_response(msg)


@router.post("/retry/{message_id}", response_model=ChatResponse)
async def retry_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    """
    重新生成Assistant响应（再试一次）
    找到指定消息前的用户消息，重新生成回复
    """
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # 如果是assistant消息，找到对应的用户消息
    if msg.role == "assistant":
        # 查找该消息之前的最后一条用户消息
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
    
    # 获取项目
    project = db.query(Project).filter(Project.id == user_msg.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 重新运行Agent
    result = await content_agent.run(
        project_id=user_msg.project_id,
        user_input=user_msg.content,
        current_phase=user_msg.message_metadata.get("phase", project.current_phase),
        golden_context=project.golden_context or {},
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
    )
    
    # 创建新的响应（关联到原消息）
    new_msg = ChatMessage(
        id=generate_uuid(),
        project_id=user_msg.project_id,
        role="assistant",
        content=result.get("agent_output", ""),
        parent_message_id=message_id,
        message_metadata={
            "phase": result.get("current_phase", "intent"),
            "tool_used": result.get("tool_used"),
            "is_retry": True,
        },
    )
    db.add(new_msg)
    db.commit()
    
    return ChatResponse(
        message_id=new_msg.id,
        message=result.get("agent_output", ""),
        phase=result.get("current_phase", "intent"),
        phase_status=result.get("phase_status", {}),
        waiting_for_human=result.get("waiting_for_human", False),
    )


@router.post("/tool", response_model=ChatResponse)
async def call_tool(
    request: ToolCallRequest,
    db: Session = Depends(get_db),
):
    """
    直接调用Tool执行任务
    """
    from core.tools import deep_research, field_generator, simulator, evaluator
    
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 根据tool_name调用对应工具
    tool_map = {
        "deep_research": deep_research.deep_research_tool,
        "generate_field": field_generator.generate_field_tool,
        "simulate_consumer": simulator.simulate_consumer_tool,
        "evaluate_content": evaluator.evaluate_content_tool,
    }
    
    tool_func = tool_map.get(request.tool_name)
    if not tool_func:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}")
    
    # 保存Tool调用消息
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=f"调用工具: {request.tool_name}",
        message_metadata={
            "phase": project.current_phase,
            "tool_called": request.tool_name,
            "parameters": request.parameters,
        },
    )
    db.add(user_msg)
    
    try:
        # 执行Tool
        result = await tool_func(
            project_id=request.project_id,
            **request.parameters,
        )
        
        output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        output = f"工具执行失败: {str(e)}"
    
    # 保存结果
    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=output,
        message_metadata={
            "phase": project.current_phase,
            "tool_used": request.tool_name,
        },
    )
    db.add(agent_msg)
    db.commit()
    
    return ChatResponse(
        message_id=agent_msg.id,
        message=output,
        phase=project.current_phase,
        phase_status=project.phase_status or {},
        waiting_for_human=False,
    )


@router.delete("/message/{message_id}")
def delete_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    """删除消息"""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(msg)
    db.commit()
    return {"message": "Deleted"}


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    与Agent对话（SSE流式输出）
    """
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 先保存用户消息
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_message_metadata={
            "phase": request.current_phase or project.current_phase,
            "references": request.references,
        },
    )
    db.add(user_msg)
    db.commit()
    
    async def event_generator():
        """生成SSE事件"""
        full_content = ""
        
        try:
            async for event in content_agent.stream(
                project_id=request.project_id,
                user_input=request.message,
                current_phase=request.current_phase or project.current_phase,
                golden_context=project.golden_context or {},
                autonomy_settings=project.agent_autonomy or {},
                use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
            ):
                for node_name, node_output in event.items():
                    if isinstance(node_output, dict):
                        output = node_output.get("agent_output", "")
                        if output:
                            full_content += output
                            data = json.dumps({
                                "node": node_name,
                                "content": output,
                                "phase": node_output.get("current_phase", ""),
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
            
            # 保存完整响应
            agent_msg = ChatMessage(
                id=generate_uuid(),
                project_id=request.project_id,
                role="assistant",
                content=full_content,
                message_metadata={"phase": project.current_phase},
            )
            db.add(agent_msg)
            db.commit()
            
            yield f"data: {json.dumps({'done': True, 'message_id': agent_msg.id})}\n\n"
            
        except Exception as e:
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/advance")
async def advance_phase(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    推进到下一阶段
    """
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_idx = project.phase_order.index(project.current_phase)
    if current_idx >= len(project.phase_order) - 1:
        return {"message": "Already at final phase", "phase": project.current_phase}
    
    next_phase = project.phase_order[current_idx + 1]
    
    # 检查当前阶段是否需要人工确认
    needs_confirm = project.agent_autonomy.get(project.current_phase, True)
    if needs_confirm:
        # 需要确认，标记等待状态
        return ChatResponse(
            message_id="",
            message=f"阶段 {project.current_phase} 需要您确认后才能继续。请确认当前阶段内容后说'继续'。",
            phase=project.current_phase,
            phase_status=project.phase_status,
            waiting_for_human=True,
        )
    
    # 不需要确认，直接推进
    project.phase_status[project.current_phase] = "completed"
    project.current_phase = next_phase
    project.phase_status[next_phase] = "in_progress"
    
    db.commit()
    
    result = await content_agent.run(
        project_id=request.project_id,
        user_input=f"开始{next_phase}阶段",
        current_phase=next_phase,
        golden_context=project.golden_context or {},
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
    )
    
    return ChatResponse(
        message_id="",
        message=result.get("agent_output", ""),
        phase=next_phase,
        phase_status=project.phase_status,
        waiting_for_human=result.get("waiting_for_human", False),
    )


# ============== Helpers ==============

def _to_message_response(m: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=m.id,
        role=m.role,
        content=m.content,
        original_content=m.original_content or "",
        is_edited=m.is_edited or False,
        metadata=m.message_metadata or {},
        created_at=m.created_at.isoformat() if m.created_at else "",
    )
