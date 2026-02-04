#!/usr/bin/env python3
"""
添加 use_flexible_architecture 字段到 projects 表的迁移脚本
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from core.database import get_engine

def migrate():
    """添加 use_flexible_architecture 字段"""
    engine = get_engine()
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM pragma_table_info('projects') 
            WHERE name='use_flexible_architecture'
        """))
        exists = result.scalar() > 0
        
        if exists:
            print("字段 use_flexible_architecture 已存在，跳过迁移")
            return
        
        # 添加字段
        conn.execute(text("""
            ALTER TABLE projects 
            ADD COLUMN use_flexible_architecture BOOLEAN DEFAULT 0
        """))
        conn.commit()
        print("✓ 已添加 use_flexible_architecture 字段到 projects 表")

if __name__ == "__main__":
    migrate()
