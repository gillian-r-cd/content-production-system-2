# backend/api/simulation.py
# 功能: 消费者模拟API
# 主要路由: 模拟记录CRUD、人物小传获取
# 数据结构: SimulationRecord的创建、查询

"""
消费者模拟 API
管理模拟记录、人物小传选择
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    SimulationRecord,
    Simulator,
    ProjectField,
    Project,
    generate_uuid,
)


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
    target_field_ids: list[str] = []
    persona: PersonaSchema


class SimulationResponse(BaseModel):
    id: str
    project_id: str
    simulator_id: str
    target_field_ids: list[str]
    persona: dict
    interaction_log: list | dict
    feedback: dict
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class PersonaFromResearch(BaseModel):
    name: str
    background: str
    story: str


# ============== Routes ==============

@router.get("/project/{project_id}", response_model=list[SimulationResponse])
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
    from core.tools import run_simulation
    
    record = db.query(SimulationRecord).filter(SimulationRecord.id == simulation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation record not found")
    
    # 获取模拟器
    simulator = db.query(Simulator).filter(Simulator.id == record.simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Simulator not found")
    
    # 获取要模拟的内容
    target_fields = db.query(ProjectField).filter(
        ProjectField.id.in_(record.target_field_ids)
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
    
    try:
        # 运行模拟
        result = await run_simulation(
            simulator=simulator,
            content=content,
            persona=record.persona or {},
        )
        
        # 更新记录
        record.interaction_log = result.interaction_log
        record.feedback = {
            "scores": result.feedback.scores,
            "comments": result.feedback.comments,
            "overall": result.feedback.overall,
        }
        record.status = "completed" if result.success else "failed"
        
    except Exception as e:
        record.status = "failed"
        record.feedback = {"error": str(e)}
    
    db.commit()
    db.refresh(record)
    
    return _to_response(record)


@router.get("/project/{project_id}/personas", response_model=list[PersonaFromResearch])
def get_personas_from_research(project_id: str, db: Session = Depends(get_db)):
    """
    从消费者调研中提取人物小传
    解析research阶段的字段内容，提取人物小传
    """
    # 获取消费者调研阶段的字段
    research_fields = (
        db.query(ProjectField)
        .filter(
            ProjectField.project_id == project_id,
            ProjectField.phase == "research",
            ProjectField.status == "completed",
        )
        .all()
    )
    
    personas = []
    
    for field in research_fields:
        # 尝试从字段内容中提取人物小传
        # 人物小传通常以"人物小传"、"典型用户"等关键词开始
        content = field.content or ""
        
        # 简单的解析逻辑：查找包含"小传"的段落
        if "小传" in field.name or "人物" in field.name or "用户" in field.name:
            # 整个字段作为一个人物
            personas.append(PersonaFromResearch(
                name=field.name,
                background=f"来自消费者调研 - {field.name}",
                story=content[:500] if content else "",
            ))
        elif "小传" in content:
            # 尝试按段落分割提取多个人物
            paragraphs = content.split("\n\n")
            current_persona = None
            
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                    
                # 检测人物标题
                if any(marker in p for marker in ["人物", "小传", "用户画像", "典型用户"]):
                    if current_persona:
                        personas.append(current_persona)
                    
                    # 提取人物名称（通常在第一行）
                    lines = p.split("\n")
                    name = lines[0].strip("# ").strip("：:").strip()
                    story = "\n".join(lines[1:]) if len(lines) > 1 else ""
                    
                    current_persona = PersonaFromResearch(
                        name=name[:50],
                        background=f"来自: {field.name}",
                        story=story[:500],
                    )
                elif current_persona:
                    # 追加到当前人物的故事
                    current_persona.story += "\n" + p[:200]
            
            if current_persona:
                personas.append(current_persona)
    
    # 如果没有找到，返回空列表
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

