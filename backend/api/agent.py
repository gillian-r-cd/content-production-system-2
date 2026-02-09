# backend/api/agent.py
# 功能: Agent对话API，支持SSE流式输出、对话历史、编辑重发、Tool调用
# 主要路由: /chat, /stream, /history, /retry, /tool
# 数据结构: ChatRequest, ChatResponse, ChatMessage
#
# 架构原则（重构版）:
# 1. stream_chat 是纯粹的传输层，不包含任何路由逻辑
# 2. 所有路由决策由 route_intent() 统一做出
# 3. 各阶段节点函数自行管理内部状态（问题计数、偏好检查等）
# 4. 只有 chat 路由做 token-by-token 流式输出，其余走节点函数

"""
Agent 对话 API
支持普通响应和SSE流式输出
支持对话历史持久化、编辑重发、再试一次
"""

import json
import asyncio
import time
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField, ChatMessage, GenerationLog, ContentVersion, generate_uuid
from core.models.content_block import ContentBlock
from core.orchestrator import content_agent


router = APIRouter()


# ============== Helpers ==============

import logging
_logger = logging.getLogger("agent")


def _save_version_before_overwrite(db: Session, entity_id: str, old_content: str, source: str, source_detail: str = None):
    """Agent 覆写字段/内容块前，先保存旧内容为版本"""
    if not old_content or not old_content.strip():
        return
    max_ver = db.query(ContentVersion.version_number).filter(
        ContentVersion.block_id == entity_id
    ).order_by(ContentVersion.version_number.desc()).first()
    next_ver = (max_ver[0] + 1) if max_ver else 1
    ver = ContentVersion(
        id=generate_uuid(),
        block_id=entity_id,
        version_number=next_ver,
        content=old_content,
        source=source,
        source_detail=source_detail,
    )
    db.add(ver)
    db.flush()
    _logger.info(f"[版本] agent覆写前保存 v{next_ver} ({source})")


