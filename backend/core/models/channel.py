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
        lines = [f"## 目标渠道: {self.name}"]
        if self.description:
            lines.append(self.description)
        
        if self.constraints:
            lines.append("\n### 渠道要求")
            if self.constraints.get("max_length"):
                lines.append(f"- 字数限制: {self.constraints['max_length']}")
            if self.constraints.get("format"):
                lines.append(f"- 格式要求: {self.constraints['format']}")
            if self.constraints.get("style"):
                lines.append(f"- 风格要求: {self.constraints['style']}")
        
        return "\n".join(lines)

