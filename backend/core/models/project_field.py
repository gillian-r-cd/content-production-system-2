# backend/core/models/project_field.py
# 功能: 项目字段模型，存储实际生成的内容
# 主要类: ProjectField
# 数据结构: 项目中每个字段的实际内容、状态、依赖关系

"""
项目字段模型
存储项目中每个字段的实际内容
可以基于模板创建，也可以完全自定义
"""

from typing import Optional, Set, Dict, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project
    from core.models.field_template import FieldTemplate


# 字段状态
FIELD_STATUS = {
    "pending": "待生成",
    "generating": "生成中",
    "completed": "已完成",
    "failed": "生成失败",
}


class ProjectField(BaseModel):
    """
    项目字段（实际内容）
    
    Attributes:
        project_id: 所属项目
        template_id: 来源模板（可选）
        phase: 所属阶段 (intent/research/inner/outer)
        name: 字段名称
        field_type: 字段类型 (text/richtext/list/structured)
        content: 实际内容（Markdown格式）
        status: 状态
        ai_prompt: AI生成提示词（可覆盖模板）
        pre_questions: 生成前提问（可覆盖模板）
        pre_answers: 用户回答的提问
        dependencies: 依赖配置
            - depends_on: 依赖的字段ID列表
            - dependency_type: "all" 或 "any"
        generation_log_id: 最近一次生成日志ID
    """
    __tablename__ = "project_fields"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("field_templates.id"), nullable=True
    )
    
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), default="text")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    
    ai_prompt: Mapped[str] = mapped_column(Text, default="")
    pre_questions: Mapped[list] = mapped_column(JSON, default=list)
    pre_answers: Mapped[dict] = mapped_column(JSON, default=dict)
    dependencies: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"depends_on": [], "dependency_type": "all"}
    )
    # 生产约束配置
    # - max_length: 最大字数（如 500）
    # - output_format: 输出格式 (markdown / plain_text / json / list)
    # - structure: 结构模板（如 "标题 + 正文 + 总结"）
    # - example: 示例输出
    constraints: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "max_length": None,  # None = 不限制
            "output_format": "markdown",
            "structure": None,
            "example": None,
        }
    )
    # 是否需要人工确认（False = 依赖满足后自动生成，默认不需要确认）
    need_review: Mapped[bool] = mapped_column(default=False)
    generation_log_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    # 内容摘要（digest_service 自动生成，用于内容块索引）
    digest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 关联
    project: Mapped["Project"] = relationship(
        "Project", back_populates="fields"
    )
    template: Mapped["FieldTemplate"] = relationship("FieldTemplate")

    def can_generate(self, completed_field_ids: Set[str]) -> bool:
        """
        检查是否可以生成（依赖是否满足）
        
        Args:
            completed_field_ids: 已完成的字段ID集合
        """
        depends_on = self.dependencies.get("depends_on", [])
        if not depends_on:
            return True
        
        dep_type = self.dependencies.get("dependency_type", "all")
        
        if dep_type == "all":
            return all(dep_id in completed_field_ids for dep_id in depends_on)
        else:  # any
            return any(dep_id in completed_field_ids for dep_id in depends_on)

    def get_dependency_context(self, fields_by_id: dict) -> str:
        """
        获取依赖字段的内容作为上下文
        
        Args:
            fields_by_id: {field_id: ProjectField} 映射
        """
        depends_on = self.dependencies.get("depends_on", [])
        if not depends_on:
            return ""
        
        context_parts = []
        for dep_id in depends_on:
            if dep_id in fields_by_id:
                dep_field = fields_by_id[dep_id]
                if dep_field.content:
                    context_parts.append(
                        f"## {dep_field.name}\n{dep_field.content}"
                    )
        
        return "\n\n".join(context_parts)

