# backend/scripts/migrate_add_undo.py
# 功能: 添加撤回功能所需的数据库表和字段
# 包括: 1. content_blocks.deleted_at 字段  2. block_history 表

"""
迁移脚本：添加撤回功能支持
运行方式：cd backend && python -m scripts.migrate_add_undo
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from core.database import get_engine, Base
from core.models import ContentBlock, BlockHistory


def migrate():
    """执行迁移"""
    print("开始迁移：添加撤回功能支持...")
    
    engine = get_engine()
    with engine.connect() as conn:
        # 1. 检查 content_blocks 表是否存在 deleted_at 字段
        result = conn.execute(text(
            "PRAGMA table_info(content_blocks)"
        )).fetchall()
        
        columns = [row[1] for row in result]
        
        if "deleted_at" not in columns:
            print("  - 添加 content_blocks.deleted_at 字段...")
            conn.execute(text(
                "ALTER TABLE content_blocks ADD COLUMN deleted_at DATETIME DEFAULT NULL"
            ))
            print("    ✓ deleted_at 字段已添加")
        else:
            print("    ✓ deleted_at 字段已存在")
        
        # 2. 检查 block_history 表是否存在
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='block_history'"
        )).fetchone()
        
        if not result:
            print("  - 创建 block_history 表...")
            conn.execute(text("""
                CREATE TABLE block_history (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    action VARCHAR(20) NOT NULL,
                    block_id VARCHAR(36) NOT NULL,
                    block_snapshot JSON DEFAULT '{}',
                    children_snapshots JSON DEFAULT '[]',
                    undone BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """))
            print("    ✓ block_history 表已创建")
        else:
            print("    ✓ block_history 表已存在")
        
        conn.commit()
    
    print("\n✓ 迁移完成！")


if __name__ == "__main__":
    migrate()
