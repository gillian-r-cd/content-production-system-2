# backend/core/models/evaluation.py
# 功能: 评估模板和评估报告模型
# 主要类: EvaluationTemplate, EvaluationReport
# 数据结构: 存储评估体系定义和评估结果

"""
评估模型
包含评估模板（可自定义）和评估报告
"""

from sqlalchemy import String, Text, JSON, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel


class EvaluationTemplate(BaseModel):
    """
    评估模板（可自定义）
    
    Attributes:
        name: 模板名称
        description: 描述
        sections: 评估板块列表，每个板块:
            - id: 唯一标识
            - name: 板块名称
            - grader_prompt: 评分提示词
            - weight: 权重（0-1）
            - metrics: 评估指标列表
                - name: 指标名称
                - type: "score_1_10" | "text_list" | "boolean" | "text"
            - sub_sections: 子板块（可嵌套）
            - source: 数据来源，如 "simulation_records" 表示从模拟记录汇总
    
    Example:
        {
            "sections": [
                {
                    "id": "intent_alignment",
                    "name": "意图对齐度",
                    "grader_prompt": "评估内容是否准确传达了原始意图...",
                    "weight": 0.25,
                    "metrics": [
                        {"name": "核心信息覆盖", "type": "score_1_10"},
                        {"name": "偏离点", "type": "text_list"}
                    ]
                }
            ]
        }
    """
    __tablename__ = "evaluation_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sections: Mapped[list] = mapped_column(JSON, default=list)

    def get_total_weight(self) -> float:
        """计算总权重（应该等于1）"""
        return sum(s.get("weight", 0) for s in self.sections)

    def validate(self) -> list[str]:
        """验证模板，返回错误列表"""
        errors = []
        total_weight = self.get_total_weight()
        if abs(total_weight - 1.0) > 0.01:
            errors.append(f"权重总和应为1，当前为{total_weight}")
        
        seen_ids = set()
        for section in self.sections:
            if section.get("id") in seen_ids:
                errors.append(f"重复的板块ID: {section.get('id')}")
            seen_ids.add(section.get("id"))
        
        return errors


class EvaluationReport(BaseModel):
    """
    评估报告
    
    Attributes:
        project_id: 所属项目
        template_id: 使用的评估模板
        scores: 各板块评分结果
            {section_id: {metric_name: value}}
        overall_score: 综合评分（加权平均）
        suggestions: 修改建议列表
            - id: 建议ID
            - section_id: 相关板块
            - content: 建议内容
            - priority: 优先级（high/medium/low）
            - adopted: 是否已采纳
            - action_taken: 采纳后的操作
        summary: 总结评语
    """
    __tablename__ = "evaluation_reports"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_templates.id"), nullable=True
    )
    
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")

    # 关联
    project: Mapped["Project"] = relationship(
        "Project", back_populates="evaluation_reports"
    )
    template: Mapped["EvaluationTemplate"] = relationship("EvaluationTemplate")

    def get_pending_suggestions(self) -> list[dict]:
        """获取未处理的建议"""
        return [s for s in self.suggestions if not s.get("adopted")]

    def adopt_suggestion(self, suggestion_id: str, action: str) -> bool:
        """采纳建议"""
        for suggestion in self.suggestions:
            if suggestion.get("id") == suggestion_id:
                suggestion["adopted"] = True
                suggestion["action_taken"] = action
                return True
        return False

