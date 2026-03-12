# backend/core/models/channel.py
# 功能: 渠道模型，用于外延设计
# 主要类: Channel
# 数据结构: 存储渠道信息、提示词模板

"""
渠道模型
用于外延设计，预设常用渠道如销售PPT、小红书、微信公众号等
"""

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.localization import DEFAULT_LOCALE, normalize_locale
from core.models.base import BaseModel


class Channel(BaseModel):
    """
    渠道
    
    Attributes:
        name: 渠道名称
        description: 渠道描述
        platform: 平台类型（如social/doc/video）
        prompt_template: 针对该渠道的内容生成提示词模板
        constraints: 渠道限制（如字数、格式要求）
        examples: 示例内容
    """
    __tablename__ = "channels"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default=DEFAULT_LOCALE, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(50), default="other")
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "max_length": None,
            "format": "markdown",
            "style": None,
        }
    )
    examples: Mapped[list] = mapped_column(JSON, default=list)

    def to_prompt_context(self) -> str:
        """转换为提示词上下文"""
        locale = normalize_locale(getattr(self, "locale", DEFAULT_LOCALE))
        channel_title = "## 対象チャネル" if locale == "ja-JP" else "## 目标渠道"
        requirement_title = "### チャネル要件" if locale == "ja-JP" else "### 渠道要求"
        max_length_label = "文字数上限" if locale == "ja-JP" else "字数限制"
        format_label = "形式要件" if locale == "ja-JP" else "格式要求"
        style_label = "文体要件" if locale == "ja-JP" else "风格要求"
        lines = [f"{channel_title}: {self.name}"]
        if self.description:
            lines.append(self.description)
        
        if self.constraints:
            lines.append(f"\n{requirement_title}")
            if self.constraints.get("max_length"):
                lines.append(f"- {max_length_label}: {self.constraints['max_length']}")
            if self.constraints.get("format"):
                lines.append(f"- {format_label}: {self.constraints['format']}")
            if self.constraints.get("style"):
                lines.append(f"- {style_label}: {self.constraints['style']}")
        
        return "\n".join(lines)


