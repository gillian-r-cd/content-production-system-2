# backend/core/models/field_template.py
# 功能: 字段模板模型，全局共享的可复用模板
# 主要类: FieldTemplate
# 数据结构: 存储字段定义、依赖关系、AI提示词等

"""
字段模板模型
全局共享，可在多个项目中复用
每个模板包含若干字段定义及其关联关系
"""

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


class FieldTemplate(BaseModel):
    """
    字段模板（全局共享）
    
    Attributes:
        name: 模板名称
        description: 模板描述
        category: 分类（如"课程"、"文章"、"营销"）
        fields: 字段定义列表，每个字段包含:
            - name: 字段名
            - type: 类型 (text/richtext/list/structured)
            - ai_prompt: AI生成提示词
            - pre_questions: 生成前提问列表
            - depends_on: 依赖的字段名列表
            - dependency_type: 依赖类型 (all/any)
    
    Example fields:
        [
            {
                "name": "课程目标",
                "type": "text",
                "ai_prompt": "基于项目意图，明确课程的核心学习目标...",
                "pre_questions": ["目标学员的现有水平是？"],
                "depends_on": [],
                "dependency_type": "all"
            },
            {
                "name": "课程大纲",
                "type": "structured",
                "ai_prompt": "根据课程目标，设计详细的课程大纲...",
                "pre_questions": [],
                "depends_on": ["课程目标"],
                "dependency_type": "all"
            }
        ]
    """
    __tablename__ = "field_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="通用")
    fields: Mapped[list] = mapped_column(JSON, default=list)

    def get_field_names(self) -> list[str]:
        """获取所有字段名"""
        return [f["name"] for f in self.fields]

    def get_field_by_name(self, name: str) -> dict | None:
        """根据名称获取字段定义"""
        for field in self.fields:
            if field["name"] == name:
                return field
        return None

    def validate_dependencies(self) -> list[str]:
        """验证依赖关系，返回错误列表"""
        errors = []
        field_names = set(self.get_field_names())
        
        for field in self.fields:
            for dep in field.get("depends_on", []):
                if dep not in field_names:
                    errors.append(
                        f"字段'{field['name']}'依赖的'{dep}'不存在"
                    )
        
        # 检测循环依赖
        # TODO: 实现拓扑排序检测
        
        return errors

