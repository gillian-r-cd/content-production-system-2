# backend/api/fields.py
# 功能: 字段管理API
# 主要路由: CRUD操作、生成、依赖管理
# 数据结构: FieldCreate, FieldUpdate, FieldResponse

"""
字段管理 API
"""

from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from core.database import get_db
from core.models import ProjectField, Project, FieldTemplate, generate_uuid
from core.tools import generate_field, generate_field_stream, resolve_field_order
from core.prompt_engine import prompt_engine, PromptContext, GoldenContext


router = APIRouter()


# ============== Schemas ==============

class FieldCreate(BaseModel):
    """创建字段请求"""
    project_id: str
    phase: str
    name: str
    field_type: str = "text"
    ai_prompt: str = ""
    pre_questions: List[str] = []
    dependencies: dict = {"depends_on": [], "dependency_type": "all"}
    template_id: Optional[str] = None


class FieldUpdate(BaseModel):
    """更新字段请求"""
    name: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    ai_prompt: Optional[str] = None
    pre_answers: Optional[dict] = None
    dependencies: Optional[dict] = None


class FieldResponse(BaseModel):
    """字段响应"""
    id: str
    project_id: str
    phase: str
    name: str
    field_type: str
    content: str
    status: str
    ai_prompt: str
    pre_questions: list
    pre_answers: dict
    dependencies: dict
    template_id: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    """生成请求"""
    pre_answers: dict = {}


# ============== Routes ==============

