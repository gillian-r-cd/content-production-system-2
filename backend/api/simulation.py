# backend/api/simulation.py
# 功能: 消费者模拟API
# 主要路由: 模拟记录CRUD、人物小传获取
# 数据结构: SimulationRecord的创建、查询

"""
消费者模拟 API
管理模拟记录、人物小传选择
"""

from typing import Optional, List, Union
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    SimulationRecord,
    Simulator,
    Project,
    generate_uuid,
)
from core.models.content_block import ContentBlock


router = APIRouter()


# ============== Schemas ==============

class PersonaSchema(BaseModel):
    source: str = "custom"
    name: str = ""
    background: str = ""
    story: str = ""


class SimulationCreate(BaseModel):
    project_id: str
    simulator_id: str
    target_field_ids: List[str] = []
    persona: PersonaSchema


class SimulationResponse(BaseModel):
    id: str
    project_id: str
    simulator_id: str
    target_field_ids: List[str]
    persona: dict
    interaction_log: Union[list, dict]
    feedback: dict
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class PersonaFromResearch(BaseModel):
    name: str
    background: str
    story: str


# ============== Routes ==============

@router.get("/project/{project_id}", response_model=List[SimulationResponse])
def list_simulations(project_id: str, db: Session = Depends(get_db)):
    """获取项目的模拟记录列表"""
    records = (
        db.query(SimulationRecord)
        .filter(SimulationRecord.project_id == project_id)
        .order_by(SimulationRecord.created_at.desc())
        .all()
    )
    return [_to_response(r) for r in records]