def _resolve_references(
    db: Session,
    project_id: str,
    references: list[str],
) -> dict[str, str]:
    """
    统一的 @ 引用解析：ProjectField → ContentBlock → 方案JSON
    返回: {引用名: 内容} 映射
    """
    if not references:
        return {}

    result = {}

    # 1. 搜索 ProjectField
    ref_fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.name.in_(references)
    ).all()
    for f in ref_fields:
        result[f.name] = f.content or ""

    # 2. 搜索 ContentBlock（灵活架构）
    missing = [r for r in references if r not in result]
    if missing:
        ref_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name.in_(missing),
            ContentBlock.deleted_at == None,
        ).all()
        for b in ref_blocks:
            result[b.name] = b.content or ""

    # 3. 从 design_inner 字段的 proposals JSON 中解析方案引用
    import re
    proposal_refs = [r for r in references if r not in result and r.startswith("方案")]
    if proposal_refs:
        design_field = db.query(ProjectField).filter(
            ProjectField.project_id == project_id,
            ProjectField.phase == "design_inner",
        ).first()
        if design_field and design_field.content:
            try:
                data = json.loads(design_field.content)
                proposals = data.get("proposals", [])
                if isinstance(proposals, list):
                    for ref_name in proposal_refs:
                        match = re.match(r"方案(\d+)[:：]?(.*)", ref_name)
                        if match:
                            idx = int(match.group(1)) - 1
                            if 0 <= idx < len(proposals):
                                result[ref_name] = json.dumps(proposals[idx], ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass
    
    if result:
        print(f"[Agent] @ 引用解析: {references} -> 找到 {len(result)} 个")
    
    return result


def _save_result_to_field(
    db: Session,
    project: Project,
    result: dict,
    current_phase: str,
) -> Optional[dict]:
    """
    将节点执行结果保存到 ProjectField。
    返回 field_updated 信息（如有）。
    """
    agent_output = result.get("agent_output", "")
    is_producing = result.get("is_producing", False)
    result_phase = result.get("current_phase", current_phase)
    modify_target = result.get("modify_target_field")

    if not agent_output:
        return None

    field_updated = None

    # 情况1: 修改已有字段
    if modify_target:
        import re as _re
        # 情况1a: 方案引用（"方案N:..." 是 design_inner 字段内的子元素）
        proposal_match = _re.match(r"方案(\d+)", modify_target)
        if proposal_match:
            idx = int(proposal_match.group(1)) - 1
            design_field = db.query(ProjectField).filter(
                ProjectField.project_id == project.id,
                ProjectField.phase == "design_inner",
            ).first()
            if design_field and design_field.content:
                try:
                    data = json.loads(design_field.content)
                    proposals = data.get("proposals", [])
                    if 0 <= idx < len(proposals):
                        # 保存旧版本
                        _save_version_before_overwrite(db, design_field.id, design_field.content, "agent_modify", f"modify_proposal_{idx+1}")
                        # 尝试将 agent_output 解析为 JSON 更新方案
                        try:
                            # 清理 markdown 代码块包裹
                            clean = agent_output.strip()
                            if clean.startswith("```"):
                                clean = _re.sub(r'^```(?:json)?\s*', '', clean)
                                clean = _re.sub(r'\s*```$', '', clean)
                            modified_proposal = json.loads(clean)
                            proposals[idx] = modified_proposal
                        except (json.JSONDecodeError, TypeError):
                            # LLM 输出不是 JSON → 作为 description 写入
                            proposals[idx]["description"] = agent_output
                        data["proposals"] = proposals
                        design_field.content = json.dumps(data, ensure_ascii=False, indent=2)
                        field_updated = {
                            "id": design_field.id, "name": design_field.name,
                            "phase": "design_inner", "action": "proposal_modified",
                        }
                        print(f"[save] 更新方案{idx+1}: {proposals[idx].get('name', '?')}")
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"[save] 方案更新失败: {e}")
        
        # 情况1b: 普通字段名（ProjectField / ContentBlock）
        if not field_updated:
            target = db.query(ProjectField).filter(
                ProjectField.project_id == project.id,
                ProjectField.name == modify_target,
            ).first()
            if target:
                _save_version_before_overwrite(db, target.id, target.content, "agent_modify", modify_target)
                target.content = agent_output
                target.status = "completed"
                field_updated = {"id": target.id, "name": target.name, "phase": target.phase, "action": "modified"}
            else:
                target_block = db.query(ContentBlock).filter(
                    ContentBlock.project_id == project.id,
                    ContentBlock.name == modify_target,
                    ContentBlock.deleted_at == None,
                ).first()
                if target_block:
                    _save_version_before_overwrite(db, target_block.id, target_block.content, "agent_modify", modify_target)
                    target_block.content = agent_output
                    target_block.status = "completed"
                    field_updated = {"id": target_block.id, "name": target_block.name, "phase": "", "action": "modified"}

    # 情况2: 意图分析阶段 - 解析JSON保存为3个字段
    elif is_producing and result_phase == "intent":
        import re
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', agent_output, re.DOTALL)
            json_str = json_match.group(1) if json_match else agent_output
            intent_data = json.loads(json_str)

            fields_created = []
            for field_name in ["做什么", "给谁看", "期望行动"]:
                content = intent_data.get(field_name, "")
                if not content:
                    continue
                existing = db.query(ProjectField).filter(
                    ProjectField.project_id == project.id,
                    ProjectField.phase == "intent",
                    ProjectField.name == field_name,
                ).first()
                if existing:
                    _save_version_before_overwrite(db, existing.id, existing.content, "agent_produce", f"intent_{field_name}")
                    existing.content = content
                    existing.status = "completed"
                    fields_created.append({"id": existing.id, "name": field_name})
                else:
                    new_field = ProjectField(
                        id=generate_uuid(),
                        project_id=project.id,
                        name=field_name,
                        phase="intent",
                        content=content,
                        field_type="text",
                        status="completed",
                    )
                    db.add(new_field)
                    fields_created.append({"id": new_field.id, "name": field_name})

            field_updated = {"fields": fields_created, "phase": result_phase}
        except (json.JSONDecodeError, Exception) as e:
            print(f"[Agent] Intent JSON parse fallback: {e}")
            new_field = ProjectField(
                id=generate_uuid(),
                project_id=project.id,
                name="项目意图",
                phase=result_phase,
                content=agent_output,
                field_type="richtext",
                status="completed",
            )
            db.add(new_field)
            field_updated = {"id": new_field.id, "name": "项目意图", "phase": result_phase}

    # 情况3: 其他阶段产出 - 保存为单个字段
    elif is_producing and result_phase:
        field_name = _get_phase_field_name(result_phase)
        existing = db.query(ProjectField).filter(
            ProjectField.project_id == project.id,
            ProjectField.phase == result_phase,
            ProjectField.name == field_name,
        ).first()
        if existing:
            _save_version_before_overwrite(db, existing.id, existing.content, "agent_produce", result_phase)
            existing.content = agent_output
            existing.status = "completed"
            field_updated = {"id": existing.id, "name": existing.name, "phase": result_phase}
        else:
            new_field = ProjectField(
                id=generate_uuid(),
                project_id=project.id,
                name=field_name,
                phase=result_phase,
                content=agent_output,
                field_type="structured" if result_phase == "research" else "richtext",
                status="completed",
            )
            db.add(new_field)
            field_updated = {"id": new_field.id, "name": new_field.name, "phase": result_phase}

    # 更新灵活架构的 ContentBlock（如有）
    if is_producing and result_phase and project.use_flexible_architecture:
        _update_content_block(db, project.id, result_phase, agent_output)

    return field_updated


