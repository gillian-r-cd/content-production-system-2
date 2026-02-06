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
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField, ChatMessage, GenerationLog, generate_uuid
from core.models.content_block import ContentBlock
from core.orchestrator import content_agent


router = APIRouter()


# ============== Schemas ==============

class ChatRequest(BaseModel):
    """对话请求"""
    project_id: str
    message: str
    current_phase: Optional[str] = None
    references: List[str] = []  # @引用的字段名列表


class FieldUpdatedInfo(BaseModel):
    """字段更新信息"""
    id: str
    name: str
    phase: str
    action: Optional[str] = None  # "modified" | "created"


class ChatResponseSchema(BaseModel):
    """对话响应"""
    message_id: str
    message: str
    phase: str
    phase_status: Dict[str, str]
    waiting_for_human: bool
    field_updated: Optional[FieldUpdatedInfo] = None  # @ 引用修改后返回


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

@router.get("/history/{project_id}", response_model=List[ChatMessageResponse])
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
    phase_status: Dict[str, str]
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
    
    # 加载历史对话（只加载当前阶段的消息，避免混入之前阶段的内容）
    history_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == request.project_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    
    # 只保留当前阶段的消息（通过 metadata.phase 过滤）
    current_phase_messages = []
    for m in history_messages:
        msg_phase = None
        if m.message_metadata:
            msg_phase = m.message_metadata.get("phase")
        # 如果消息没有 phase 信息，或者是当前阶段的消息，则保留
        if msg_phase is None or msg_phase == current_phase:
            current_phase_messages.append(m)
    
    # 只取最近的20条当前阶段消息
    chat_history = [{"role": m.role, "content": m.content} for m in current_phase_messages[-20:]]
    
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
    
    # ===== @ 引用解析：查询引用字段的内容（同时搜索 ProjectField 和 ContentBlock）=====
    references = request.references or []
    referenced_contents = {}
    
    if references:
        # 1. 先查询 ProjectField（传统架构）
        referenced_fields = db.query(ProjectField).filter(
            ProjectField.project_id == request.project_id,
            ProjectField.name.in_(references)
        ).all()
        
        for field in referenced_fields:
            referenced_contents[field.name] = field.content or ""
        
        # 2. 对未找到的引用，继续搜索 ContentBlock（灵活架构）
        missing_refs = [r for r in references if r not in referenced_contents]
        if missing_refs:
            referenced_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == request.project_id,
                ContentBlock.name.in_(missing_refs),
                ContentBlock.deleted_at == None,
            ).all()
            
            for block in referenced_blocks:
                referenced_contents[block.name] = block.content or ""
        
        # 记录日志
        print(f"[Agent] @ 引用解析: {references} -> 找到 {len(referenced_contents)} 个字段/内容块")
    
    # 获取创作者特质（全局注入到每个 LLM 调用）
    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()
    
    # 运行Agent（传递历史对话、阶段状态、架构信息和引用内容）
    result = await content_agent.run(
        project_id=request.project_id,
        user_input=request.message,
        current_phase=current_phase,
        creator_profile=creator_profile_str,  # 重构：传递创作者特质而非 golden_context
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
        chat_history=chat_history,
        phase_status=project.phase_status or {},
        phase_order=project.phase_order,  # 传递项目实际的阶段顺序
        references=references,  # @ 引用的字段名
        referenced_contents=referenced_contents,  # 引用字段的内容
    )
    
    agent_output = result.get("agent_output", "")
    result_phase = result.get("current_phase", current_phase)
    is_producing = result.get("is_producing", False)
    
    # ===== 核心逻辑：只有产出模式才保存为 ProjectField =====
    # 意图分析阶段：提问模式(is_producing=False)只显示在对话区
    #              产出模式(is_producing=True)才保存为字段显示在中间栏
    
    field_updated = None
    fields_created = []
    
    # ===== 特殊处理：@ 引用字段修改（同时支持 ProjectField 和 ContentBlock）=====
    modify_target_field = result.get("modify_target_field")
    if modify_target_field and agent_output:
        # 1. 先查找 ProjectField
        target_field = db.query(ProjectField).filter(
            ProjectField.project_id == request.project_id,
            ProjectField.name == modify_target_field,
        ).first()
        
        if target_field:
            target_field.content = agent_output
            target_field.status = "completed"
            field_updated = {
                "id": target_field.id, 
                "name": target_field.name, 
                "phase": target_field.phase,
                "action": "modified"
            }
            print(f"[Agent] ProjectField 修改成功: {modify_target_field}")
        else:
            # 2. 查找 ContentBlock
            target_block = db.query(ContentBlock).filter(
                ContentBlock.project_id == request.project_id,
                ContentBlock.name == modify_target_field,
                ContentBlock.deleted_at == None,
            ).first()
            
            if target_block:
                target_block.content = agent_output
                target_block.status = "completed"
                field_updated = {
                    "id": target_block.id, 
                    "name": target_block.name, 
                    "phase": "",
                    "action": "modified"
                }
                print(f"[Agent] ContentBlock 修改成功: {modify_target_field}")
            else:
                print(f"[Agent] 字段修改失败: 未找到 {modify_target_field} (已搜索 ProjectField 和 ContentBlock)")
    
    elif agent_output and result_phase and is_producing:
        # ===== 意图分析阶段：解析JSON创建3个独立字段 =====
        if result_phase == "intent":
            try:
                # 提取JSON（可能包含```json...```包裹）
                import re
                json_match = re.search(r'```json\s*(.*?)\s*```', agent_output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = agent_output
                
                intent_data = json.loads(json_str)
                
                # 创建3个独立字段
                intent_fields = [
                    ("做什么", intent_data.get("做什么", "")),
                    ("给谁看", intent_data.get("给谁看", "")),
                    ("期望行动", intent_data.get("期望行动", "")),
                ]
                
                for field_name, field_content in intent_fields:
                    if not field_content:
                        continue
                    
                    # 查找或创建
                    existing = db.query(ProjectField).filter(
                        ProjectField.project_id == request.project_id,
                        ProjectField.phase == "intent",
                        ProjectField.name == field_name,
                    ).first()
                    
                    if existing:
                        existing.content = field_content
                        existing.status = "completed"
                        fields_created.append({"id": existing.id, "name": field_name})
                    else:
                        new_field = ProjectField(
                            id=generate_uuid(),
                            project_id=request.project_id,
                            name=field_name,
                            phase="intent",
                            content=field_content,
                            field_type="text",
                            status="completed",
                        )
                        db.add(new_field)
                        fields_created.append({"id": new_field.id, "name": field_name})
                
                field_updated = {"fields": fields_created, "phase": result_phase}
                
            except (json.JSONDecodeError, Exception) as e:
                # JSON解析失败，回退到保存原始内容
                print(f"Intent JSON parse error: {e}, saving raw content")
                new_field = ProjectField(
                    id=generate_uuid(),
                    project_id=request.project_id,
                    name="项目意图",
                    phase=result_phase,
                    content=agent_output,
                    field_type="richtext",
                    status="completed",
                )
                db.add(new_field)
                field_updated = {"id": new_field.id, "name": "项目意图", "phase": result_phase}
        else:
            # ===== 其他阶段：保存为单个字段 =====
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
                existing_field.content = agent_output
                existing_field.status = "completed"
                field_updated = {"id": existing_field.id, "name": existing_field.name, "phase": result_phase}
            else:
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
    
    # ===== 记录GenerationLog（使用 Agent 返回的完整 prompt 信息）=====
    # full_prompt 包含系统提示词和用户输入
    full_prompt = result.get("full_prompt", request.message)
    
    log_entry = GenerationLog(
        id=generate_uuid(),
        project_id=request.project_id,
        phase=result_phase,
        operation=f"agent_chat_{result_phase}",
        model=ai_client.model,
        prompt_input=full_prompt,  # 完整的 prompt（系统提示词 + 用户输入）
        prompt_output=agent_output,
        tokens_in=result.get("tokens_in", 0),
        tokens_out=result.get("tokens_out", 0),
        duration_ms=result.get("duration_ms", 0),
        cost=result.get("cost", 0.0),
        status="success",
    )
    db.add(log_entry)
    
    # 保存Agent响应到对话历史
    # 核心规则：产出模式下，聊天区只显示简短确认，完整内容在中间工作台
    
    # 优先使用 display_output（某些阶段如 design_inner 会单独提供对话区显示内容）
    display_output = result.get("display_output")
    
    if display_output:
        # 如果有专门的显示内容，直接使用
        chat_content = display_output
    elif is_producing and field_updated:
        # 产出模式：聊天区显示简短确认
        phase_names = {
            "intent": "意图分析",
            "research": "消费者调研报告", 
            "design_inner": "内涵设计方案",
            "produce_inner": "内涵生产内容",
            "design_outer": "外延设计方案",
            "produce_outer": "外延生产内容",
            "simulate": "消费者模拟",
            "evaluate": "评估报告",
        }
        phase_name = phase_names.get(result_phase, result_phase)
        chat_content = f"✅ 已生成【{phase_name}】，请在左侧工作台查看和编辑。"
    else:
        # 对话模式：显示完整内容
        chat_content = agent_output
    
    # 获取字段ID（兼容单字段和多字段模式）
    field_id = None
    if field_updated:
        if "id" in field_updated:
            field_id = field_updated["id"]
        elif "fields" in field_updated and len(field_updated["fields"]) > 0:
            field_id = field_updated["fields"][0]["id"]
    
    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=chat_content,
        message_metadata={
            "phase": result_phase,
            "tool_used": result.get("tool_used"),
            "waiting_for_human": result.get("waiting_for_human", False),
            "field_id": field_id,
            "is_producing": is_producing,  # 标记便于前端判断
        },
    )
    db.add(agent_msg)
    
    # 更新项目状态
    project_updated = False
    new_phase_status = result.get("phase_status", project.phase_status or {})
    
    # 使用 orchestrator 返回的 phase_status（已包含正确的完成/进行中状态）
    # 不再强制覆盖，尊重 orchestrator 的判断
    if new_phase_status != project.phase_status:
        project.phase_status = new_phase_status
        project_updated = True
    
    # 注意：不再更新 project.golden_context
    # 意图分析、消费者调研结果已保存到 ProjectField
    # 后续阶段通过字段依赖获取，而非全局 golden_context
    
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


