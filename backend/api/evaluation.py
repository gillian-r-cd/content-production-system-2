# backend/api/evaluation.py
# 功能: 评估API
# 主要路由: 运行评估、获取报告、管理建议采纳
# 数据结构: EvaluationRun, EvaluationReportResponse

"""
评估 API
运行项目评估、获取报告、管理修改建议
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Project,
    EvaluationTemplate,
    EvaluationReport,
    SimulationRecord,
    generate_uuid,
)
from core.models.content_block import ContentBlock
from core.tools import evaluate_project
from core.prompt_engine import prompt_engine


router = APIRouter()


# ============== Schemas ==============

class RunEvaluationRequest(BaseModel):
    """运行评估请求"""
    template_id: Optional[str] = None  # 不指定则使用默认模板


class SuggestionAdoptRequest(BaseModel):
    """采纳建议请求"""
    suggestion_id: str
    action_description: str  # 用户描述的操作


class EvaluationReportResponse(BaseModel):
    """评估报告响应"""
    id: str
    project_id: str
    template_id: Optional[str]
    scores: dict
    overall_score: float
    suggestions: list
    summary: str
    created_at: str

    model_config = {"from_attributes": True}


class EvaluationTemplateResponse(BaseModel):
    """评估模板响应"""
    id: str
    name: str
    description: str
    sections: list
    created_at: str

    model_config = {"from_attributes": True}


class TemplateCreate(BaseModel):
    """创建评估模板"""
    name: str
    description: str = ""
    sections: list = []


class TemplateUpdate(BaseModel):
    """更新评估模板"""
    name: Optional[str] = None
    description: Optional[str] = None
    sections: Optional[list] = None


# ============== Routes ==============

@router.get("/templates", response_model=list[EvaluationTemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    """获取评估模板列表"""
    templates = db.query(EvaluationTemplate).all()
    return [_to_template_response(t) for t in templates]


@router.post("/templates", response_model=EvaluationTemplateResponse)
def create_template(data: TemplateCreate, db: Session = Depends(get_db)):
    """创建评估模板"""
    template = EvaluationTemplate(
        id=generate_uuid(),
        name=data.name,
        description=data.description,
        sections=data.sections,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _to_template_response(template)


@router.put("/templates/{template_id}", response_model=EvaluationTemplateResponse)
def update_template(
    template_id: str,
    update: TemplateUpdate,
    db: Session = Depends(get_db),
):
    """更新评估模板"""
    template = db.query(EvaluationTemplate).filter(
        EvaluationTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    db.commit()
    db.refresh(template)
    return _to_template_response(template)


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    """删除评估模板"""
    template = db.query(EvaluationTemplate).filter(
        EvaluationTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db.delete(template)
    db.commit()
    return {"message": "Deleted"}


@router.get("/project/{project_id}/reports", response_model=list[EvaluationReportResponse])
def list_reports(project_id: str, db: Session = Depends(get_db)):
    """获取项目的评估报告列表"""
    reports = (
        db.query(EvaluationReport)
        .filter(EvaluationReport.project_id == project_id)
        .order_by(EvaluationReport.created_at.desc())
        .all()
    )
    return [_to_report_response(r) for r in reports]


@router.get("/reports/{report_id}", response_model=EvaluationReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)):
    """获取评估报告详情"""
    report = db.query(EvaluationReport).filter(
        EvaluationReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _to_report_response(report)


@router.post("/project/{project_id}/run", response_model=EvaluationReportResponse)
async def run_evaluation(
    project_id: str,
    request: RunEvaluationRequest,
    db: Session = Depends(get_db),
):
    """
    运行项目评估
    
    基于评估模板对项目进行全面评估，生成评估报告
    """
    # 获取项目
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取评估模板
    template = None
    if request.template_id:
        template = db.query(EvaluationTemplate).filter(
            EvaluationTemplate.id == request.template_id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
    else:
        # 使用默认模板
        template = db.query(EvaluationTemplate).first()
        if not template:
            # 创建默认模板
            template = EvaluationTemplate(
                id=generate_uuid(),
                name="标准评估模板",
                description="默认的项目评估模板",
                sections=[
                    {
                        "id": "intent_alignment",
                        "name": "意图对齐度",
                        "weight": 0.25,
                        "grader_prompt": "评估内容是否准确传达了项目意图",
                        "metrics": [
                            {"name": "核心信息覆盖", "type": "score_1_10"},
                            {"name": "偏离程度", "type": "score_1_10"},
                        ],
                    },
                    {
                        "id": "user_match",
                        "name": "用户匹配度",
                        "weight": 0.25,
                        "grader_prompt": "评估内容是否适合目标用户",
                        "metrics": [
                            {"name": "痛点回应", "type": "score_1_10"},
                            {"name": "价值传递", "type": "score_1_10"},
                        ],
                    },
                    {
                        "id": "quality",
                        "name": "内容质量",
                        "weight": 0.30,
                        "grader_prompt": "评估内容的专业性和完整性",
                        "metrics": [
                            {"name": "专业性", "type": "score_1_10"},
                            {"name": "完整性", "type": "score_1_10"},
                            {"name": "可读性", "type": "score_1_10"},
                        ],
                    },
                    {
                        "id": "simulation",
                        "name": "模拟反馈",
                        "weight": 0.20,
                        "source": "simulation_records",
                        "metrics": [],
                    },
                ],
            )
            db.add(template)
            db.commit()
    
    # 获取项目字段（P0-1: 统一使用 ContentBlock）
    fields = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.status == "completed",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    
    # 获取模拟记录
    simulation_records = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == project_id,
        SimulationRecord.status == "completed",
    ).all()
    
    # 构建项目上下文
    gc = prompt_engine.build_golden_context(project)
    project_context = gc.to_prompt()
    
    # 运行评估
    result = await evaluate_project(
        template=template,
        project=project,
        fields=fields,
        simulation_records=simulation_records,
        project_context=project_context,
    )
    
    # 创建报告
    report = EvaluationReport(
        id=generate_uuid(),
        project_id=project_id,
        template_id=template.id,
        scores={
            section_id: {
                "scores": score.scores,
                "comments": score.comments,
                "summary": score.summary,
            }
            for section_id, score in result.section_scores.items()
        },
        overall_score=result.overall_score,
        suggestions=[s.model_dump() for s in result.suggestions],
        summary=result.summary,
    )
    
    db.add(report)
    
    # 更新项目阶段状态
    if project.phase_status:
        project.phase_status = {**project.phase_status, "evaluate": "completed"}
    
    db.commit()
    db.refresh(report)
    
    return _to_report_response(report)


@router.post("/reports/{report_id}/adopt", response_model=EvaluationReportResponse)
async def adopt_suggestion(
    report_id: str,
    request: SuggestionAdoptRequest,
    db: Session = Depends(get_db),
):
    """
    采纳修改建议
    
    标记建议为已采纳，记录操作描述
    """
    report = db.query(EvaluationReport).filter(
        EvaluationReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # 查找并更新建议
    suggestions = report.suggestions or []
    found = False
    
    for suggestion in suggestions:
        if suggestion.get("id") == request.suggestion_id:
            suggestion["adopted"] = True
            suggestion["action_taken"] = request.action_description
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    report.suggestions = suggestions
    db.commit()
    db.refresh(report)
    
    return _to_report_response(report)


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    """删除评估报告"""
    report = db.query(EvaluationReport).filter(
        EvaluationReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    db.delete(report)
    db.commit()
    return {"message": "Deleted"}


# ============== Helpers ==============

def _to_template_response(t: EvaluationTemplate) -> EvaluationTemplateResponse:
    return EvaluationTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description or "",
        sections=t.sections or [],
        created_at=t.created_at.isoformat() if t.created_at else "",
    )


def _to_report_response(r: EvaluationReport) -> EvaluationReportResponse:
    return EvaluationReportResponse(
        id=r.id,
        project_id=r.project_id,
        template_id=r.template_id,
        scores=r.scores or {},
        overall_score=r.overall_score or 0.0,
        suggestions=r.suggestions or [],
        summary=r.summary or "",
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