def _update_content_block(db: Session, project_id: str, phase: str, content: str):
    """更新灵活架构中对应的 ContentBlock"""
    handler_map = {
        "intent": ["intent_analysis", "intent"],
        "research": ["consumer_research", "research"],
    }
    handlers = handler_map.get(phase)
    if handlers:
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.special_handler.in_(handlers),
            ContentBlock.deleted_at == None,
        ).first()
        if block:
            _save_version_before_overwrite(db, block.id, block.content, "agent_produce", f"block_{phase}")
            block.content = content
            block.status = "completed"


def _build_chat_display(result: dict, current_phase: str) -> str:
    """构建对话区显示内容"""
    display = result.get("display_output")
    if display:
        return display

    if result.get("is_producing", False):
        phase_names = {
            "intent": "意图分析", "research": "消费者调研报告",
            "design_inner": "内涵设计方案", "produce_inner": "内涵生产内容",
            "design_outer": "外延设计方案", "produce_outer": "外延生产内容",
            "evaluate": "评估报告",
        }
        name = phase_names.get(result.get("current_phase", current_phase), current_phase)
        return f"✅ 已生成【{name}】，请在左侧工作台查看和编辑。"

    return result.get("agent_output", "")


def _build_chat_system_prompt(
    current_phase: str,
    creator_profile: str,
    referenced_contents: dict,
    references: list,
) -> str:
    """构建 chat 路由的 system prompt"""
    ref_context = ""
    if referenced_contents:
        ref_parts = [f"### {name}\n{content}" for name, content in referenced_contents.items()]
        ref_context = f"\n\n## 引用的字段内容\n" + "\n\n".join(ref_parts)

    proposal_instruction = ""
    if any(r.startswith("方案") for r in references):
        proposal_instruction = "\n\n用户引用了具体方案。如需修改，请输出完整方案JSON（```json代码块包裹）。"

    return f"""你是一个智能的内容生产 Agent。

## 我的能力
1. **意图分析**: 通过问答帮你明确内容目标
2. **消费者调研**: DeepResearch 深度分析目标用户
3. **内涵设计/生产**: 规划和生成核心内容
4. **外延设计/生产**: 营销触达内容
5. **消费者模拟**: 模拟用户反馈
6. **评估**: 多维度质量评估

## 项目上下文
{creator_profile or '（暂无创作者信息）'}

当前阶段: {current_phase}{ref_context}{proposal_instruction}

请友好地回答用户的问题。"""


# ============== Schemas ==============

class ChatRequest(BaseModel):
    """对话请求"""
    project_id: str
    message: str
    current_phase: Optional[str] = None
    references: List[str] = []


class FieldUpdatedInfo(BaseModel):
    """字段更新信息"""
    id: str
    name: str
    phase: str
    action: Optional[str] = None


class ChatResponseSchema(BaseModel):
    """对话响应"""
    message_id: str
    message: str
    phase: str
    phase_status: Dict[str, str]
    waiting_for_human: bool
    field_updated: Optional[FieldUpdatedInfo] = None


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


