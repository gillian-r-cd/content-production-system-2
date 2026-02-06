# backend/scripts/migrate_grader.py
# 功能: 创建 graders 表并插入预置评分器

"""
数据库迁移：创建 graders 表 + 预置评分器
运行方式: cd backend && python -m scripts.migrate_grader
"""

import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from core.database import get_engine, get_session_maker
from core.models.base import generate_uuid
from core.models.grader import Grader, PRESET_GRADERS

engine = get_engine()
SessionLocal = get_session_maker()


def run_migration():
    print("=== Grader 表迁移 ===")
    
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    # 1. 创建 graders 表
    if "graders" not in existing_tables:
        print("[1] 创建 graders 表...")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE graders (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    grader_type VARCHAR(30) DEFAULT 'content_only',
                    prompt_template TEXT DEFAULT '',
                    dimensions JSON DEFAULT '[]',
                    scoring_criteria JSON DEFAULT '{}',
                    is_preset BOOLEAN DEFAULT 0,
                    project_id VARCHAR(36),
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
        print("  -> graders 表创建成功")
    else:
        print("[1] graders 表已存在，跳过")
    
    # 2. 插入预置 Grader
    db = SessionLocal()
    try:
        existing_count = db.query(Grader).filter(Grader.is_preset == True).count()
        if existing_count > 0:
            print(f"[2] 已有 {existing_count} 个预置评分器，跳过插入")
        else:
            print(f"[2] 插入 {len(PRESET_GRADERS)} 个预置评分器...")
            for preset in PRESET_GRADERS:
                grader = Grader(
                    id=generate_uuid(),
                    name=preset["name"],
                    grader_type=preset["grader_type"],
                    prompt_template=preset["prompt_template"],
                    dimensions=preset["dimensions"],
                    scoring_criteria=preset["scoring_criteria"],
                    is_preset=preset["is_preset"],
                    project_id=None,
                )
                db.add(grader)
                print(f"  -> 创建预置: {preset['name']}")
            db.commit()
            print("  -> 预置评分器插入完成")
    finally:
        db.close()
    
    print("\n=== 迁移完成 ===")


if __name__ == "__main__":
    run_migration()

