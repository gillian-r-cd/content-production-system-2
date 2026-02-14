#!/usr/bin/env python3
"""
添加特殊字段模板：基础调研模板

包含意图分析、消费者调研两个字段
这两个字段存在依赖关系：
- 意图分析: 无依赖
- 消费者调研: 依赖意图分析

这是推荐的组合模板，确保用户引用时不会搞错依赖关系。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_session_maker
from core.models import FieldTemplate


def add_special_templates():
    """添加特殊字段模板"""
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # 检查是否已存在基础调研模板
        existing = db.query(FieldTemplate).filter(
            FieldTemplate.name == "基础调研模板"
        ).first()
        
        if existing:
            print("✅ 基础调研模板已存在，更新字段配置...")
            # 更新字段配置
            existing.fields = get_research_template_fields()
            existing.description = "意图分析 + 消费者调研的完整流程，两个字段已配置好依赖关系"
            db.commit()
            print("✅ 已更新基础调研模板")
        else:
            print("准备添加: 基础调研模板")
            template = FieldTemplate(
                name="基础调研模板",
                description="意图分析 + 消费者调研的完整流程，两个字段已配置好依赖关系",
                category="基础流程",
                fields=get_research_template_fields()
            )
            db.add(template)
            db.commit()
            print("✅ 成功添加基础调研模板（含3个字段）")
        
        # 删除旧的独立模板（如果存在）
        old_templates = db.query(FieldTemplate).filter(
            FieldTemplate.name.in_(["意图分析模板", "消费者调研模板", "消费者模拟模板"])
        ).all()
        
        if old_templates:
            for t in old_templates:
                db.delete(t)
            db.commit()
            print(f"✅ 已删除 {len(old_templates)} 个旧的独立模板（已合并到基础调研模板）")
        
        # 显示所有模板
        all_templates = db.query(FieldTemplate).all()
        print(f"\n当前共有 {len(all_templates)} 个字段模板:")
        for t in all_templates:
            field_names = [f.get('name', 'unnamed') for f in (t.fields or [])]
            print(f"  - {t.name} ({t.category}): {len(t.fields or [])} 个字段")
            for fn in field_names:
                print(f"      • {fn}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 错误: {e}")
        raise
    finally:
        db.close()


def get_research_template_fields():
    """返回基础调研模板的字段配置"""
    return [
        # 1. 意图分析 - 无依赖
        {
            "name": "意图分析",
            "type": "structured",
            "ai_prompt": """你是一个专业的内容策略顾问。你的任务是帮助用户澄清内容生产的核心意图。

请提出三个最关键的问题，帮助用户明确：
1. 内容的核心目标是什么？（教育、营销、品牌建设等）
2. 目标受众是谁？他们最关心什么？
3. 内容的独特价值主张是什么？

基于用户的回答，总结出清晰的内容生产意图。

输出格式：
## 核心目标
[描述内容的核心目标]

## 目标受众
[描述目标受众特征]

## 价值主张
[描述独特价值主张]

## 意图总结
[一句话总结项目意图]""",
            "pre_questions": [
                "你这次想做什么内容？请简单描述一下（比如：一篇文章、一个视频脚本、一份产品介绍、一套培训课件等），并补充一句说明它的大致主题或方向。"
            ],
            "depends_on": [],  # 无依赖
            "dependency_type": "all",
            "need_review": True,
            "constraints": {
                "question_count": 3,
                "question_strategy": "sequential"
            },
            "special_handler": "intent_analysis"
        },
        
        # 2. 消费者调研 - 依赖意图分析
        {
            "name": "消费者调研",
            "type": "structured",
            "ai_prompt": """基于项目意图，进行深度消费者调研。

调研目标：
1. 目标用户画像：年龄、职业、特征、行为模式
2. 用户痛点：核心问题和未满足需求
3. 价值主张：如何解决用户问题

生成3个典型用户角色（Persona），每个角色包含：
- 基本信息（年龄、性别、城市、教育、职业、收入等）
- 背景简介
- 核心痛点（3-5个）

输出格式为结构化JSON，包含：
- summary: 调研摘要
- consumer_profile: 消费者画像（年龄范围、职业列表、特征、行为、痛点、价值主张）
- personas: 用户角色列表（每个包含id、name、basic_info、background、pain_points、selected）
- sources: 调研来源""",
            "pre_questions": [],
            "depends_on": ["意图分析"],  # 依赖意图分析
            "dependency_type": "all",
            "need_review": True,
            "constraints": {
                "persona_count": 3,
                "output_format": "json",
                "use_deep_research": True
            },
            "special_handler": "consumer_research"
        },
        
    ]


if __name__ == "__main__":
    print("=" * 50)
    print("添加/更新基础调研模板")
    print("=" * 50)
    add_special_templates()
