# backend/scripts/migrate_add_tool_prompts.py
# 功能: 添加 tool_prompts 字段到 agent_settings 表

"""
迁移脚本：添加 tool_prompts 字段
运行方式：cd backend && python -m scripts.migrate_add_tool_prompts
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from core.database import get_engine


def migrate():
    """执行迁移"""
    print("开始迁移：添加 tool_prompts 字段...")
    
    engine = get_engine()
    with engine.connect() as conn:
        # 检查字段是否存在
        result = conn.execute(text(
            "PRAGMA table_info(agent_settings)"
        )).fetchall()
        
        columns = [row[1] for row in result]
        
        if "tool_prompts" not in columns:
            print("  - 添加 agent_settings.tool_prompts 字段...")
            conn.execute(text(
                "ALTER TABLE agent_settings ADD COLUMN tool_prompts JSON DEFAULT '{}'"
            ))
            print("    ✓ tool_prompts 字段已添加")
        else:
            print("    ✓ tool_prompts 字段已存在")
        
        conn.commit()
    
    print("\n✓ 迁移完成！")


if __name__ == "__main__":
    migrate()
