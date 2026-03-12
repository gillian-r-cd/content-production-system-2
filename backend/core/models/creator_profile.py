# backend/core/models/creator_profile.py
# 功能: 创作者特质模型
# 主要类: CreatorProfile
# 数据结构: 存储创作者的个性化特质，作为所有内容生产的全局约束

"""
创作者特质模型
全局设置，在开始项目时先选创作者特质，作为项目所有字段的输入
"""

from typing import Optional

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.localization import DEFAULT_LOCALE, normalize_locale
from core.locale_text import rt
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
    stable_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default=DEFAULT_LOCALE, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[dict] = mapped_column(JSON, default=dict)

    # 关联的项目
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="creator_profile"
    )

    def to_prompt_context(self, locale: Optional[str] = None) -> str:
        """转换为提示词上下文。"""
        target_locale = normalize_locale(locale or getattr(self, "locale", DEFAULT_LOCALE))
        lines = [
            rt(target_locale, "creator_profile.section_header"),
            rt(target_locale, "creator_profile.name_line", name=self.name),
        ]
        if self.description:
            lines.append(self.description)
        if self.traits:
            for key, value in self.traits.items():
                runtime_key = f"creator_profile.trait.{key}"
                label = rt(target_locale, runtime_key)
                if label == runtime_key:
                    label = str(key)
                if isinstance(value, list):
                    value_text = ", ".join(str(item) for item in value)
                else:
                    value_text = str(value)
                if value_text:
                    lines.append(f"- {label}: {value_text}")
        return "\n".join(lines)


