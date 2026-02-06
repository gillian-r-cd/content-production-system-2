# backend/scripts/migrate_eval_v2.py
# 功能: Eval V2 数据库迁移 - 创建 eval_tasks 表，更新 eval_trials 和 simulators 表
# 主要操作:
#   1. 创建 eval_tasks 表
#   2. 给 eval_trials 表添加 eval_task_id 和 llm_calls 列
#   3. 给 simulators 表添加 simulator_type/interaction_mode/grader_template/feedback_mode/is_preset 列
#   4. 更新综合评估字段模板为新版

"""
Eval V2 迁移脚本
运行: cd backend && python -m scripts.migrate_eval_v2
"""

import sys
import os
from pathlib import Path

# Windows UTF-8 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_engine, get_session_maker
from core.models import generate_uuid, FieldTemplate
from sqlalchemy import text


def migrate():
    engine = get_engine()
    
    with engine.connect() as conn:
        # ===== 1. 创建 eval_tasks 表 =====
        print("[1/4] 创建 eval_tasks 表...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eval_tasks (
                id VARCHAR(36) PRIMARY KEY,
                eval_run_id VARCHAR(36) NOT NULL,
                name VARCHAR(200) NOT NULL,
                simulator_type VARCHAR(50) DEFAULT 'coach',
                interaction_mode VARCHAR(50) DEFAULT 'review',
                simulator_config JSON DEFAULT '{}',
                persona_config JSON DEFAULT '{}',
                target_block_ids JSON DEFAULT '[]',
                grader_config JSON DEFAULT '{}',
                order_index INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending',
                error TEXT DEFAULT '',
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (eval_run_id) REFERENCES eval_runs(id)
            )
        """))
        print("  ✓ eval_tasks 表已创建")
        
        # ===== 2. 给 eval_trials 添加新列 =====
        print("[2/4] 更新 eval_trials 表...")
        
        # 检查列是否存在
        try:
            conn.execute(text("SELECT eval_task_id FROM eval_trials LIMIT 1"))
            print("  - eval_task_id 列已存在，跳过")
        except Exception:
            conn.execute(text("ALTER TABLE eval_trials ADD COLUMN eval_task_id VARCHAR(36)"))
            print("  ✓ 添加了 eval_task_id 列")
        
        try:
            conn.execute(text("SELECT llm_calls FROM eval_trials LIMIT 1"))
            print("  - llm_calls 列已存在，跳过")
        except Exception:
            conn.execute(text("ALTER TABLE eval_trials ADD COLUMN llm_calls JSON DEFAULT '[]'"))
            print("  ✓ 添加了 llm_calls 列")
        
        # ===== 3. 给 simulators 添加新列 =====
        print("[3/4] 更新 simulators 表...")
        
        new_columns = [
            ("simulator_type", "VARCHAR(50) DEFAULT 'custom'"),
            ("interaction_mode", "VARCHAR(50) DEFAULT 'review'"),
            ("grader_template", "TEXT DEFAULT ''"),
            ("feedback_mode", "VARCHAR(50) DEFAULT 'structured'"),
            ("is_preset", "BOOLEAN DEFAULT 0"),
        ]
        
        for col_name, col_def in new_columns:
            try:
                conn.execute(text(f"SELECT {col_name} FROM simulators LIMIT 1"))
                print(f"  - {col_name} 列已存在，跳过")
            except Exception:
                conn.execute(text(f"ALTER TABLE simulators ADD COLUMN {col_name} {col_def}"))
                print(f"  ✓ 添加了 {col_name} 列")
        
        conn.commit()
    
    # ===== 4. 更新综合评估字段模板 =====
    print("[4/4] 更新综合评估字段模板...")
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # 查找旧模板
        old_template = db.query(FieldTemplate).filter(
            FieldTemplate.name == "综合评估模板"
        ).first()
        
        new_fields = [
            {
                "name": "目标消费者画像",
                "type": "richtext",
                "ai_prompt": "从消费者调研中加载并管理目标消费者画像，也可手动创建新画像。",
                "pre_questions": [],
                "depends_on": [],
                "dependency_type": "all",
                "special_handler": "eval_persona_setup",
                "constraints": {},
            },
            {
                "name": "评估任务配置",
                "type": "richtext",
                "ai_prompt": "配置评估任务：选择模拟器类型、交互模式、消费者画像、评分维度。支持批量创建和全回归模板。",
                "pre_questions": [],
                "depends_on": ["目标消费者画像"],
                "dependency_type": "all",
                "special_handler": "eval_task_config",
                "constraints": {},
            },
            {
                "name": "评估报告",
                "type": "richtext",
                "ai_prompt": "统一评估报告：执行所有试验 → 各 Grader 评分 → 综合诊断。含完整 LLM 调用日志、分维度评分、交互记录。",
                "pre_questions": [],
                "depends_on": ["评估任务配置"],
                "dependency_type": "all",
                "special_handler": "eval_report",
                "constraints": {},
            },
        ]
        
        if old_template:
            old_template.fields = new_fields
            old_template.description = (
                "Eval V2 综合评估模板：目标画像 → 任务配置 → 评估报告（执行+评分+诊断一体化）。"
                "支持自定义 simulator × persona × grader 组合，并行执行无限 trial。"
            )
            print("  ✓ 更新了现有的综合评估模板")
        else:
            new_template = FieldTemplate(
                id=generate_uuid(),
                name="综合评估模板",
                description=(
                    "Eval V2 综合评估模板：目标画像 → 任务配置 → 执行过程(含完整LLM日志) → 评分报告 → 综合诊断。"
                    "支持自定义 simulator × persona × grader 组合，并行执行无限 trial。"
                ),
                category="评估",
                fields=new_fields,
            )
            db.add(new_template)
            print("  ✓ 创建了新的综合评估模板")
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        print(f"  ✗ 更新模板失败: {e}")
        raise
    finally:
        db.close()
    
    print("\n✅ Eval V2 迁移完成！")


if __name__ == "__main__":
    migrate()