@router.get("/project/{project_id}", response_model=list[FieldResponse])
def list_project_fields(
    project_id: str,
    phase: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取项目的字段列表"""
    query = db.query(ProjectField).filter(ProjectField.project_id == project_id)
    if phase:
        query = query.filter(ProjectField.phase == phase)
    
    fields = query.all()
    return [_field_to_response(f) for f in fields]


@router.post("/", response_model=FieldResponse)
def create_field(
    field: FieldCreate,
    db: Session = Depends(get_db),
):
    """创建字段"""
    # 如果有模板，从模板获取配置
    if field.template_id:
        template = db.query(FieldTemplate).filter(
            FieldTemplate.id == field.template_id
        ).first()
        if template:
            # 从模板获取字段配置
            for t_field in template.fields:
                if t_field.get("name") == field.name:
                    field.ai_prompt = field.ai_prompt or t_field.get("ai_prompt", "")
                    field.pre_questions = field.pre_questions or t_field.get("pre_questions", [])
                    break
    
    db_field = ProjectField(
        id=generate_uuid(),
        project_id=field.project_id,
        template_id=field.template_id,
        phase=field.phase,
        name=field.name,
        field_type=field.field_type,
        ai_prompt=field.ai_prompt,
        pre_questions=field.pre_questions,
        dependencies=field.dependencies,
        status="pending",
    )
    
    db.add(db_field)
    db.commit()
    db.refresh(db_field)
    
    return _field_to_response(db_field)


@router.get("/{field_id}", response_model=FieldResponse)
def get_field(
    field_id: str,
    db: Session = Depends(get_db),
):
    """获取字段详情"""
    field = db.query(ProjectField).filter(ProjectField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return _field_to_response(field)


@router.put("/{field_id}", response_model=FieldResponse)
def update_field(
    field_id: str,
    update: FieldUpdate,
    db: Session = Depends(get_db),
):
    """更新字段"""
    field = db.query(ProjectField).filter(ProjectField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(field, key, value)
    
    db.commit()
    db.refresh(field)
    
    return _field_to_response(field)


@router.delete("/{field_id}")
def delete_field(
    field_id: str,
    db: Session = Depends(get_db),
):
    """删除字段"""
    field = db.query(ProjectField).filter(ProjectField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    db.delete(field)
    db.commit()
    
    return {"message": "Field deleted"}


@router.post("/{field_id}/generate", response_model=FieldResponse)
async def generate_field_content(
    field_id: str,
    request: GenerateRequest,
    db: Session = Depends(get_db),
):
    """生成字段内容"""
    field = db.query(ProjectField).filter(ProjectField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    project = db.query(Project).filter(Project.id == field.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 检查依赖是否满足
    depends_on = field.dependencies.get("depends_on", [])
    if depends_on:
        completed_fields = db.query(ProjectField).filter(
            ProjectField.id.in_(depends_on),
            ProjectField.status == "completed"
        ).all()
        
        dep_type = field.dependencies.get("dependency_type", "all")
        if dep_type == "all" and len(completed_fields) < len(depends_on):
            raise HTTPException(
                status_code=400, 
                detail="Dependencies not satisfied"
            )
    
    # 更新预回答
    field.pre_answers = request.pre_answers
    field.status = "generating"
    db.commit()
    
    # 构建上下文
    gc = GoldenContext(
        creator_profile=project.golden_context.get("creator_profile", ""),
        intent=project.golden_context.get("intent", ""),
        consumer_personas=project.golden_context.get("consumer_personas", ""),
    )
    
    # 获取依赖字段内容
    dep_fields = db.query(ProjectField).filter(
        ProjectField.id.in_(depends_on)
    ).all() if depends_on else []
    
    context = prompt_engine.build_prompt_context(
        project=project,
        phase=field.phase,
        golden_context=gc,
        dependent_fields=dep_fields,
    )
    
    # 生成
    result = await generate_field(field, context)
    
    if result.success:
        field.content = result.content
        field.status = "completed"
    else:
        field.status = "failed"
    
    db.commit()
    db.refresh(field)
    
    return _field_to_response(field)


@router.post("/{field_id}/generate/stream")
async def generate_field_stream_api(
    field_id: str,
    request: GenerateRequest,
    db: Session = Depends(get_db),
):
    """流式生成字段内容"""
    field = db.query(ProjectField).filter(ProjectField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    project = db.query(Project).filter(Project.id == field.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 更新预回答和状态
    field.pre_answers = request.pre_answers
    field.status = "generating"
    db.commit()
    
    # 构建上下文
    gc = GoldenContext(
        creator_profile=project.golden_context.get("creator_profile", ""),
        intent=project.golden_context.get("intent", ""),
        consumer_personas=project.golden_context.get("consumer_personas", ""),
    )
    
    depends_on = field.dependencies.get("depends_on", [])
    dep_fields = db.query(ProjectField).filter(
        ProjectField.id.in_(depends_on)
    ).all() if depends_on else []
    
    context = prompt_engine.build_prompt_context(
        project=project,
        phase=field.phase,
        golden_context=gc,
        dependent_fields=dep_fields,
    )
    
    async def stream_generator():
        content_parts = []
        try:
            async for chunk in generate_field_stream(field, context):
                content_parts.append(chunk)
                data = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            
            # 保存完整内容
            full_content = "".join(content_parts)
            field.content = full_content
            field.status = "completed"
            db.commit()
            
            yield f"data: {json.dumps({'done': True, 'field_id': field_id})}\n\n"
            
        except Exception as e:
            field.status = "failed"
            db.commit()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
    )


@router.get("/project/{project_id}/order")
def get_field_order(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取字段生成顺序（基于依赖关系）"""
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id
    ).all()
    
    try:
        order = resolve_field_order(fields)
        return {
            "order": [
                [{"id": f.id, "name": f.name} for f in group]
                for group in order
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class BatchGenerateRequest(BaseModel):
    """批量生成请求"""
    phase: Optional[str] = None  # 不指定则生成所有pending字段
    respect_autonomy: bool = True  # 是否尊重Agent自主权检查点


class BatchGenerateResponse(BaseModel):
    """批量生成响应"""
    generated: List[str]  # 成功生成的字段ID
    failed: List[dict]  # 失败的字段 {"id": str, "error": str}
    pending: List[str]  # 等待人工确认的字段ID
    completed: bool  # 是否全部完成


@router.post("/project/{project_id}/generate-batch", response_model=BatchGenerateResponse)
async def batch_generate_fields(
    project_id: str,
    request: BatchGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    一键生成（批量生成字段）
    
    按依赖顺序批量生成所有pending状态的字段。
    如果respect_autonomy=True，会在需要人工确认的阶段暂停。
    """
    from core.tools import generate_fields_parallel
    
    # 获取项目
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取待生成的字段
    query = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.status == "pending",
    )
    if request.phase:
        query = query.filter(ProjectField.phase == request.phase)
    
    pending_fields = query.all()
    
    if not pending_fields:
        return BatchGenerateResponse(
            generated=[],
            failed=[],
            pending=[],
            completed=True,
        )
    
    # 按依赖顺序分组
    try:
        ordered_groups = resolve_field_order(pending_fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 构建上下文
    gc = GoldenContext(
        creator_profile=project.golden_context.get("creator_profile", "") if project.golden_context else "",
        intent=project.golden_context.get("intent", "") if project.golden_context else "",
        consumer_personas=project.golden_context.get("consumer_personas", "") if project.golden_context else "",
    )
    
    generated_ids = []
    failed_items = []
    pending_ids = []
    
    # 获取所有字段用于依赖上下文
    all_fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id
    ).all()
    fields_by_id = {f.id: f for f in all_fields}
    
    # 逐组生成
    for group in ordered_groups:
        # 检查自主权（如果需要）
        if request.respect_autonomy:
            phases_in_group = set(f.phase for f in group)
            for phase in phases_in_group:
                if project.agent_autonomy and project.agent_autonomy.get(phase, True):
                    # 需要人工确认，暂停
                    pending_ids.extend([f.id for f in group])
                    continue
        
        # 为每个字段构建上下文
        for field in group:
            # 获取依赖字段
            depends_on = field.dependencies.get("depends_on", []) if field.dependencies else []
            dep_fields = [fields_by_id[dep_id] for dep_id in depends_on if dep_id in fields_by_id]
            
            context = prompt_engine.build_prompt_context(
                project=project,
                phase=field.phase,
                golden_context=gc,
                dependent_fields=dep_fields,
            )
            
            # 更新状态
            field.status = "generating"
            db.commit()
            
            # 生成
            result = await generate_field(field, context)
            
            if result.success:
                field.content = result.content
                field.status = "completed"
                generated_ids.append(field.id)
                # 更新缓存
                fields_by_id[field.id] = field
            else:
                field.status = "failed"
                failed_items.append({
                    "id": field.id,
                    "name": field.name,
                    "error": result.error or "Unknown error",
                })
            
            db.commit()
    
    return BatchGenerateResponse(
        generated=generated_ids,
        failed=failed_items,
        pending=pending_ids,
        completed=len(pending_ids) == 0 and len(failed_items) == 0,
    )


# ============== Helpers ==============

def _field_to_response(field: ProjectField) -> FieldResponse:
    """转换为响应格式"""
    return FieldResponse(
        id=field.id,
        project_id=field.project_id,
        phase=field.phase,
        name=field.name,
        field_type=field.field_type,
        content=field.content or "",
        status=field.status,
        ai_prompt=field.ai_prompt or "",
        pre_questions=field.pre_questions or [],
        pre_answers=field.pre_answers or {},
        dependencies=field.dependencies or {"depends_on": [], "dependency_type": "all"},
        template_id=field.template_id,
        created_at=field.created_at.isoformat() if field.created_at else "",
        updated_at=field.updated_at.isoformat() if field.updated_at else "",
    )

