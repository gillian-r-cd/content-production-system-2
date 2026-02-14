# backend/scripts/migrate_eval_tables.py
# 功能: 创建 Eval 体系所需的数据库表 + 预置评估模板

"""
迁移脚本: 创建 eval_runs 和 eval_trials 表，并插入综合评估模板
运行: cd backend && python -m scripts.migrate_eval_tables
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Base, get_engine, get_session_maker
from core.models import (
    EvalRun, EvalTrial, FieldTemplate, generate_uuid,
)


def migrate():
    """创建 Eval 表"""
    engine = get_engine()
    
    # 创建新表
    print("正在创建 eval_runs 和 eval_trials 表...")
    Base.metadata.create_all(bind=engine, tables=[
        EvalRun.__table__,
        EvalTrial.__table__,
    ])
    print("✅ 表创建完成")
    
    # 插入综合评估模板
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        existing = db.query(FieldTemplate).filter(
            FieldTemplate.name == "综合评估模板"
        ).first()
        
        # Eval V2: 3 字段（画像 → 任务配置 → 评估报告）
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
        new_desc = (
            "Eval V2 综合评估模板：目标画像 → 任务配置 → 评估报告（执行+评分+诊断一体化）。"
            "支持自定义 simulator × persona × grader 组合，并行执行无限 trial。"
        )

        if existing:
            # 已存在 → 就地升级为 V2
            existing.fields = new_fields
            existing.description = new_desc
            db.commit()
            print("✅ 综合评估模板已更新为 V2")
        else:
            eval_template = FieldTemplate(
                id=generate_uuid(),
                name="综合评估模板",
                description=new_desc,
                category="评估",
                fields=new_fields,
            )
            db.add(eval_template)
            db.commit()
            print("✅ 已创建综合评估模板（V2）")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 错误: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Eval 体系迁移")
    print("=" * 50)
    migrate()
    print("=" * 50)
    print("迁移完成!")
    print("=" * 50)
