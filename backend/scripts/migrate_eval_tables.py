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
        
        if existing:
            print("✅ 综合评估模板已存在，跳过")
        else:
            eval_template = FieldTemplate(
                id=generate_uuid(),
                name="综合评估模板",
                description="5角色评估体系：教练（策略）+ 编辑（手艺）+ 专家（专业）+ 消费者（体验）+ 销售（转化）+ 综合诊断",
                category="评估",
                fields=[
                    {
                        "name": "教练评审",
                        "type": "richtext",
                        "ai_prompt": "从策略视角评估内容：方向是否正确？意图是否对齐？定位是否清晰？",
                        "pre_questions": [],
                        "depends_on": [],
                        "dependency_type": "all",
                        "special_handler": "eval_coach",
                    },
                    {
                        "name": "编辑评审",
                        "type": "richtext",
                        "ai_prompt": "从编辑视角评估内容：结构是否合理？语言质量？风格一致性？",
                        "pre_questions": [],
                        "depends_on": [],
                        "dependency_type": "all",
                        "special_handler": "eval_editor",
                    },
                    {
                        "name": "领域专家评审",
                        "type": "richtext",
                        "ai_prompt": "从专业视角评估内容：事实准确性？专业深度？数据支撑？",
                        "pre_questions": [],
                        "depends_on": [],
                        "dependency_type": "all",
                        "special_handler": "eval_expert",
                    },
                    {
                        "name": "消费者体验",
                        "type": "richtext",
                        "ai_prompt": "以目标消费者身份体验内容：是否有用？能解决问题吗？会推荐吗？",
                        "pre_questions": [],
                        "depends_on": [],
                        "dependency_type": "all",
                        "special_handler": "eval_consumer",
                    },
                    {
                        "name": "内容销售测试",
                        "type": "richtext",
                        "ai_prompt": "模拟销售场景：销售顾问向目标消费者推介内容，测试转化能力。",
                        "pre_questions": [],
                        "depends_on": [],
                        "dependency_type": "all",
                        "special_handler": "eval_seller",
                    },
                    {
                        "name": "综合诊断",
                        "type": "richtext",
                        "ai_prompt": "跨角色诊断分析：综合所有评估结果，找出系统性问题和改进优先级。",
                        "pre_questions": [],
                        "depends_on": ["教练评审", "编辑评审", "领域专家评审", "消费者体验", "内容销售测试"],
                        "dependency_type": "all",
                        "special_handler": "eval_diagnoser",
                    },
                ]
            )
            db.add(eval_template)
            db.commit()
            print("✅ 已创建综合评估模板")
        
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
