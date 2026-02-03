# backend/core/models/base.py
# 功能: 基础模型类，提供通用字段和方法
# 主要类: BaseModel (包含id, created_at, updated_at)
# 数据结构: 所有模型的基类

"""
基础模型类
所有数据模型都继承自此类，自动获得id、时间戳等通用字段
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def generate_uuid() -> str:
    """生成UUID字符串"""
    return str(uuid.uuid4())


class BaseModel(Base):
    """
    抽象基础模型
    提供: id (UUID), created_at, updated_at
    """
    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        """转换为字典（用于API响应）"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