class ChatResponseExtended(BaseModel):
    """扩展的对话响应 - 包含字段更新"""
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
    db: Session = Depends(get_db),
):
    """获取项目的对话历史"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [_to_message_response(m) for m in messages]


@router.post("/chat", response_model=ChatResponseExtended)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    与Agent对话（非流式）
    
    统一走 content_agent.run()，由 LangGraph 图决定路由和执行。
    """
    from core.ai_client import ai_client
    
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_phase = request.current_phase or project.current_phase
    
    # 加载当前阶段的历史对话
    history_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == request.project_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    current_phase_messages = []
    for m in history_messages:
        msg_phase = m.message_metadata.get("phase") if m.message_metadata else None
        if msg_phase is None or msg_phase == current_phase:
            current_phase_messages.append(m)
    
    chat_history = [{"role": m.role, "content": m.content} for m in current_phase_messages[-20:]]
    
    # 保存用户消息
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_metadata={"phase": current_phase, "references": request.references},
    )
    db.add(user_msg)
    db.commit()
    
    # 解析引用
    referenced_contents = _resolve_references(db, request.project_id, request.references)

    # 获取创作者特质
    creator_profile_str = ""
    if project.creator_profile:
        creator_profile_str = project.creator_profile.to_prompt_context()
    
    # 运行 Agent
    try:
        result = await asyncio.wait_for(
            content_agent.run(
                project_id=request.project_id,
                user_input=request.message,
                current_phase=current_phase,
                creator_profile=creator_profile_str,
                autonomy_settings=project.agent_autonomy or {},
                use_deep_research=getattr(project, 'use_deep_research', True),
                chat_history=chat_history,
                phase_status=project.phase_status or {},
                phase_order=project.phase_order,
                references=request.references or [],
                referenced_contents=referenced_contents,
            ),
            timeout=300,
        )
    except asyncio.TimeoutError:
        error_msg = ChatMessage(
            id=generate_uuid(), project_id=request.project_id,
            role="assistant", content="⚠️ 处理超时，请稍后重试。",
            message_metadata={"phase": current_phase, "error": "timeout"},
        )
        db.add(error_msg)
        db.commit()
        return JSONResponse(status_code=504, content={"detail": "Agent 处理超时"})
    except Exception as agent_err:
        error_msg = ChatMessage(
            id=generate_uuid(), project_id=request.project_id,
            role="assistant", content=f"⚠️ 处理失败: {str(agent_err)[:200]}",
            message_metadata={"phase": current_phase, "error": str(agent_err)[:200]},
        )
        db.add(error_msg)
        db.commit()
        return JSONResponse(status_code=500, content={"detail": str(agent_err)[:200]})
    
    result_phase = result.get("current_phase", current_phase)
    is_producing = result.get("is_producing", False)
    
    # 保存结果到字段
    field_updated = _save_result_to_field(db, project, result, current_phase)

    # 记录日志
    log_entry = GenerationLog(
        id=generate_uuid(),
        project_id=request.project_id,
        phase=result_phase,
        operation=f"agent_chat_{result_phase}",
        model=ai_client.model,
        prompt_input=result.get("full_prompt", request.message),
        prompt_output=result.get("agent_output", ""),
        tokens_in=result.get("tokens_in", 0),
        tokens_out=result.get("tokens_out", 0),
        duration_ms=result.get("duration_ms", 0),
        cost=result.get("cost", 0.0),
        status="success",
    )
    db.add(log_entry)
    
    # 构建对话区显示内容
    chat_content = _build_chat_display(result, current_phase)

    # 保存 Agent 响应
    field_id = None
    if field_updated:
        field_id = field_updated.get("id") or (field_updated.get("fields", [{}])[0].get("id") if field_updated.get("fields") else None)
    
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
            "is_producing": is_producing,
        },
    )
    db.add(agent_msg)
    
    # 更新项目状态
    project_updated = False
    new_phase_status = result.get("phase_status", project.phase_status or {})
    if result_phase == "intent" and is_producing and field_updated:
        new_phase_status["intent"] = "completed"
    if new_phase_status != project.phase_status:
        project.phase_status = new_phase_status
        project_updated = True
    if result_phase != project.current_phase:
        project.current_phase = result_phase
        project_updated = True
    
    db.commit()
    
    return ChatResponseExtended(
        message_id=agent_msg.id,
        message=chat_content,
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
        "evaluate": "项目评估报告",
    }
    return names.get(phase, f"{phase}_output")


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
    """重新生成Assistant响应"""
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
    
    result = await content_agent.run(
        project_id=user_msg.project_id,
        user_input=user_msg.content,
        current_phase=user_msg.message_metadata.get("phase", project.current_phase) if user_msg.message_metadata else project.current_phase,
        creator_profile=creator_profile_str,
        autonomy_settings=project.agent_autonomy or {},
        use_deep_research=getattr(project, 'use_deep_research', True),
        phase_status=project.phase_status or {},
    )
    
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
    
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=f"调用工具: {request.tool_name}",
        message_metadata={"phase": project.current_phase, "tool_called": request.tool_name, "parameters": request.parameters},
    )
    db.add(user_msg)
    
    try:
        output = ""
        params = request.parameters or {}
        
        if request.tool_name == "deep_research":
            deps = get_intent_and_research(request.project_id, db)
            intent_str = deps.get("intent", "")
            query = params.get("query", f"项目调研: {project.name}")
            result = await deep_research_fn(query=query, intent=intent_str or project.name, max_sources=params.get("max_sources", 10))
            output = json.dumps({
                "summary": result.summary if hasattr(result, 'summary') else str(result),
                "personas": [p.__dict__ if hasattr(p, '__dict__') else str(p) for p in (result.personas if hasattr(result, 'personas') else [])],
                "sources_count": len(result.sources) if hasattr(result, 'sources') else 0,
            }, ensure_ascii=False, default=str)
            
        elif request.tool_name == "generate_field":
            field_name = params.get("field_name")
            if not field_name:
                output = "错误: 需要提供 field_name 参数"
            else:
                field_data = get_field_content(request.project_id, field_name, db)
                if field_data:
                    from api.blocks import generate_block_content
                    block = db.query(ContentBlock).filter(ContentBlock.id == field_data["id"], ContentBlock.deleted_at == None).first()
                    if block:
                        result = await generate_block_content(block.id, db)
                        output = f"已生成字段 '{field_name}'。\n\n{result.get('content', '')[:500]}..."
                    else:
                        output = f"未找到字段 '{field_name}'"
                else:
                    output = f"未找到字段 '{field_name}'"
            
        elif request.tool_name == "simulate_consumer":
            from core.ai_client import AIClient, ChatMessage as AIChatMessage
            content = params.get("content", "")
            if not content:
                fields = db.query(ProjectField).filter(ProjectField.project_id == request.project_id, ProjectField.content != None, ProjectField.content != "").all()
                content = "\n\n".join([f"【{f.name}】\n{f.content}" for f in fields]) if fields else ""
            if not content:
                output = "暂无已生成的内容，请先生成字段内容。"
            else:
                ai = AIClient()
                sim_result = await ai.async_chat(
                    messages=[
                        AIChatMessage(role="system", content="你是一位典型的内容消费者。请给出真实的感受、建议和评分（1-10分）。"),
                        AIChatMessage(role="user", content=f"请体验以下内容：\n\n{content[:5000]}"),
                    ], max_tokens=4096,
                )
                output = sim_result.content
            
        elif request.tool_name == "evaluate_content":
            from core.ai_client import AIClient, ChatMessage as AIChatMessage
            fields = db.query(ProjectField).filter(ProjectField.project_id == request.project_id, ProjectField.status == "completed").all()
            parts = [f"【{f.name}】\n{f.content}" for f in fields if f.content]
            if not parts:
                output = "暂无已完成的内容，请先生成字段。"
            else:
                ai = AIClient()
                eval_result = await ai.async_chat(
                    messages=[
                        AIChatMessage(role="system", content="你是专业内容评估专家。评估内容质量并给出1-10分和改进建议。"),
                        AIChatMessage(role="user", content=f"请评估：\n\n{chr(10).join(parts)[:8000]}"),
                    ], max_tokens=4096,
                )
                output = eval_result.content
        
        if not output:
            output = f"工具 {request.tool_name} 执行完成，但没有返回结果。"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        output = f"工具执行失败: {str(e)}"
    
    agent_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=output,
        message_metadata={"phase": project.current_phase, "tool_used": request.tool_name},
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
    与Agent对话（SSE流式输出）

    架构原则 — 彻底去除 if-else 路由:
    1. 收集上下文（DB查询、历史加载、引用解析）
    2. route_intent(state) → 唯一路由决策
    3. 分发:
       - chat → ai_client.stream_chat() (token-by-token)
       - generic_research → 深度调研（非流式）
       - 其余 → 调用对应节点函数（非流式），结果以SSE发送
    4. 保存响应、更新状态
    """
    from core.ai_client import ai_client, ChatMessage as AIChatMessage
    from core.models import PROJECT_PHASES
    from core.orchestrator import (
        route_intent, ContentProductionState,
        intent_analysis_node, research_node, design_inner_node,
        produce_inner_node, design_outer_node, produce_outer_node,
        evaluate_node, modify_node, query_node, tool_node, chat_node,
        generate_field_node,
    )
    from langchain_core.messages import HumanMessage, AIMessage
    
    # --- 验证项目 ---
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_phase = request.current_phase or project.current_phase
    
    # --- 保存用户消息 ---
    user_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="user",
        content=request.message,
        message_metadata={"phase": current_phase, "references": request.references},
    )
    db.add(user_msg)
    db.commit()
    
    # 保存 user_msg.id，在 SSE 事件中返回给前端（用于编辑重发等场景）
    saved_user_msg_id = user_msg.id
    
    # --- 加载当前阶段对话历史 ---
    history_msgs = db.query(ChatMessage).filter(
        ChatMessage.project_id == request.project_id
    ).order_by(ChatMessage.created_at).all()
    
    current_phase_msgs = []
    for m in history_msgs:
        msg_phase = m.message_metadata.get("phase") if m.message_metadata else None
        if msg_phase is None or msg_phase == current_phase:
            current_phase_msgs.append(m)
    
    chat_history = []
    for m in current_phase_msgs[-20:]:
        if m.role == "user":
            chat_history.append(HumanMessage(content=m.content))
        else:
            chat_history.append(AIMessage(content=m.content))
    
    # --- 解析 @ 引用 ---
    references = request.references or []
    referenced_contents = _resolve_references(db, request.project_id, references)

    # --- SSE 事件生成器 ---
    async def event_generator():
        try:
            # 先返回用户消息的真实 ID（前端用于编辑重发）
            yield f"data: {json.dumps({'type': 'user_saved', 'message_id': saved_user_msg_id}, ensure_ascii=False)}\n\n"
            
            # 获取创作者特质
            creator_profile_str = ""
            if project.creator_profile:
                creator_profile_str = project.creator_profile.to_prompt_context()
            
            # ===== 构建状态 =====
            initial_state: ContentProductionState = {
                "project_id": request.project_id,
                "current_phase": current_phase,
                "phase_order": project.phase_order if project.phase_order is not None else PROJECT_PHASES.copy(),
                "phase_status": project.phase_status or {p: "pending" for p in PROJECT_PHASES},
                "autonomy_settings": project.agent_autonomy or {},
                "creator_profile": creator_profile_str,
                "fields": {},
                "messages": chat_history,
                "user_input": request.message,
                "agent_output": "",
                "waiting_for_human": False,
                "route_target": "",
                "use_deep_research": getattr(project, 'use_deep_research', True),
                "is_producing": False,
                "error": None,
                "references": references,
                "referenced_contents": referenced_contents,
                # 初始化路由相关字段
                "tokens_in": 0, "tokens_out": 0, "duration_ms": 0, "cost": 0.0,
                "full_prompt": "",
                "parsed_intent_type": "", "parsed_target_field": None,
                "parsed_operation": "", "modify_target_field": None,
                "pending_intents": [],
            }

            # ===== 唯一路由决策 =====
            routed_state = await route_intent(initial_state)
            route_target = routed_state.get("route_target", "chat")

            print(f"[stream] route_intent → {route_target}")
            yield f"data: {json.dumps({'type': 'route', 'target': route_target}, ensure_ascii=False)}\n\n"

            # ===== 分发: chat → 流式 =====
            if route_target == "chat":
                system_prompt = _build_chat_system_prompt(
                    current_phase, creator_profile_str, referenced_contents, references)

                messages = [AIChatMessage(role="system", content=system_prompt)]
                for m in chat_history[-10:]:
                    if isinstance(m, HumanMessage):
                        messages.append(AIChatMessage(role="user", content=m.content))
                    elif isinstance(m, AIMessage):
                        messages.append(AIChatMessage(role="assistant", content=m.content))
                messages.append(AIChatMessage(role="user", content=request.message))

                full_content = ""
                start_time = time.time()
                async for token in ai_client.stream_chat(messages, temperature=0.7):
                    full_content += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                duration_ms = int((time.time() - start_time) * 1000)

                # 处理方案引用修改
                _handle_proposal_auto_update(db, request, references, full_content)

                # 保存日志
                full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{request.message}"
                gen_log = GenerationLog(
                    id=generate_uuid(), project_id=request.project_id,
                    phase=current_phase, operation=f"agent_stream_chat",
                    model=ai_client.model, prompt_input=full_prompt,
                    prompt_output=full_content,
                    tokens_in=len(full_prompt) // 4, tokens_out=len(full_content) // 4,
                    duration_ms=duration_ms, cost=0.0, status="success",
                )
                db.add(gen_log)
                
                # 保存响应
                agent_msg = ChatMessage(
                    id=generate_uuid(), project_id=request.project_id,
                    role="assistant", content=full_content,
                    message_metadata={"phase": current_phase, "route": route_target},
                )
                db.add(agent_msg)
                db.commit()

                yield f"data: {json.dumps({'type': 'done', 'message_id': agent_msg.id, 'route': route_target}, ensure_ascii=False)}\n\n"
                return

            # ===== 分发: generic_research → 深度调研 =====
            if route_target == "generic_research":
                yield f"data: {json.dumps({'type': 'content', 'content': '🔍 正在进行深度调研...'}, ensure_ascii=False)}\n\n"
                report_md = await _do_generic_research(request.message, request.project_id, creator_profile_str)

                gen_log = GenerationLog(
                    id=generate_uuid(), project_id=request.project_id,
                    phase=current_phase, operation="agent_stream_generic_research",
                    model=ai_client.model, prompt_input=f"[调研] {request.message}",
                    prompt_output=report_md[:2000],
                    tokens_in=0, tokens_out=len(report_md), duration_ms=0, cost=0.0, status="success",
                )
                db.add(gen_log)
                db.commit()

                yield f"data: {json.dumps({'type': 'content', 'content': report_md}, ensure_ascii=False)}\n\n"

                agent_msg = ChatMessage(
                    id=generate_uuid(), project_id=request.project_id,
                    role="assistant", content=report_md,
                    message_metadata={"phase": current_phase, "route": "generic_research"},
                )
                db.add(agent_msg)
                db.commit()
                
                yield f"data: {json.dumps({'type': 'done', 'is_producing': False}, ensure_ascii=False)}\n\n"
                return

            # ===== 分发: advance_phase → 推进阶段 =====
            if route_target == "advance_phase":
                advance_result = _do_advance_phase(db, project, routed_state)
                yield f"data: {json.dumps({'type': 'content', 'content': advance_result['message']}, ensure_ascii=False)}\n\n"

                agent_msg = ChatMessage(
                    id=generate_uuid(), project_id=request.project_id,
                    role="assistant", content=advance_result["message"],
                    message_metadata={"phase": advance_result.get("phase", current_phase), "route": "advance_phase"},
                )
                db.add(agent_msg)
                db.commit()

                yield f"data: {json.dumps({'type': 'done', 'message_id': agent_msg.id, 'route': 'advance_phase', 'is_producing': False}, ensure_ascii=False)}\n\n"
                return

            # ===== 分发: 所有其他路由 → 调用节点函数 =====
            # 映射 route_target → 节点函数
            node_map = {
                "phase_intent": intent_analysis_node,
                "phase_research": research_node,
                "phase_design_inner": design_inner_node,
                "phase_produce_inner": produce_inner_node,
                "phase_design_outer": design_outer_node,
                "phase_produce_outer": produce_outer_node,
                "phase_evaluate": evaluate_node,
                "research": research_node,
                "modify": modify_node,
                "query": query_node,
                "generate": generate_field_node,
                "generate_field": generate_field_node,
            }
            # tool_* 路由统一走 tool_node
            if route_target.startswith("tool_"):
                node_map[route_target] = tool_node

            # "phase_current" → 映射到当前阶段的节点
            if route_target == "phase_current":
                route_target = f"phase_{current_phase}"

            node_fn = node_map.get(route_target)

            if not node_fn:
                # 未知路由 → 回退到 chat
                print(f"[stream] 未知路由 {route_target}，回退到 chat")
                node_fn = chat_node

            # 执行节点函数
            yield f"data: {json.dumps({'type': 'content', 'content': '⏳ 正在处理...'}, ensure_ascii=False)}\n\n"
            result = await node_fn(routed_state)

            # ===== 统一后处理 =====
            agent_output = result.get("agent_output", "")
            is_producing = result.get("is_producing", False)
            result_phase = result.get("current_phase", current_phase)

            # 保存到 ProjectField
            field_updated = _save_result_to_field(db, project, result, current_phase)

            # 保存日志
            gen_log = GenerationLog(
                id=generate_uuid(), project_id=request.project_id,
                phase=result_phase, operation=f"agent_stream_{route_target}",
                model=ai_client.model,
                prompt_input=result.get("full_prompt", ""),
                prompt_output=agent_output[:2000] if agent_output else "",
                tokens_in=result.get("tokens_in", 0), tokens_out=result.get("tokens_out", 0),
                duration_ms=result.get("duration_ms", 0), cost=result.get("cost", 0.0),
                status="success",
            )
            db.add(gen_log)

            # 更新项目状态
            new_phase_status = result.get("phase_status", project.phase_status or {})
            if result_phase == "intent" and is_producing and field_updated:
                new_phase_status["intent"] = "completed"
            if new_phase_status != project.phase_status:
                project.phase_status = new_phase_status
            if result_phase != project.current_phase:
                project.current_phase = result_phase
            db.add(project)

            # 构建对话区显示
            display_content = _build_chat_display(result, current_phase)

            # 发送内容
            yield f"data: {json.dumps({'type': 'content', 'content': display_content}, ensure_ascii=False)}\n\n"

            # 保存响应
            agent_msg = ChatMessage(
                id=generate_uuid(), project_id=request.project_id,
                role="assistant", content=display_content,
                message_metadata={"phase": result_phase, "route": route_target},
            )
            db.add(agent_msg)
            db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': agent_msg.id, 'route': route_target, 'is_producing': is_producing}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[stream] EXCEPTION: {e}\n{tb}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'traceback': tb[:500]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _handle_proposal_auto_update(db: Session, request: ChatRequest, references: list, content: str):
    """如果 chat 回复中包含方案 JSON，自动更新 design_inner 字段"""
    import re
    has_proposal_ref = any(r.startswith("方案") for r in references)
    if not has_proposal_ref or not content:
        return

    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if not json_match:
        return

    try:
        modified = json.loads(json_match.group(1))
        if not isinstance(modified, dict) or "name" not in modified or "fields" not in modified:
            return

        design_field = db.query(ProjectField).filter(
            ProjectField.project_id == request.project_id,
            ProjectField.phase == "design_inner",
        ).first()
        if not design_field or not design_field.content:
            return

        data = json.loads(design_field.content)
        proposals = data.get("proposals", [])
        for i, p in enumerate(proposals):
            if p.get("id") == modified.get("id") or p.get("name") == modified.get("name"):
                proposals[i] = modified
                data["proposals"] = proposals
                design_field.content = json.dumps(data, ensure_ascii=False, indent=2)
                print(f"[stream] 自动更新方案: {modified.get('name')}")
                break
    except (json.JSONDecodeError, TypeError):
        pass


async def _do_generic_research(query: str, project_id: str, creator_profile: str) -> str:
    """执行通用深度调研，返回 Markdown 报告"""
    from core.tools.deep_research import search_tavily, plan_search_queries
    from core.tools.architecture_reader import get_intent_and_research
    from core.ai_client import ai_client as _ai, ChatMessage as _CM

    deps = get_intent_and_research(project_id)
    intent = deps.get("intent", query)

    try:
        search_queries = await plan_search_queries(query, intent)
        if not search_queries:
            search_queries = [query[:100]]

        all_results = []
        for q in search_queries:
            results = search_tavily(q, max_results=5)
            all_results.extend(results)

        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
                if len(unique_results) >= 10:
                    break

        sections = []
        source_urls = []
        for idx, item in enumerate(unique_results[:10]):
            url = item.get("url", f"来源{idx+1}")
            title = item.get("title", "")
            content = item.get("content", "")[:3000]
            source_urls.append(url)
            sections.append(f"[来源{idx+1}] ({url})\n标题: {title}\n{content}")

        combined = "\n\n---\n\n".join(sections)[:15000]
        source_list = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(source_urls))

        response = await _ai.async_chat([
            _CM(role="system", content=f"""你是一个专业的调研分析师。基于搜索结果生成结构化调研报告。