@router.post("/retry/{message_id}", response_model=ChatResponseSchema)
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
    
    # 获取创作者特质
    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()
    
    # 重新运行Agent
    result = await content_agent.run(
        project_id=user_msg.project_id,
        user_input=user_msg.content,
        current_phase=user_msg.message_metadata.get("phase", project.current_phase),
        creator_profile=creator_profile_str,
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
        phase_status=project.phase_status or {},  # 传递现有阶段状态！
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
    
    return ChatResponseSchema(
        message_id=new_msg.id,
        message=result.get("agent_output", ""),
        phase=result.get("current_phase", "intent"),
        phase_status=result.get("phase_status", {}),
        waiting_for_human=result.get("waiting_for_human", False),
    )


@router.post("/tool", response_model=ChatResponseSchema)
async def call_tool(
    request: ToolCallRequest,
    db: Session = Depends(get_db),
):
    """
    直接调用Tool执行任务
    
    每个工具需要不同的参数和上下文，这里做统一适配。
    """
    from core.tools.deep_research import deep_research as deep_research_fn
    from core.tools.simulator import run_simulation as run_simulation_fn
    from core.tools.architecture_reader import get_intent_and_research, get_field_content
    
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    valid_tools = ["deep_research", "generate_field", "simulate_consumer", "evaluate_content"]
    if request.tool_name not in valid_tools:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}. Available: {valid_tools}")
    
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
        output = ""
        params = request.parameters or {}
        
        if request.tool_name == "deep_research":
            # deep_research(query, intent, max_sources) -> ResearchReport
            deps = get_intent_and_research(request.project_id, db)
            intent_str = deps.get("intent", "")
            query = params.get("query", f"项目调研: {project.name}")
            max_sources = params.get("max_sources", 10)
            
            result = await deep_research_fn(
                query=query,
                intent=intent_str or project.name,
                max_sources=max_sources,
            )
            output = json.dumps({
                "summary": result.summary if hasattr(result, 'summary') else str(result),
                "personas": [p.__dict__ if hasattr(p, '__dict__') else str(p) for p in (result.personas if hasattr(result, 'personas') else [])],
                "sources_count": len(result.sources) if hasattr(result, 'sources') else 0,
            }, ensure_ascii=False, default=str)
            
        elif request.tool_name == "generate_field":
            # 生成指定字段内容
            field_name = params.get("field_name")
            if not field_name:
                output = "错误: 需要提供 field_name 参数指定要生成的字段名称"
            else:
                # 查找字段（同时支持 ProjectField 和 ContentBlock）
                field_data = get_field_content(request.project_id, field_name, db)
                if not field_data:
                    # 列出可用字段
                    available = []
                    pf_list = db.query(ProjectField).filter(
                        ProjectField.project_id == request.project_id
                    ).all()
                    available.extend([f.name for f in pf_list])
                    cb_list = db.query(ContentBlock).filter(
                        ContentBlock.project_id == request.project_id,
                        ContentBlock.block_type == "field",
                        ContentBlock.deleted_at == None,
                    ).all()
                    available.extend([b.name for b in cb_list])
                    output = f"未找到字段 '{field_name}'。可用字段: {available}"
                else:
                    # 使用 blocks API 中的生成逻辑
                    from api.blocks import generate_block_content
                    from core.models.content_block import ContentBlock as CB
                    
                    # 检查是 ContentBlock 还是 ProjectField
                    block = db.query(CB).filter(
                        CB.id == field_data["id"],
                        CB.deleted_at == None,
                    ).first()
                    
                    if block:
                        result = await generate_block_content(block.id, db)
                        output = f"已生成字段 '{field_name}' 的内容。\n\n{result.get('content', '')[:500]}..."
                    else:
                        # ProjectField - 使用 fields API
                        from api.fields import generate_field_api
                        result = await generate_field_api(field_data["id"], db)
                        output = f"已生成字段 '{field_name}' 的内容。\n\n{result.get('content', '')[:500]}..."
            
        elif request.tool_name == "simulate_consumer":
            # 消费者模拟 - 使用 AI 模拟消费者体验
            from core.ai_client import AIClient, ChatMessage as AIChatMessage
            
            content = params.get("content", "")
            if not content:
                # 尝试从项目字段中获取内容
                all_content_parts = []
                if project.use_flexible_architecture:
                    blocks = db.query(ContentBlock).filter(
                        ContentBlock.project_id == request.project_id,
                        ContentBlock.block_type == "field",
                        ContentBlock.deleted_at == None,
                        ContentBlock.content != None,
                        ContentBlock.content != "",
                    ).all()
                    all_content_parts = [f"【{b.name}】\n{b.content}" for b in blocks]
                else:
                    fields = db.query(ProjectField).filter(
                        ProjectField.project_id == request.project_id,
                        ProjectField.content != None,
                        ProjectField.content != "",
                    ).all()
                    all_content_parts = [f"【{f.name}】\n{f.content}" for f in fields]
                content = "\n\n".join(all_content_parts) if all_content_parts else ""
            
            if not content:
                output = "项目中暂无已生成的内容，请先生成一些字段内容后再进行消费者模拟。"
            else:
                # 使用数据库中的模拟器（如果有），否则直接用 AI 模拟
                from core.models.simulator import Simulator as SimulatorModel
                sim = db.query(SimulatorModel).first()
                
                if sim:
                    persona = params.get("persona", {"name": "普通用户", "age": 25, "occupation": "白领"})
                    result = await run_simulation_fn(
                        simulator=sim,
                        content=content[:5000],
                        persona=persona,
                    )
                    output = json.dumps({
                        "feedback": result.feedback.__dict__ if hasattr(result.feedback, '__dict__') else str(result.feedback),
                        "success": result.success,
                    }, ensure_ascii=False, default=str)
                else:
                    # 无模拟器时，直接用 AI 做简易模拟
                    ai_client = AIClient()
                    sim_result = await ai_client.async_chat(
                        messages=[
                            AIChatMessage(role="system", content="你是一位典型的内容消费者。请从消费者的角度体验以下内容，给出真实的感受、建议和评分（1-10分）。包括：1）第一印象 2）内容吸引力 3）是否愿意继续阅读/观看 4）改进建议。"),
                            AIChatMessage(role="user", content=f"请体验以下内容：\n\n{content[:5000]}"),
                        ],
                        max_tokens=4096,
                    )
                    output = sim_result.content
            
        elif request.tool_name == "evaluate_content":
            # 内容评估 - 简单使用 AI 进行评估
            from core.ai_client import AIClient, ChatMessage as AIChatMessage
            
            # 收集所有已完成的内容
            all_content_parts = []
            if project.use_flexible_architecture:
                blocks = db.query(ContentBlock).filter(
                    ContentBlock.project_id == request.project_id,
                    ContentBlock.block_type == "field",
                    ContentBlock.deleted_at == None,
                    ContentBlock.status == "completed",
                ).all()
                all_content_parts = [f"【{b.name}】\n{b.content}" for b in blocks if b.content]
            else:
                fields = db.query(ProjectField).filter(
                    ProjectField.project_id == request.project_id,
                    ProjectField.status == "completed",
                ).all()
                all_content_parts = [f"【{f.name}】\n{f.content}" for f in fields if f.content]
            
            if not all_content_parts:
                output = "项目中暂无已完成的内容，请先生成一些字段内容后再进行评估。"
            else:
                content_text = "\n\n".join(all_content_parts)
                ai_client = AIClient()
                eval_result = await ai_client.async_chat(
                    messages=[
                        AIChatMessage(role="system", content="你是一个专业的内容评估专家。请对以下内容进行全面评估，包括：内容质量、逻辑连贯性、创意程度、目标受众匹配度。给出1-10分的评分和详细的改进建议。"),
                        AIChatMessage(role="user", content=f"请评估以下项目内容：\n\n{content_text[:8000]}"),
                    ],
                    max_tokens=4096,
                )
                output = eval_result.content
        
        if not output:
            output = f"工具 {request.tool_name} 执行完成，但没有返回结果。"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    
    return ChatResponseSchema(
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
    与Agent对话（真正的 token-by-token SSE流式输出）
    
    流程：
    1. 先执行意图路由（快速，非流式）
    2. 根据路由结果，流式生成内容
    """
    from core.ai_client import ai_client, ChatMessage as AIChatMessage
    from core.orchestrator import route_intent, ContentProductionState, PROJECT_PHASES
    from langchain_core.messages import HumanMessage, AIMessage
    
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_phase = request.current_phase or project.current_phase
    
    # 先保存用户消息
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
    
    # 获取对话历史
    history_msgs = db.query(ChatMessage).filter(
        ChatMessage.project_id == request.project_id
    ).order_by(ChatMessage.created_at).all()
    
    chat_history = []
    for m in history_msgs[-20:]:  # 最近 20 条
        if m.role == "user":
            chat_history.append(HumanMessage(content=m.content))
        else:
            chat_history.append(AIMessage(content=m.content))
    
    # ===== @ 引用解析（stream 端点同样需要）=====
    stream_references = request.references or []
    stream_referenced_contents = {}
    if stream_references:
        # 1. 先搜索 ProjectField
        ref_fields = db.query(ProjectField).filter(
            ProjectField.project_id == request.project_id,
            ProjectField.name.in_(stream_references)
        ).all()
        for f in ref_fields:
            stream_referenced_contents[f.name] = f.content or ""
        
        # 2. 搜索 ContentBlock（灵活架构）
        missing = [r for r in stream_references if r not in stream_referenced_contents]
        if missing:
            ref_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == request.project_id,
                ContentBlock.name.in_(missing),
                ContentBlock.deleted_at == None,
            ).all()
            for b in ref_blocks:
                stream_referenced_contents[b.name] = b.content or ""
        
        print(f"[Agent/stream] @ 引用解析: {stream_references} -> 找到 {len(stream_referenced_contents)} 个字段/内容块")
    
    async def event_generator():
        """生成 token-by-token SSE 事件"""
        full_content = ""
        
        try:
            # 获取创作者特质
            creator_profile_str = ""
            if project.creator_profile:
                creator_profile_str = project.creator_profile.to_prompt_context()
            
            # 1. 执行意图路由
            initial_state: ContentProductionState = {
                "project_id": request.project_id,
                "current_phase": current_phase,
                "phase_order": project.phase_order if project.phase_order is not None else PROJECT_PHASES.copy(),
                "phase_status": project.phase_status or {p: "pending" for p in PROJECT_PHASES},
                "autonomy_settings": project.agent_autonomy or {},
                "creator_profile": creator_profile_str,  # 创作者特质
                "fields": {},
                "messages": chat_history,
                "user_input": request.message,
                "agent_output": "",
                "waiting_for_human": False,
                "route_target": "",
                "use_deep_research": project.use_deep_research if hasattr(project, 'use_deep_research') else True,
                "is_producing": False,
                "error": None,
                "references": stream_references,
                "referenced_contents": stream_referenced_contents,
            }
            
            # 2. 意图分析特殊处理（支持传统阶段 + 灵活架构模板）
            phase_status = project.phase_status or {}
            intent_completed = phase_status.get("intent") == "completed"
            
            # 统计已问的问题数（只在当前轮次内 - 从最后一次"开始"或"完成"标记后开始计数）
            question_count = 0
            has_active_intent_flow = False  # 是否有活跃的意图分析对话
            
            # 关键：从后往前扫描，找到当前轮次的问题数
            for m in reversed(chat_history):
                if isinstance(m, AIMessage):
                    content = m.content if hasattr(m, 'content') else str(m)
                    # 遇到完成标记 → 之前的问题属于上一轮，停止计数
                    if "✅ 已生成" in content or "已生成【意图分析】" in content:
                        break
                    # 统计当前轮次的问题
                    if "【问题" in content and "/3】" in content:
                        question_count += 1
                        has_active_intent_flow = True
                elif isinstance(m, HumanMessage):
                    content = m.content if hasattr(m, 'content') else str(m)
                    # 遇到"开始"触发词且之前已经有问题 → 这是本轮开始，停止
                    if content.strip() in ["开始", "开始吧", "开始意图分析", "start", "Start"] and question_count > 0:
                        break
            
            # 检测是否通过模板触发意图分析（灵活架构场景）
            # 触发条件：用户输入包含"开始意图分析"/"开始"且有意图分析字段
            is_intent_trigger = request.message.strip() in ["开始", "开始吧", "开始意图分析", "start", "Start"]
            has_intent_block = False
            if project.use_flexible_architecture:
                intent_block = db.query(ContentBlock).filter(
                    ContentBlock.project_id == request.project_id,
                    ContentBlock.special_handler.in_(["intent_analysis", "intent"]),
                    ContentBlock.deleted_at == None,
                ).first()
                has_intent_block = intent_block is not None
            
            # 进入意图分析流程的条件（放宽：不仅限于 current_phase == "intent"）
            should_handle_intent = (
                (current_phase == "intent" and not intent_completed) or
                has_active_intent_flow or
                (is_intent_trigger and has_intent_block and question_count == 0)
            )
            
            print(f"[stream] 当前阶段={current_phase}, 意图已完成={intent_completed}, "
                  f"已问问题数={question_count}, 活跃意图流={has_active_intent_flow}, "
                  f"触发意图={is_intent_trigger}, 有意图块={has_intent_block}, "
                  f"处理意图={should_handle_intent}")
            
            # 意图分析流程
            if should_handle_intent:
                # 检查用户是否在问通用问题（而不是回答意图问题）
                question_indicators = ["？", "?", "什么", "怎么", "如何", "能不能", "可以吗", "你是", "能做", "有什么"]
                is_asking_question = any(qi in request.message for qi in question_indicators) and question_count > 0
                
                if is_asking_question:
                    # 用户在问通用问题，走 chat 流程
                    route_target = "chat"
                    system_prompt = f"""你是一个智能的内容生产 Agent。

## 我的能力
1. **意图分析**: 通过问答帮你明确内容目标
2. **消费者调研**: DeepResearch 深度分析目标用户
3. **内涵设计/生产**: 规划和生成核心内容
4. **外延设计/生产**: 营销触达内容
5. **消费者模拟**: 模拟用户反馈
6. **评估**: 多维度质量评估

当前阶段: {current_phase}

请友好地回答用户的问题。回答完后提醒用户继续回答意图分析的问题。"""
                elif question_count >= 3:
                    # 已问完3个问题，生成意图分析报告
                    route_target = "intent_produce"
                    system_prompt = """你是一个专业的内容策略顾问。根据用户的所有回答，生成结构化的项目意图分析。

请严格按以下格式输出：

1. **做什么**: [用一句话总结这个内容的主题和形式]
2. **给谁看**: [目标受众的岗位/角色、所在行业、1-2个核心痛点]
3. **核心价值**: [这个内容能给读者带来的独特收获或认知转变]

请仔细分析对话历史中用户的所有回答，提炼出准确的意图。"""
                else:
                    # 继续提问
                    route_target = "intent_question"
                    next_q = question_count + 1
                    
                    # 根据问题序号设置问题方向
                    if next_q == 1:
                        question_focus = "你想做什么内容？（比如：一篇文章、一个视频脚本、一份产品介绍、一套培训课件等），请用一句话描述你想做的内容方向。"
                    elif next_q == 2:
                        question_focus = "这个内容主要给谁看？请用「岗位/角色 + 所在行业 + 当前面临的1-2个痛点」来描述目标读者。"
                    else:
                        question_focus = "你觉得这个内容最核心的价值是什么？读者看完后应该获得什么独特的收获或认知？"
                    
                    system_prompt = f"""你是一个专业的内容策略顾问。你的任务是通过提问帮助用户澄清内容意图。

这是第 {next_q} 个问题（共3个）。

请在回复开头标注【问题 {next_q}/3】，然后提出以下问题：
{question_focus}

规则：
- 只问这1个问题，简洁明了
- 可以根据用户之前的回答适当调整措辞，使问题更自然
- 不要回答用户的问题，只提问"""
            else:
                # 非意图阶段 或 意图已完成：执行路由
                routed_state = await route_intent(initial_state)
                route_target = routed_state.get("route_target", "chat")
                
                if route_target == "chat":
                    # 构建引用上下文（如果有 @ 引用）
                    ref_context = ""
                    if stream_referenced_contents:
                        ref_parts = [f"### {name}\n{content}" for name, content in stream_referenced_contents.items()]
                        ref_context = f"\n\n## 引用的字段内容\n" + "\n\n".join(ref_parts)
                    
                    system_prompt = f"""你是一个智能的内容生产 Agent。

## 项目上下文
{creator_profile_str or '（暂无创作者信息）'}

当前阶段: {current_phase}{ref_context}

请友好地回答用户的问题。"""
                else:
                    # 其他阶段：非流式处理（走原逻辑）
                    # 根据当前阶段确定 route_target（用于前端判断是否为产出模式）
                    phase_route_map = {
                        "research": "research",
                        "design_inner": "design_inner",
                        "produce_inner": "produce_inner",
                        "design_outer": "design_outer",
                        "produce_outer": "produce_outer",
                        "simulate": "simulate",
                        "evaluate": "evaluate",
                    }
                    route_target = phase_route_map.get(current_phase, route_target)
                    
                    # 先发送路由信息，让前端知道这是产出模式
                    yield f"data: {json.dumps({'type': 'route', 'target': route_target}, ensure_ascii=False)}\n\n"
                    
                    result = await content_agent.run(
                project_id=request.project_id,
                user_input=request.message,
                        current_phase=current_phase,
                        creator_profile=creator_profile_str,
                autonomy_settings=project.agent_autonomy or {},
                        chat_history=chat_history,
                        references=stream_references,
                        referenced_contents=stream_referenced_contents,
                    )
                    full_content = result.get("agent_output", "")
                    display_content = result.get("display_output", full_content)  # 用于对话区显示
                    
                    # 记录日志 - 确保 full_prompt 始终有值
                    from core.models import GenerationLog
                    log_prompt_input = result.get("full_prompt", "")
                    if not log_prompt_input:
                        # 如果 full_prompt 为空，构建一个基本的日志
                        log_prompt_input = f"""[未捕获完整提示词]
路由目标: {route_target}
用户输入: {request.message}
当前阶段: {current_phase}
解析意图: {result.get('parsed_intent_type', 'unknown')}
目标字段: {result.get('parsed_target_field', 'none')}

注意: 此日志未能获取完整的系统提示词，请检查对应节点是否正确设置了 full_prompt"""
                    
                    gen_log = GenerationLog(
                        id=generate_uuid(),
                        project_id=request.project_id,
                        phase=current_phase,
                        operation=f"agent_stream_{route_target}",
                        model="gpt-5.1",
                        prompt_input=log_prompt_input,
                        prompt_output=full_content,
                        tokens_in=result.get("tokens_in", 0),
                        tokens_out=result.get("tokens_out", 0),
                        duration_ms=result.get("duration_ms", 0),
                        cost=result.get("cost", 0.0),
                        status="success",
                    )
                    db.add(gen_log)
                    
                    # ===== 特殊处理：@ 引用字段修改（同时支持 ProjectField 和 ContentBlock）=====
                    stream_modify_target = result.get("modify_target_field")
                    if stream_modify_target and full_content:
                        # 1. 先查找 ProjectField
                        mod_field = db.query(ProjectField).filter(
                            ProjectField.project_id == request.project_id,
                            ProjectField.name == stream_modify_target,
                        ).first()
                        if mod_field:
                            mod_field.content = full_content
                            mod_field.status = "completed"
                            print(f"[stream] ProjectField 修改成功: {stream_modify_target}")
                        else:
                            # 2. 查找 ContentBlock
                            mod_block = db.query(ContentBlock).filter(
                                ContentBlock.project_id == request.project_id,
                                ContentBlock.name == stream_modify_target,
                                ContentBlock.deleted_at == None,
                            ).first()
                            if mod_block:
                                mod_block.content = full_content
                                mod_block.status = "completed"
                                print(f"[stream] ContentBlock 修改成功: {stream_modify_target}")
                            else:
                                print(f"[stream] 修改失败: 未找到 {stream_modify_target}")
                    
                    # ===== 关键：将结果保存为 ProjectField =====
                    elif result.get("is_producing", False) and full_content:
                        # 使用 Agent 返回的 current_phase，因为可能已经跳转到新阶段
                        save_phase = result.get("current_phase", current_phase)
                        print(f"[stream] 保存阶段: {save_phase} (原阶段: {current_phase})")
                        
                        phase_field_names = {
                            "research": "消费者调研报告",
                            "design_inner": "内涵设计方案",
                            "produce_inner": "内涵生产内容",
                            "design_outer": "外延设计方案",
                            "produce_outer": "外延生产内容",
                            "simulate": "消费者模拟结果",
                            "evaluate": "评估报告",
                        }
                        field_name = phase_field_names.get(save_phase, f"{save_phase}结果")
                        
                        # 查找或创建字段
                        existing_field = db.query(ProjectField).filter(
                            ProjectField.project_id == request.project_id,
                            ProjectField.phase == save_phase,
                            ProjectField.name == field_name,
                        ).first()
                        
                        if existing_field:
                            existing_field.content = full_content
                            existing_field.status = "completed"
                        else:
                            new_field = ProjectField(
                                id=generate_uuid(),
                                project_id=request.project_id,
                                name=field_name,
                                phase=save_phase,
                                content=full_content,
                                field_type="structured" if save_phase == "research" else "richtext",
                                status="completed",
                            )
                            db.add(new_field)
                        
                        print(f"[stream] 已保存 {save_phase} 阶段结果到字段: {field_name}")
                        
                        # 注意：不再更新 project.golden_context
                        # 结果已保存到 ProjectField，后续阶段通过字段依赖获取
                        
                        # 更新阶段状态 - 使用正确的阶段
                        new_phase_status = project.phase_status or {}
                        new_phase_status[save_phase] = "in_progress"
                        project.phase_status = new_phase_status
                        
                        # 更新项目的当前阶段
                        project.current_phase = save_phase
                        db.add(project)
                    
                    # 一次性发送内容（发送简洁展示文本）
                    yield f"data: {json.dumps({'type': 'content', 'content': display_content}, ensure_ascii=False)}\n\n"
                    
                    # 保存响应
                    agent_msg = ChatMessage(
                        id=generate_uuid(),
                        project_id=request.project_id,
                        role="assistant",
                        content=display_content,  # 保存简洁展示内容到对话历史
                        message_metadata={"phase": current_phase, "route": route_target},
                    )
                    db.add(agent_msg)
                    db.commit()
                    
                    # 发送完成事件，包含 route 信息
                    yield f"data: {json.dumps({'type': 'done', 'message_id': agent_msg.id, 'route': route_target}, ensure_ascii=False)}\n\n"
                    return
            
            # 发送路由信息
            yield f"data: {json.dumps({'type': 'route', 'target': route_target}, ensure_ascii=False)}\n\n"
            
            # 3. 构建消息列表
            messages = [AIChatMessage(role="system", content=system_prompt)]
            for m in chat_history[-10:]:
                if isinstance(m, HumanMessage):
                    messages.append(AIChatMessage(role="user", content=m.content))
                elif isinstance(m, AIMessage):
                    messages.append(AIChatMessage(role="assistant", content=m.content))
            messages.append(AIChatMessage(role="user", content=request.message))
            
            # 4. 真正的 token-by-token 流式输出
            import time
            start_time = time.time()
            
            async for token in ai_client.stream_chat(messages, temperature=0.7):
                full_content += token
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 5. 记录 GenerationLog - 必须记录完整的 prompt（system + 历史 + user）
            from core.models import GenerationLog
            
            # 构建完整的 prompt 用于日志记录
            full_prompt_for_log = f"[System]\n{system_prompt}\n\n"
            for m in messages[1:-1]:  # 跳过 system 和最后的 user
                role = m.role if hasattr(m, 'role') else 'unknown'
                content = m.content if hasattr(m, 'content') else str(m)
                full_prompt_for_log += f"[{role}]\n{content}\n\n"
            full_prompt_for_log += f"[User]\n{request.message}"
            
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=request.project_id,
                phase=current_phase,
                operation=f"agent_stream_{route_target}",
                model="gpt-5.1",
                prompt_input=full_prompt_for_log,  # 记录完整 prompt
                prompt_output=full_content,
                tokens_in=len(full_prompt_for_log) // 4,  # 估算
                tokens_out=len(full_content) // 4,
                duration_ms=duration_ms,
                cost=0.0,
                status="success",
            )
            db.add(gen_log)
            
            # 6. 如果是意图分析完成，更新项目状态和字段
            if route_target == "intent_produce":
                # 解析生成的意图内容（用于保存到字段）
                intent_data = {
                    "做什么": "",
                    "给谁看": "",
                    "核心价值": "",
                }
                current_key = None
                for line in full_content.split('\n'):
                    if "**做什么**" in line or "做什么:" in line or "做什么：" in line:
                        current_key = "做什么"
                        if ":" in line or "：" in line:
                            intent_data[current_key] = line.split(":", 1)[-1].split("：", 1)[-1].strip().strip("*").strip()
                    elif "**给谁看**" in line or "给谁看:" in line or "给谁看：" in line:
                        current_key = "给谁看"
                        if ":" in line or "：" in line:
                            intent_data[current_key] = line.split(":", 1)[-1].split("：", 1)[-1].strip().strip("*").strip()
                    elif "**核心价值**" in line or "核心价值:" in line or "核心价值：" in line:
                        current_key = "核心价值"
                        if ":" in line or "：" in line:
                            intent_data[current_key] = line.split(":", 1)[-1].split("：", 1)[-1].strip().strip("*").strip()
                    elif current_key and line.strip():
                        if not intent_data[current_key]:
                            intent_data[current_key] = line.strip()
                
                # 更新阶段状态
                new_phase_status = project.phase_status or {}
                new_phase_status["intent"] = "completed"
                project.phase_status = new_phase_status
                db.add(project)
                
                if project.use_flexible_architecture:
                    # 灵活架构：保存到 ContentBlock
                    intent_block = db.query(ContentBlock).filter(
                        ContentBlock.project_id == request.project_id,
                        ContentBlock.special_handler.in_(["intent_analysis", "intent"]),
                        ContentBlock.deleted_at == None,
                    ).first()
                    if intent_block:
                        intent_block.content = full_content
                        intent_block.status = "completed"
                        print(f"[stream] 意图分析完成，已保存到 ContentBlock: {intent_block.name}")
                    else:
                        # 如果找不到特殊字段，尝试按名称查找
                        intent_block = db.query(ContentBlock).filter(
                            ContentBlock.project_id == request.project_id,
                            ContentBlock.name == "意图分析",
                            ContentBlock.block_type == "field",
                            ContentBlock.deleted_at == None,
                        ).first()
                        if intent_block:
                            intent_block.content = full_content
                            intent_block.status = "completed"
                            print(f"[stream] 意图分析完成，已保存到 ContentBlock (按名称): {intent_block.name}")
                        else:
                            print(f"[stream] 警告：未找到意图分析 ContentBlock，结果未保存")
                else:
                    # 传统架构：保存到 ProjectField
                    for field_name, content in intent_data.items():
                        if content:
                            existing = db.query(ProjectField).filter(
                                ProjectField.project_id == request.project_id,
                                ProjectField.phase == "intent",
                                ProjectField.name == field_name,
                            ).first()
                            if existing:
                                existing.content = content
                                existing.status = "completed"
                            else:
                                new_field = ProjectField(
                                    id=generate_uuid(),
                                    project_id=request.project_id,
                                    name=field_name,
                                    phase="intent",
                                    content=content,
                                    field_type="richtext",
                                    status="completed",
                                )
                                db.add(new_field)
                    
                    print(f"[stream] 意图分析完成，已保存到 ProjectField")
            
            # 7. 保存完整响应
            agent_msg = ChatMessage(
                id=generate_uuid(),
                project_id=request.project_id,
                role="assistant",
                content=full_content,
                message_metadata={"phase": current_phase, "route": route_target},
            )
            db.add(agent_msg)
            db.commit()
            
            yield f"data: {json.dumps({'type': 'done', 'message_id': agent_msg.id, 'route': route_target}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        }
    )


@router.post("/advance")
async def advance_phase(
    request: ChatRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    推进到下一阶段（用户点击确认按钮后调用）
    
    快速返回，调研任务在后台执行
    """
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_idx = project.phase_order.index(project.current_phase)
    if current_idx >= len(project.phase_order) - 1:
        return ChatResponseExtended(
            message_id="",
            message="已经是最后一个阶段了",
            phase=project.current_phase,
            phase_status=project.phase_status,
            waiting_for_human=False,
        )
    
    prev_phase = project.current_phase
    next_phase = project.phase_order[current_idx + 1]
    
    # 更新阶段状态
    project.phase_status[prev_phase] = "completed"
    project.current_phase = next_phase
    project.phase_status[next_phase] = "in_progress"
    db.commit()
    
    # 保存进入阶段的消息
    enter_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=f"✅ 已进入【{_get_phase_field_name(next_phase)}】阶段。请在右侧对话框输入「开始」来生成内容。",
        message_metadata={"phase": next_phase},
    )
    db.add(enter_msg)
    db.commit()
    
    # 重新查询获取最新状态
    db.refresh(project)
    
    return ChatResponseExtended(
        message_id=enter_msg.id,
        message=f"✅ 已进入【{_get_phase_field_name(next_phase)}】阶段。请在右侧对话框输入「开始」来生成内容。",
        phase=next_phase,
        phase_status=project.phase_status,
        waiting_for_human=False,
        project_updated=True,
        is_producing=False,
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
