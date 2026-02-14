# backend/scripts/migrate_add_constraints.py
# 功能: 为 project_fields 表添加 constraints 列
# 运行: python -m scripts.migrate_add_constraints

"""
数据库迁移：添加 constraints 列到 project_fields 表
"""

import sys
from pathlib import Path

# 确保可以导入core模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_engine
from sqlalchemy import text


def migrate():
    """添加 constraints 和 need_review 列"""
    print("Migrating database...")
    
    engine = get_engine()
    
    with engine.connect() as conn:
        # 检查列是否已存在
        result = conn.execute(text("PRAGMA table_info(project_fields)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "constraints" not in columns:
            print("  Adding constraints column...")
            conn.execute(text(
                "ALTER TABLE project_fields ADD COLUMN constraints JSON DEFAULT '{\"max_length\": null, \"output_format\": \"markdown\", \"structure\": null, \"example\": null}'"
            ))
            conn.commit()
            print("  [OK] constraints column added")
        else:
            print("  [SKIP] constraints column exists")
        
        if "need_review" not in columns:
            print("  Adding need_review column...")
            conn.execute(text(
                "ALTER TABLE project_fields ADD COLUMN need_review BOOLEAN DEFAULT 1"
            ))
            conn.commit()
            print("  [OK] need_review column added")
        else:
            print("  [SKIP] need_review column exists")
    
    print("Migration complete!")


if __name__ == "__main__":
    migrate()