使用内联引用 [1] [2] 标注来源。输出纯 Markdown 格式。
创作者特质: {creator_profile or '通用'}"""),
            _CM(role="user", content=f"""# 调研主题\n{query}\n\n# 来源列表\n{source_list}\n\n# 搜索结果\n{combined}\n\n请生成调研报告："""),
        ], temperature=0.7)

        report_md = response.content
        if source_urls:
            report_md += "\n\n---\n\n## 参考来源\n\n" + "\n\n".join(f"[{i+1}] {url}" for i, url in enumerate(source_urls))

        return report_md

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"调研执行失败: {str(e)}"


def _do_advance_phase(db: Session, project: Project, state: dict) -> dict:
    """推进到下一阶段"""
    phase_order = project.phase_order
    target_field = state.get("parsed_target_field", "")

    # 如果指定了目标阶段
    if target_field:
        phase_map = {
            "意图分析": "intent", "intent": "intent",
            "消费者调研": "research", "调研": "research", "research": "research",
            "内涵设计": "design_inner", "design_inner": "design_inner",
            "内涵生产": "produce_inner", "produce_inner": "produce_inner",
            "外延设计": "design_outer", "design_outer": "design_outer",
            "外延生产": "produce_outer", "produce_outer": "produce_outer",
            "评估": "evaluate", "evaluate": "evaluate",
        }
        target_phase = phase_map.get(target_field.strip(), "")
        if target_phase and target_phase in phase_order:
            prev = project.current_phase
            project.phase_status[prev] = "completed"
            project.current_phase = target_phase
            project.phase_status[target_phase] = "in_progress"
            db.commit()
            return {"message": f"✅ 已进入【{_get_phase_field_name(target_phase)}】阶段。", "phase": target_phase}

    # 默认推进到下一阶段
    try:
        idx = phase_order.index(project.current_phase)
        if idx >= len(phase_order) - 1:
            return {"message": "已经是最后一个阶段了。", "phase": project.current_phase}

        prev = project.current_phase
        next_phase = phase_order[idx + 1]
        project.phase_status[prev] = "completed"
        project.current_phase = next_phase
        project.phase_status[next_phase] = "in_progress"
        db.commit()
        return {"message": f"✅ 已进入【{_get_phase_field_name(next_phase)}】阶段。请在右侧对话框输入「开始」来生成内容。", "phase": next_phase}

    except ValueError:
        return {"message": "无法确定下一阶段。", "phase": project.current_phase}


@router.post("/advance")
async def advance_phase(
    request: ChatRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """推进到下一阶段（用户点击确认按钮后调用）"""
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    current_idx = project.phase_order.index(project.current_phase)
    if current_idx >= len(project.phase_order) - 1:
        return ChatResponseExtended(
            message_id="", message="已经是最后一个阶段了",
            phase=project.current_phase, phase_status=project.phase_status,
            waiting_for_human=False,
        )
    
    prev_phase = project.current_phase
    next_phase = project.phase_order[current_idx + 1]
    
    project.phase_status[prev_phase] = "completed"
    project.current_phase = next_phase
    project.phase_status[next_phase] = "in_progress"
    db.commit()
    
    enter_msg = ChatMessage(
        id=generate_uuid(),
        project_id=request.project_id,
        role="assistant",
        content=f"✅ 已进入【{_get_phase_field_name(next_phase)}】阶段。请在右侧对话框输入「开始」来生成内容。",
        message_metadata={"phase": next_phase},
    )
    db.add(enter_msg)
    db.commit()
    
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
