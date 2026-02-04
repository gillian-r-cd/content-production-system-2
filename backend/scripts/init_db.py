# backend/scripts/init_db.py
# 功能: 初始化数据库，创建表，插入预置数据
# 主要函数: init_database(), seed_default_data()

"""
数据库初始化脚本
运行: python -m scripts.init_db
"""

import sys
from pathlib import Path

# 确保可以导入core模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Base, get_engine, get_session_maker
from core.models import (
    CreatorProfile,
    FieldTemplate,
    Channel,
    Simulator,
    EvaluationTemplate,
    INTERACTION_TYPES,
    SystemPrompt,
    AgentSettings,
    generate_uuid,
)


def init_database():
    """创建所有数据库表"""
    print("正在创建数据库表...")
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成！")


def seed_default_data():
    """插入预置数据"""
    print("正在插入预置数据...")
    
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # 1. 预置创作者特质
        if db.query(CreatorProfile).count() == 0:
            profiles = [
                CreatorProfile(
                    name="专业严谨型",
                    description="适合B2B、技术类、专业培训内容",
                    traits={
                        "tone": "专业、权威、严谨",
                        "vocabulary": "行业术语丰富，数据支撑",
                        "personality": "理性、客观、深度",
                        "taboos": ["过度口语化", "无根据的承诺"],
                    }
                ),
                CreatorProfile(
                    name="亲和幽默型",
                    description="适合C端、生活类、轻松话题内容",
                    traits={
                        "tone": "轻松、幽默、接地气",
                        "vocabulary": "日常用语，适当网络梗",
                        "personality": "亲切、有趣、共情",
                        "taboos": ["过于严肃", "冷冰冰的表达"],
                    }
                ),
                CreatorProfile(
                    name="故事驱动型",
                    description="适合品牌叙事、案例分享、情感营销",
                    traits={
                        "tone": "叙事性强、画面感丰富",
                        "vocabulary": "形象化描述，情感词汇",
                        "personality": "温暖、感性、启发性",
                        "taboos": ["纯数据堆砌", "缺乏情节"],
                    }
                ),
            ]
            db.add_all(profiles)
            print(f"  - 创建了 {len(profiles)} 个创作者特质")
        
        # 1.5 预置系统提示词
        if db.query(SystemPrompt).count() == 0:
            prompts = [
                SystemPrompt(
                    id=generate_uuid(),
                    name="意图分析提示词",
                    phase="intent",
                    content="""你是一个专业的内容策略顾问。你的任务是帮助用户澄清内容生产的核心意图。

请提出三个最关键的问题，帮助用户明确：
1. 内容的核心目标是什么？（教育、营销、品牌建设等）
2. 目标受众是谁？他们最关心什么？
3. 内容的独特价值主张是什么？

基于用户的回答，总结出清晰的内容生产意图。""",
                    description="用于意图分析阶段，引导用户明确内容生产目标"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="消费者调研提示词",
                    phase="research",
                    content="""你是一个专业的用户研究专家。基于项目意图，你需要：

1. 调研目标用户群体的特征
2. 分析用户的核心痛点和需求
3. 输出用户画像和典型人物小传

使用DeepResearch工具进行网络调研，结合项目意图生成深入的消费者洞察。""",
                    description="用于消费者调研阶段，指导用户研究和画像生成"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="内涵设计提示词",
                    phase="design_inner",
                    content="""你是一个资深的内容架构师。基于意图分析和消费者调研结果，你需要：

1. 设计内容生产方案和整体框架
2. 规划内容大纲和章节结构
3. 推荐合适的字段模板
4. 确定各字段之间的依赖关系

确保设计方案能够有效传达核心价值，并与目标受众产生共鸣。""",
                    description="用于内涵设计阶段，指导内容架构设计"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="内涵生产提示词",
                    phase="produce_inner",
                    content="""你是一个专业的内容创作者。基于内涵设计的方案和大纲，你需要：

1. 按照字段依赖顺序逐一生产内容
2. 确保内容风格与创作者特质一致
3. 在生成每个字段时参考Golden Context
4. 保持内容的连贯性和一致性

所有生成的内容都应该服务于项目的核心意图。""",
                    description="用于内涵生产阶段，指导具体内容生成"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="外延设计提示词",
                    phase="design_outer",
                    content="""你是一个全渠道营销策略专家。基于已生产的核心内容，你需要：

1. 分析内容适合的传播渠道
2. 为每个渠道设计内容改编方案
3. 制定渠道组合策略
4. 确保各渠道内容的协调一致

考虑不同渠道的特点和用户习惯，最大化内容传播效果。""",
                    description="用于外延设计阶段，指导多渠道传播策略"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="外延生产提示词",
                    phase="produce_outer",
                    content="""你是一个多平台内容运营专家。基于外延设计方案，你需要：

1. 将核心内容改编为各渠道适用的版本
2. 遵循各渠道的格式和风格要求
3. 优化标题、开头等关键位置
4. 添加渠道特有的互动元素

确保改编后的内容既保留核心信息，又符合渠道特性。""",
                    description="用于外延生产阶段，指导渠道内容生成"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="消费者模拟提示词",
                    phase="simulate",
                    content="""你需要扮演目标消费者，基于消费者画像和人物小传，对生产的内容进行真实体验。

根据模拟器设定的交互类型：
- 对话式：与内容/Chatbot进行多轮对话
- 阅读式：阅读全部内容并给出反馈
- 决策式：基于内容做出购买/行动决策
- 探索式：自由探索内容并记录体验
- 体验式：完整体验产品/服务流程

请保持角色一致性，给出真实的反馈和评价。""",
                    description="用于消费者模拟阶段，指导模拟器行为"
                ),
                SystemPrompt(
                    id=generate_uuid(),
                    name="评估提示词",
                    phase="evaluate",
                    content="""你是一个内容质量评估专家。基于评估模板，你需要：

1. 从多个维度评估内容质量
2. 综合消费者模拟的反馈结果
3. 识别内容的优势和改进空间
4. 给出具体的修改建议

评估应该客观、全面，并提供可操作的改进方向。""",
                    description="用于评估阶段，指导内容质量评估"
                ),
            ]
            db.add_all(prompts)
            print(f"  - 创建了 {len(prompts)} 个系统提示词")
        
        # 1.6 预置Agent设置
        if db.query(AgentSettings).count() == 0:
            settings = AgentSettings(
                id=generate_uuid(),
                name="default",
                tools=[
                    "deep_research", 
                    "generate_field", 
                    "simulate_consumer", 
                    "evaluate_content",
                    "architecture_writer",
                    "outline_generator",
                    "persona_manager",
                    "skill_manager",
                ],
                skills=[],
                autonomy_defaults={
                    "intent": True,
                    "research": True,
                    "design_inner": True,
                    "produce_inner": True,
                    "design_outer": True,
                    "produce_outer": True,
                    "simulate": True,
                    "evaluate": True,
                },
                tool_prompts={
                    "deep_research": "你是一个专业的用户研究专家。基于项目意图，进行网络调研，分析目标用户群体的特征、痛点和需求。",
                    "generate_field": "你是一个专业的内容创作者。基于上下文和依赖字段，生成高质量的内容。遵循创作者特质、保持风格一致性。",
                    "simulate_consumer": "你将扮演一个典型的目标消费者，基于用户画像进行内容体验模拟。提供真实的反馈、困惑点和改进建议。",
                    "evaluate_content": "你是一个内容质量评估专家。根据评估维度对内容进行打分和分析，给出具体的改进建议。",
                    "architecture_writer": "你是项目架构师。根据用户的自然语言描述，识别需要进行的架构操作（添加阶段/字段、删除、移动），并执行相应的修改。",
                    "outline_generator": "你是一个内容策划专家。基于项目意图和消费者调研结果，生成结构化的内容大纲，包括主题、章节、关键点和预计字段。",
                    "persona_manager": "你是用户研究专家。帮助用户管理消费者画像，包括创建新画像、编辑现有画像、推荐合适的画像用于模拟。",
                    "skill_manager": "你是AI技能管理专家。帮助用户查看、创建、应用可复用的AI技能，每个技能是一个可重复使用的提示词模板。",
                },
            )
            db.add(settings)
            print("  - 创建了默认Agent设置")
        
        # 2. 预置渠道
        if db.query(Channel).count() == 0:
            channels = [
                Channel(
                    name="小红书",
                    description="年轻女性为主的种草社区",
                    platform="social",
                    constraints={
                        "max_length": 1000,
                        "format": "短文+emoji",
                        "style": "亲和、真实、有态度",
                    }
                ),
                Channel(
                    name="微信公众号",
                    description="深度内容传播平台",
                    platform="social",
                    constraints={
                        "max_length": 5000,
                        "format": "长文，支持图文",
                        "style": "专业或有温度",
                    }
                ),
                Channel(
                    name="销售PPT",
                    description="B2B销售演示文稿",
                    platform="doc",
                    constraints={
                        "max_length": None,
                        "format": "结构化要点",
                        "style": "专业、有说服力",
                    }
                ),
                Channel(
                    name="产品落地页",
                    description="产品/服务介绍页面",
                    platform="web",
                    constraints={
                        "max_length": 2000,
                        "format": "标题+卖点+CTA",
                        "style": "简洁、有冲击力",
                    }
                ),
            ]
            db.add_all(channels)
            print(f"  - 创建了 {len(channels)} 个渠道")
        
        # 3. 预置模拟器
        if db.query(Simulator).count() == 0:
            simulators = []
            for type_id, type_info in INTERACTION_TYPES.items():
                simulator = Simulator(
                    name=f"默认{type_info['name']}模拟器",
                    description=type_info["description"],
                    interaction_type=type_id,
                    prompt_template=Simulator.get_default_template(type_id),
                    evaluation_dimensions=type_info["evaluation_dimensions"],
                )
                simulators.append(simulator)
            db.add_all(simulators)
            print(f"  - 创建了 {len(simulators)} 个模拟器")
        
        # 4. 预置评估模板
        if db.query(EvaluationTemplate).count() == 0:
            template = EvaluationTemplate(
                name="默认评估模板",
                description="通用的内容评估模板",
                sections=[
                    {
                        "id": "intent_alignment",
                        "name": "意图对齐度",
                        "grader_prompt": "评估生成的内容是否准确传达了项目的核心意图。检查是否有偏离主题或遗漏关键信息的情况。",
                        "weight": 0.25,
                        "metrics": [
                            {"name": "核心信息覆盖", "type": "score_1_10"},
                            {"name": "偏离点", "type": "text_list"},
                        ]
                    },
                    {
                        "id": "consumer_fit",
                        "name": "用户匹配度",
                        "grader_prompt": "基于消费者画像评估内容适配性。检查内容是否回应了用户痛点，语言风格是否适合目标用户。",
                        "weight": 0.25,
                        "metrics": [
                            {"name": "痛点回应", "type": "score_1_10"},
                            {"name": "语言风格适配", "type": "score_1_10"},
                        ]
                    },
                    {
                        "id": "content_quality",
                        "name": "内容质量",
                        "grader_prompt": "评估内容的整体质量，包括逻辑结构、表达清晰度、专业性等。",
                        "weight": 0.20,
                        "metrics": [
                            {"name": "逻辑结构", "type": "score_1_10"},
                            {"name": "表达清晰度", "type": "score_1_10"},
                            {"name": "专业性", "type": "score_1_10"},
                        ]
                    },
                    {
                        "id": "simulation_synthesis",
                        "name": "模拟反馈综合",
                        "grader_prompt": "汇总消费者模拟的反馈结果。",
                        "weight": 0.30,
                        "source": "simulation_records",
                        "metrics": [
                            {"name": "平均满意度", "type": "score_1_10"},
                            {"name": "主要问题", "type": "text_list"},
                        ]
                    },
                ]
            )
            db.add(template)
            print("  - 创建了默认评估模板")
        
        # 5. 预置字段模板
        if db.query(FieldTemplate).count() == 0:
            templates = [
                FieldTemplate(
                    name="课程设计模板",
                    description="适用于在线课程、培训内容设计",
                    category="课程",
                    fields=[
                        {
                            "name": "课程目标",
                            "type": "text",
                            "ai_prompt": "基于项目意图和目标用户画像，明确课程的核心学习目标。目标应该是具体的、可衡量的。",
                            "pre_questions": ["目标学员的现有水平是？", "学完后学员应该能做什么？"],
                            "depends_on": [],
                            "dependency_type": "all"
                        },
                        {
                            "name": "课程大纲",
                            "type": "structured",
                            "ai_prompt": "根据课程目标，设计详细的课程大纲。包括模块划分、每个模块的主题和要点。",
                            "pre_questions": ["课程总时长预期是？"],
                            "depends_on": ["课程目标"],
                            "dependency_type": "all"
                        },
                        {
                            "name": "课程内容",
                            "type": "richtext",
                            "ai_prompt": "根据课程大纲，逐一展开每个模块的详细内容。",
                            "pre_questions": [],
                            "depends_on": ["课程大纲"],
                            "dependency_type": "all"
                        },
                    ]
                ),
                FieldTemplate(
                    name="文章写作模板",
                    description="适用于公众号、博客等长文内容",
                    category="文章",
                    fields=[
                        {
                            "name": "文章主题",
                            "type": "text",
                            "ai_prompt": "根据意图分析，确定文章的核心主题和角度。",
                            "pre_questions": ["想传达的核心观点是？"],
                            "depends_on": [],
                            "dependency_type": "all"
                        },
                        {
                            "name": "文章大纲",
                            "type": "structured",
                            "ai_prompt": "设计文章的结构大纲，包括开头、核心论点、结尾。",
                            "pre_questions": [],
                            "depends_on": ["文章主题"],
                            "dependency_type": "all"
                        },
                        {
                            "name": "正文内容",
                            "type": "richtext",
                            "ai_prompt": "按照大纲展开写作，注意保持风格一致性。",
                            "pre_questions": [],
                            "depends_on": ["文章大纲"],
                            "dependency_type": "all"
                        },
                    ]
                ),
            ]
            db.add_all(templates)
            print(f"  - 创建了 {len(templates)} 个字段模板")
        
        db.commit()
        print("预置数据插入完成！")
        
    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


def main():
    """主函数"""
    print("=" * 50)
    print("内容生产系统 - 数据库初始化")
    print("=" * 50)
    
    init_database()
    seed_default_data()
    
    print("=" * 50)
    print("初始化完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()

