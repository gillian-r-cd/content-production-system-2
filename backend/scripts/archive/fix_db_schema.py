# -*- coding: utf-8 -*-
"""修复数据库 schema - 添加缺失的列"""
from core.database import get_engine
from sqlalchemy import text

engine = get_engine()

# 需要添加的列
columns_to_add = [
    ("agent_settings", "tool_prompts", "JSON DEFAULT '{}'"),
    ("projects", "use_flexible_architecture", "BOOLEAN DEFAULT 0"),
    ("projects", "phase_template_id", "VARCHAR(36)"),
]

with engine.connect() as conn:
    for table, column, col_type in columns_to_add:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            conn.commit()
            print(f"[OK] Added {table}.{column}")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print(f"[SKIP] {table}.{column} already exists")
            else:
                print(f"[WARN] {table}.{column}: {e}")

print("\nDatabase schema fixed!")

