# backend/scripts/migrate_add_pre_questions.py
# 功能: 为 content_blocks 表添加 pre_questions 和 pre_answers 列
# 运行: python -m scripts.migrate_add_pre_questions

"""
数据库迁移：添加 pre_questions 和 pre_answers 列到 content_blocks 表
"""

import sys
from pathlib import Path

# 确保可以导入core模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_engine
from sqlalchemy import text


def migrate():
    """添加 pre_questions 和 pre_answers 字段"""
    print("Migrating database...")
    
    engine = get_engine()
    
    with engine.connect() as conn:
        # 检查列是否已存在
        result = conn.execute(text("PRAGMA table_info(content_blocks)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "pre_questions" not in columns:
            print("  Adding pre_questions column...")
            conn.execute(text(
                "ALTER TABLE content_blocks ADD COLUMN pre_questions JSON DEFAULT '[]'"
            ))
            conn.commit()
            print("  [OK] pre_questions column added")
        else:
            print("  [SKIP] pre_questions column exists")
        
        if "pre_answers" not in columns:
            print("  Adding pre_answers column...")
            conn.execute(text(
                "ALTER TABLE content_blocks ADD COLUMN pre_answers JSON DEFAULT '{}'"
            ))
            conn.commit()
            print("  [OK] pre_answers column added")
        else:
            print("  [SKIP] pre_answers column exists")
    
    print("Migration complete!")


if __name__ == "__main__":
    migrate()

