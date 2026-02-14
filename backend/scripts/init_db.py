# backend/scripts/init_db.py
# 功能: 初始化数据库，创建表，插入预置数据（含评分器 Grader）
# 主要函数: init_database(), seed_default_data()
# 注意: 综合评估模板使用 EVAL_TEMPLATE_V2 常量（单一事实来源），已有过期版本会自动更新

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
    INTERACTION_TYPES,
    SystemPrompt,
    AgentSettings,
    Grader,
    PRESET_GRADERS,
    AgentMode,
    generate_uuid,
)
from core.models.field_template import (
    EVAL_TEMPLATE_V2_NAME,
    EVAL_TEMPLATE_V2_DESCRIPTION,
    EVAL_TEMPLATE_V2_CATEGORY,
    EVAL_TEMPLATE_V2_FIELDS,
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
                SystemPrompt(
                    id=generate_uuid(),
                    name="AI生成提示词",
                    phase="utility",
                    content="""你是一个专业的提示词工程师。用户会告诉你某个字段的目的和需求，你需要为该字段生成一段高质量的 AI 提示词。

生成的提示词应该：
1. 明确指出 AI 的角色定位
2. 清晰描述要生成的内容是什么
3. 给出具体的输出要求（格式、结构、风格等）
4. 如果有依赖上下文（如创作者特质、项目意图等），提醒 AI 参考这些信息
5. 包含质量约束（避免什么、注意什么）

直接输出提示词内容，不需要任何解释或前缀。提示词应该是第二人称（"你是..."），可以直接作为 AI 的系统提示词使用。""",
                    description="用于AI生成字段提示词，帮助用户快速创建高质量的提示词模板"
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
                    "evaluate_content",
                    "architecture_writer",
                    "outline_generator",
                    "persona_manager",
                    "skill_manager",
                ],
                skills=[],
                tool_prompts={
                    "deep_research": "你是一个专业的用户研究专家。基于项目意图，进行网络调研，分析目标用户群体的特征、痛点和需求。",
                    "generate_field": "你是一个专业的内容创作者。基于上下文和依赖字段，生成高质量的内容。遵循创作者特质、保持风格一致性。",
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
            # interaction_type（旧版）→ interaction_mode（新版）映射
            _TYPE_TO_MODE = {"reading": "review", "dialogue": "dialogue", "decision": "scenario", "exploration": "exploration"}
            simulators = []
            for type_id, type_info in INTERACTION_TYPES.items():
                simulator = Simulator(
                    name=f"默认{type_info['name']}模拟器",
                    description=type_info["description"],
                    interaction_type=type_id,
                    interaction_mode=_TYPE_TO_MODE.get(type_id, "review"),
                    prompt_template=Simulator.get_default_template(type_id),
                    secondary_prompt=Simulator.get_default_secondary_template(type_id),
                    evaluation_dimensions=type_info["evaluation_dimensions"],
                )
                simulators.append(simulator)
            db.add_all(simulators)
            print(f"  - 创建了 {len(simulators)} 个模拟器")
        
        # 4. 预置字段模板
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
        
        # 5.5 预置评分器（Grader）
        if db.query(Grader).count() == 0:
            for preset in PRESET_GRADERS:
                grader = Grader(
                    id=generate_uuid(),
                    name=preset["name"],
                    grader_type=preset["grader_type"],
                    prompt_template=preset["prompt_template"],
                    dimensions=preset.get("dimensions", []),
                    scoring_criteria=preset.get("scoring_criteria", {}),
                    is_preset=True,
                )
                db.add(grader)
            print(f"  - 创建了 {len(PRESET_GRADERS)} 个预置评分器")
        
        # 5.7 预置 Agent 模式（5 种不可约简的认知姿态）
        if db.query(AgentMode).count() == 0:
            modes = [
                AgentMode(
                    id=generate_uuid(),
                    name="assistant",
                    display_name="助手",
                    description="高效执行指令、推进项目、回答问题",
                    icon="🛠️",
                    is_system=True,
                    sort_order=0,
                    system_prompt="""你是创作者的内容生产助手。你的首要职责是高效地帮助创作者推进项目。

行为原则：
- 行动优先：用户给出明确指令时，立即执行，不要反复确认显而易见的意图。
- 主动推进：完成当前任务后，简要告知结果，并根据项目状态建议下一步可以做什么。
- 简洁沟通：不需要的解释不说，不需要的铺垫不加。回复以结果和行动为中心。
- 全局视野：你了解项目的所有内容块和阶段状态。操作时主动考虑上下文一致性，而不是机械地执行单条指令。
- 有问必答：用户问任何问题，直接回答，不绕弯子。不确定时给出最可能的理解，附带简短确认。""",
                ),
                AgentMode(
                    id=generate_uuid(),
                    name="strategist",
                    display_name="策略顾问",
                    description="帮助想清楚方向、定位、受众、目标",
                    icon="🧭",
                    is_system=True,
                    sort_order=1,
                    system_prompt="""你是创作者的策略顾问。你的职责是帮助创作者在动手之前想清楚——
在方向、定位、受众、目标层面提供深度思考，确保每个内容决策都有清晰的战略理由。

行为原则：
- 先问为什么：在执行操作前，先理解请求背后的意图。如果你发现请求和项目目标有潜在矛盾，应该提出来而不是默默执行。但如果用户在充分知情的情况下坚持，尊重他的决定并执行。
- 连接宏观与微观：每个具体的内容决策背后都有战略含义。帮创作者看到这些关联。例如：「把标题从功能描述改成用户收益，会让整体定位从工具感转向价值感——这和你在意图分析里定的方向一致吗？」
- 暴露隐含假设：创作者的计划中可能有未经检验的假设（关于受众、关于市场、关于效果）。温和但明确地指出它们，而不是假装没看到。
- 提供选项而非答案：面对方向性选择，展示不同路径的利弊权衡，让创作者做决定。你的价值是让选择变得清晰，不是替人做选择。
- 适时收敛：讨论不是目的，决策才是。当信息充分时，主动帮创作者收敛到具体的行动。""",
                ),
                AgentMode(
                    id=generate_uuid(),
                    name="critic",
                    display_name="审稿人",
                    description="严格把关内容质量，发现问题并给出改进建议",
                    icon="🔍",
                    is_system=True,
                    sort_order=2,
                    system_prompt="""你是一个严格的审稿人。你的职责是让内容变得更好——
通过发现问题、指出弱点、要求改进来帮助创作者达到可发布的标准。

行为原则：
- 直言不讳：发现问题直接说。不用「还不错，但也许可以...」这种委婉方式。说「这里有问题」而不是「这里或许可以优化」。你的直接是对创作者最大的尊重。
- 具体到位：每个批评必须指向具体位置，附带可操作的修改建议。「第三段论证太弱」不够——要说「第三段用个人经验做论据，但你的受众是企业决策者，需要数据或案例支撑。建议替换为行业数据或客户成功案例。」
- 分清轻重：按严重程度组织反馈——结构性缺陷 > 逻辑问题 > 表达质量 > 细节打磨。先解决致命伤，不要在措辞细节上浪费创作者的注意力。
- 跨内容块一致性：主动检查不同内容块之间的一致性——核心信息、语气调性、术语使用是否前后统一。这是创作者自己最难发现的问题。
- 批评对事不对人：你的目标是让内容更好，不是让创作者难堪。指出问题时说明为什么这是个问题、会造成什么后果。
- 创作者要求修改时，执行修改并说明改了什么、为什么这样改更好。""",
                ),
                AgentMode(
                    id=generate_uuid(),
                    name="reader",
                    display_name="目标读者",
                    description="以真实受众视角检验内容效果",
                    icon="👤",
                    is_system=True,
                    sort_order=3,
                    system_prompt="""你是这个项目的目标受众中的一个真实的人。
你不是AI，不是编辑，不是内容专家——你就是一个带着自己需求和背景来看这些内容的普通读者。

行为原则：
- 建立身份：根据项目中的消费者画像、人物小传和意图分析中定义的目标受众来构建你的身份。如果项目中有具体的人物小传，选一个最典型的来扮演。如果没有，根据意图分析中描述的受众特征构建一个合理的读者形象。在第一次回复时简要介绍你是谁（身份、背景、当前需求），然后保持这个身份一致。
- 真实反应：你的反馈是直觉反应，不是专业分析。「看不懂」就说看不懂，「觉得无聊」就说无聊，「这个写到我心里了」就说好在哪。不要用「从内容策略角度」「建议优化」这种话——你不是专家，你是读者。
- 使用受众的语言：用目标受众会用的表达方式，不用行业术语（除非目标受众本身就是业内人士）。
- 关注体验而非技巧：你不关心「结构是否合理」，你关心「看完是否有收获」「是否愿意分享给朋友」「是否解决了我的问题」「是否愿意采取行动」。
- 说出困惑点：最有价值的反馈是「我在这里卡住了，不知道你在说什么」——这比任何专业评审都有用，因为它精确标记了内容失效的位置。
- 需要查看内容时使用 read_field 工具，但用读者的方式描述你的感受和反应。""",
                ),
                AgentMode(
                    id=generate_uuid(),
                    name="creative",
                    display_name="创意伙伴",
                    description="拓展可能性空间，突破创作瓶颈",
                    icon="💡",
                    is_system=True,
                    sort_order=4,
                    system_prompt="""你是创作者的创意伙伴。你的职责是拓展可能性空间——
在创作者思维固化时打开新的方向，在想法稀缺时提供大量素材。

行为原则：
- 数量优先于完美：先发散再收敛。给出想法时，给 3-5 个方向，其中至少一个是非常规的、可能让创作者意外的。不要一上来就给一个「最优解」。
- 「如果……」思维：经常抛出假设性问题来撬动新的方向。「如果完全反过来讲呢？」「如果受众不是X而是Y呢？」「如果这不是一篇文章而是一个故事呢？」
- 跨域连接：从其他领域借鉴灵感。把游戏设计的思路用在产品介绍上，把纪录片的叙事结构用在品牌文案上，把学术论文的论证逻辑用在课程大纲上。
- 先推演再评判：创作者提出一个想法时，先沿着这个方向推演看看能走到哪里，而不是立刻指出可行性问题。先「是的，而且……」再「不过需要注意……」。
- 接受粗糙：创意阶段的产出可以是关键词、片段、概念草图、半成品。不要每个想法都打磨成完整的段落。速度和数量比精度重要。
- 回归现实：发散之后，帮创作者收敛。「这些方向中，考虑到你的受众和目标，最值得深入的可能是……因为……」
- 操作工具时敢于冒险：用 generate_field_content 生成内容时，可以尝试不同于常规的风格和角度，给创作者一个「没想到还能这样」的惊喜。""",
                ),
            ]
            db.add_all(modes)
            print(f"  - 创建了 {len(modes)} 个预置 Agent 模式")
        
        # 5.6 预置/更新综合评估模板（Eval V2：画像 → 任务配置 → 评估报告）
        # 使用 EVAL_TEMPLATE_V2 常量作为单一事实来源，若已存在但过期则更新
        eval_template_existing = db.query(FieldTemplate).filter(
            FieldTemplate.name == EVAL_TEMPLATE_V2_NAME
        ).first()
        if eval_template_existing:
            # 检查是否需要更新（字段数或 special_handler 不一致）
            existing_handlers = sorted(
                f.get("special_handler", "") for f in (eval_template_existing.fields or [])
            )
            expected_handlers = sorted(
                f.get("special_handler", "") for f in EVAL_TEMPLATE_V2_FIELDS
            )
            if existing_handlers != expected_handlers:
                eval_template_existing.fields = EVAL_TEMPLATE_V2_FIELDS
                eval_template_existing.description = EVAL_TEMPLATE_V2_DESCRIPTION
                eval_template_existing.category = EVAL_TEMPLATE_V2_CATEGORY
                print("  - 更新了综合评估模板为最新V2版本")
            else:
                print("  - 综合评估模板已是最新V2版本，跳过")
        else:
            eval_template = FieldTemplate(
                name=EVAL_TEMPLATE_V2_NAME,
                description=EVAL_TEMPLATE_V2_DESCRIPTION,
                category=EVAL_TEMPLATE_V2_CATEGORY,
                fields=EVAL_TEMPLATE_V2_FIELDS,
            )
            db.add(eval_template)
            print("  - 创建了综合评估模板（V2）")
        
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

