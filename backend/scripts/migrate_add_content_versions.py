# backend/scripts/migrate_add_content_versions.py
# 功能: 创建 content_versions 表，用于保存字段内容的历史版本
# 运行: python scripts/migrate_add_content_versions.py

"""
数据库迁移：添加 content_versions 表
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_engine, Base
from core.models.content_version import ContentVersion

def migrate():
    """创建 content_versions 表"""
    engine = get_engine()
    ContentVersion.__table__.create(engine, checkfirst=True)
    print("✅ content_versions 表已创建（如已存在则跳过）")

if __name__ == "__main__":
    migrate()
