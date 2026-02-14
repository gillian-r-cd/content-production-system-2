# backend/scripts/migrate_add_digest.py
# 功能: 为 project_fields 和 content_blocks 表添加 digest 列
# 运行: python -m scripts.migrate_add_digest

"""
数据库迁移：添加 digest 列到 project_fields 和 content_blocks 表
用于内容块摘要索引（digest_service 自动生成）
"""

import sys
from pathlib import Path

# 确保可以导入core模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_engine
from sqlalchemy import text


def migrate():
    """添加 digest 列到 project_fields 和 content_blocks"""
    print("Migrating database — adding digest columns...")

    engine = get_engine()

    with engine.connect() as conn:
        # ── project_fields ──
        result = conn.execute(text("PRAGMA table_info(project_fields)"))
        columns = [row[1] for row in result.fetchall()]

        if "digest" not in columns:
            print("  Adding digest column to project_fields...")
            conn.execute(text(
                "ALTER TABLE project_fields ADD COLUMN digest TEXT"
            ))
            conn.commit()
            print("  [OK] project_fields.digest added")
        else:
            print("  [SKIP] project_fields.digest exists")

        # ── content_blocks ──
        result = conn.execute(text("PRAGMA table_info(content_blocks)"))
        columns = [row[1] for row in result.fetchall()]

        if "digest" not in columns:
            print("  Adding digest column to content_blocks...")
            conn.execute(text(
                "ALTER TABLE content_blocks ADD COLUMN digest TEXT"
            ))
            conn.commit()
            print("  [OK] content_blocks.digest added")
        else:
            print("  [SKIP] content_blocks.digest exists")

    print("Migration complete!")


if __name__ == "__main__":
    migrate()
