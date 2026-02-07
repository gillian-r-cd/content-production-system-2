# backend/core/models/creator_profile.py
# 功能: 创作者特质模型
# 主要类: CreatorProfile
# 数据结构: 存储创作者的个性化特质，作为所有内容生产的全局约束

"""
创作者特质模型
全局设置，在开始项目时先选创作者特质，作为项目所有字段的输入
"""

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel


class CreatorProfile(BaseModel):
    """
    创作者特质
    
    Attributes:
        name: 名称，如"专业严谨型"、"亲和幽默型"
        description: 特质描述
        traits: JSON格式的特质详情，自由格式，如:
            {
                "tone": "专业但不失亲和",
                "vocabulary": "行业术语适度使用",
                "personality": "理性、数据驱动",
                "taboos": ["过度营销", "夸大其词"]
            }
    """
    __tablename__ = "creator_profiles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[dict] = mapped_column(JSON, default=dict)

    # 关联的项目
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="creator_profile"
    )

    def to_prompt_context(self) -> str:
        """转换为提示词上下文"""
        lines = [f"## 创作者特质: {self.name}"]
        if self.description:
            lines.append(self.description)
        if self.traits:
            for key, value in self.traits.items():
                if isinstance(value, list):
                    lines.append(f"- {key}: {', '.join(value)}")
                else:
                    lines.append(f"- {key}: {value}")
        return "\n".join(lines)