@router.get("/{simulation_id}", response_model=SimulationResponse)
def get_simulation(simulation_id: str, db: Session = Depends(get_db)):
    """获取模拟记录详情"""
    record = db.query(SimulationRecord).filter(SimulationRecord.id == simulation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    return _to_response(record)


@router.post("/", response_model=SimulationResponse)
def create_simulation(data: SimulationCreate, db: Session = Depends(get_db)):
    """创建模拟记录"""
    # 验证项目存在
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证模拟器存在
    simulator = db.query(Simulator).filter(Simulator.id == data.simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Simulator not found")
    
    record = SimulationRecord(
        id=generate_uuid(),
        project_id=data.project_id,
        simulator_id=data.simulator_id,
        target_field_ids=data.target_field_ids,
        persona=data.persona.model_dump(),
        status="pending",
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return _to_response(record)


@router.delete("/{simulation_id}")
def delete_simulation(simulation_id: str, db: Session = Depends(get_db)):
    """删除模拟记录"""
    record = db.query(SimulationRecord).filter(SimulationRecord.id == simulation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    
    db.delete(record)
    db.commit()
    return {"message": "Deleted"}


@router.post("/{simulation_id}/run", response_model=SimulationResponse)
async def run_simulation_task(simulation_id: str, db: Session = Depends(get_db)):
    """
    执行模拟任务
    
    根据模拟记录的配置，实际运行模拟并更新结果
    """
    import time
    import json
    from core.tools import run_simulation
    from core.models import GenerationLog
    
    start_time = time.time()
    
    record = db.query(SimulationRecord).filter(SimulationRecord.id == simulation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    
    # 获取模拟器
    simulator = db.query(Simulator).filter(Simulator.id == record.simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Simulator not found")
    
    # 获取要模拟的内容（P0-1: 统一使用 ContentBlock）
    target_fields = db.query(ContentBlock).filter(
        ContentBlock.id.in_(record.target_field_ids),
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    
    if not target_fields:
        raise HTTPException(status_code=400, detail="No target fields found")
    
    # 合并字段内容
    content = "\n\n".join([
        f"## {f.name}\n{f.content}"
        for f in target_fields if f.content
    ])
    
    # 更新状态为运行中
    record.status = "running"
    db.commit()
    
    # 获取字段名称列表（用于对话式模拟的显示）
    content_field_names = [f.name for f in target_fields if f.name]
    
    error_msg = None
    try:
        # 运行模拟
        result = await run_simulation(
            simulator=simulator,
            content=content,
            persona=record.persona or {},
            content_field_names=content_field_names,
        )
        
        # 更新记录
        record.interaction_log = result.interaction_log
        record.feedback = {
            "scores": result.feedback.scores,
            "comments": result.feedback.comments,
            "overall": result.feedback.overall,
        }
        record.status = "completed" if result.success else "failed"
        
        if not result.success:
            error_msg = result.error
        
    except Exception as e:
        record.status = "failed"
        record.feedback = {"error": str(e)}
        error_msg = str(e)
    
    db.commit()
    db.refresh(record)
    
    # 记录到 GenerationLog
    duration_ms = int((time.time() - start_time) * 1000)
    
    # 构建完整的日志输入
    log_input = f"""[Simulation] {simulator.name} ({simulator.interaction_type})

[Persona]
{json.dumps(record.persona, ensure_ascii=False, indent=2) if record.persona else "无"}

[Target Fields]
{", ".join([f.name for f in target_fields])}

[Content]
{content[:2000]}{"..." if len(content) > 2000 else ""}"""
    
    # 构建日志输出
    log_output = json.dumps({
        "status": record.status,
        "feedback": record.feedback,
        "interaction_log_preview": str(record.interaction_log)[:1000] if record.interaction_log else None,
    }, ensure_ascii=False, indent=2)
    
    gen_log = GenerationLog(
        id=generate_uuid(),
        project_id=record.project_id,
        phase="simulate",
        operation=f"simulation_{simulator.interaction_type}",
        model="gpt-5.1",  # 或从配置获取
        prompt_input=log_input,
        prompt_output=log_output if not error_msg else f"Error: {error_msg}",
        tokens_used=0,  # 模拟器内部调用，无法精确统计
        duration_ms=duration_ms,
        cost=0.0,
    )
    db.add(gen_log)
    db.commit()
    
    return _to_response(record)


@router.get("/project/{project_id}/personas", response_model=list[PersonaFromResearch])
def get_personas_from_research(project_id: str, db: Session = Depends(get_db)):
    """
    从消费者调研中提取人物小传
    解析research阶段的字段内容（JSON格式），提取所有人物小传
    """
    import json
    
    # 获取消费者调研相关的 ContentBlock（P0-1: 统一使用 ContentBlock）
    research_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).filter(
        (ContentBlock.special_handler == "research") |
        (ContentBlock.name.in_(["消费者调研", "消费者调研报告"]))
    ).all()
    
    personas = []
    
    for field in research_blocks:
        content = field.content or ""
        if not content.strip():
            continue
        
        # 尝试解析JSON格式的消费者调研报告
        try:
            data = json.loads(content)
            
            # 检查是否有 personas 数组（标准消费者调研格式）
            if isinstance(data, dict) and "personas" in data:
                for p in data.get("personas", []):
                    if not isinstance(p, dict):
                        continue
                    
                    # 提取人物基本信息
                    name = p.get("name", "未命名人物")
                    basic_info = p.get("basic_info", {})
                    
                    # 构建背景描述
                    background_parts = []
                    if basic_info.get("age"):
                        background_parts.append(f"{basic_info['age']}岁")
                    if basic_info.get("gender"):
                        background_parts.append(basic_info["gender"])
                    if basic_info.get("city"):
                        background_parts.append(basic_info["city"])
                    if basic_info.get("occupation"):
                        background_parts.append(basic_info["occupation"])
                    if basic_info.get("income_level"):
                        background_parts.append(basic_info["income_level"])
                    
                    background = " | ".join(background_parts) if background_parts else "来自消费者调研"
                    
                    # 构建故事（背景 + 痛点）
                    story_parts = []
                    if p.get("background"):
                        story_parts.append(p["background"])
                    if p.get("pain_points") and isinstance(p["pain_points"], list):
                        story_parts.append("痛点: " + "; ".join(p["pain_points"][:3]))
                    
                    story = "\n\n".join(story_parts) if story_parts else ""
                    
                    personas.append(PersonaFromResearch(
                        name=name,
                        background=background,
                        story=story[:800] if story else "",
                    ))
                    
        except json.JSONDecodeError:
            # 非JSON格式，尝试简单文本解析（旧格式兼容）
            if "小传" in field.name or "人物" in field.name:
                personas.append(PersonaFromResearch(
                    name=field.name,
                    background=f"来自消费者调研 - {field.name}",
                    story=content[:500] if content else "",
                ))
    
    return personas


# ============== Helpers ==============

def _to_response(r: SimulationRecord) -> SimulationResponse:
    return SimulationResponse(
        id=r.id,
        project_id=r.project_id,
        simulator_id=r.simulator_id,
        target_field_ids=r.target_field_ids or [],
        persona=r.persona or {},
        interaction_log=r.interaction_log or [],
        feedback=r.feedback or {},
        status=r.status or "pending",
        created_at=r.created_at.isoformat() if r.created_at else "",
    )

