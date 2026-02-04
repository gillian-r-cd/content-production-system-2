# backend/core/prompt_engine.py
# 功能: 提示词引擎，负责Golden Context构建、动态注入、@引用解析
# 主要类: PromptEngine, GoldenContext
# 主要函数: build_golden_context(), inject_context(), parse_references()

"""
提示词引擎
核心职责:
1. 构建Golden Context (创作者特质 + 项目意图 + 用户画像)
2. 动态注入上下文到每次LLM调用
3. 解析@引用语法
4. 管理系统提示词
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from core.models import (
    Project, 
    CreatorProfile, 
    ProjectField,
    Channel,
)


@dataclass
class GoldenContext:
    """
    Golden Context - 每次LLM调用必须注入的核心上下文
    
    核心原则（2024-02更新）:
    - 只有 creator_profile 应该全局注入到每个 LLM 调用
    - intent 和 consumer_personas 应该通过字段依赖关系传递
    - 但为了向后兼容，特定阶段（如 design_inner）仍需要这些上下文
    
    包含:
    - 创作者特质: 风格、语气、禁忌等（全局注入）
    - 项目意图: 意图分析阶段的输出（通过依赖传递，或特定阶段注入）
    - 用户画像: 消费者调研阶段的输出（通过依赖传递，或特定阶段注入）
    """
    creator_profile: str = ""
    intent: str = ""
    consumer_personas: str = ""
    
    # 控制是否注入 intent 和 consumer_personas
    # False = 只注入 creator_profile（这些应该通过依赖传递）
    # True = 全部注入（用于 design_inner 等需要全局上下文的阶段）
    include_all_context: bool = True
    
    def to_prompt(self) -> str:
        """转换为提示词格式"""
        sections = []
        
        # 创作者特质始终注入
        if self.creator_profile:
            sections.append(f"# 创作者特质\n{self.creator_profile}")
        
        # intent 和 consumer_personas 根据 include_all_context 决定是否注入
        if self.include_all_context:
            if self.intent:
                sections.append(f"# 项目意图\n{self.intent}")
            
            if self.consumer_personas:
                sections.append(f"# 目标用户画像\n{self.consumer_personas}")
        
        return "\n\n".join(sections)
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return not (self.creator_profile or self.intent or self.consumer_personas)


@dataclass
class PromptContext:
    """
    完整的提示词上下文
    
    包含:
    - golden_context: 核心上下文
    - phase_context: 当前阶段上下文
    - field_context: 字段依赖上下文
    - channel_context: 渠道上下文（外延生产时）
    - custom_context: 自定义上下文
    """
    golden_context: GoldenContext = field(default_factory=GoldenContext)
    phase_context: str = ""
    field_context: str = ""
    channel_context: str = ""
    custom_context: str = ""
    
    def to_system_prompt(self) -> str:
        """构建完整的系统提示词"""
        parts = []
        
        # Golden Context（必须）
        gc = self.golden_context.to_prompt()
        if gc:
            parts.append(gc)
        
        # 阶段上下文
        if self.phase_context:
            parts.append(f"# 当前任务\n{self.phase_context}")
        
        # 字段依赖上下文
        if self.field_context:
            parts.append(f"# 参考内容\n{self.field_context}")
        
        # 渠道上下文
        if self.channel_context:
            parts.append(f"# 目标渠道\n{self.channel_context}")
        
        # 自定义上下文
        if self.custom_context:
            parts.append(self.custom_context)
        
        return "\n\n---\n\n".join(parts)


class PromptEngine:
    """
    提示词引擎
    
    职责:
    - 从数据库构建Golden Context
    - 解析@引用
    - 为不同阶段生成系统提示词
    """
    
    # 意图分析阶段 - 两种模式的提示词
    INTENT_QUESTIONING_PROMPT = """你是一个专业的内容策略顾问。你的任务是通过3个问题帮助用户澄清内容生产的意图。

问题顺序（根据对话历史判断当前应该问哪个）：

1. 【先了解项目是什么】如果用户还没说清楚想做什么内容，先问：
   "你这次想做什么内容？请简单描述一下（比如：一篇文章、一个视频脚本、一份产品介绍...）"

2. 【再问目标受众】了解内容是什么后，问：
   "这个内容主要写给谁看？请用「岗位/角色 + 所在行业 + 当前面临的1-2个痛点」来描述，比如：'中大型制造企业的IT负责人，正在推进数字化转型但缺乏内部数据基础'"

3. 【最后问期望效果】了解受众后，问：
   "看完这个内容后，你最希望读者立刻采取的一个具体行动是什么？"

规则：
- 根据对话历史判断用户已经回答了哪些问题，不要重复问
- 每次只问1个问题
- 问题要简洁明了"""

    INTENT_PRODUCING_PROMPT = """你是一个专业的内容策略顾问。根据用户的回答，提取3个核心字段。

请严格按以下JSON格式输出（不要添加任何其他内容）：

```json
{
  "做什么": "用一句话描述这个内容的主题和形式，例如：一份面向一线经理的AI对练chatbot设计方案",
  "给谁看": "目标受众的具体描述，包含角色、行业、痛点，例如：互联网/制造业的一线经理，面临绩效面谈、冲突处理等管理场景缺乏练习机会",
  "期望行动": "读者看完后最希望采取的具体行动，例如：主动尝试使用AI对练工具进行一次模拟管理对话"
}
```

规则：
- 每个字段的内容要简洁有力，1-2句话
- 直接从用户回答中提炼，不要自己发挥
- 只输出JSON，不要其他解释

请基于用户的所有回答，生成完整、具体、可操作的意图分析报告。"""
    
    # 阶段系统提示词模板
    PHASE_PROMPTS = {
        "intent": INTENT_QUESTIONING_PROMPT,  # 默认用提问模式

        "research": """你是一个资深的用户研究专家。基于用户的项目意图，进行消费者调研。

你需要输出：
1. 总体用户画像（年龄、职业、特征）
2. 核心痛点（3-5个）
3. 价值主张（3-5个）
4. 典型用户小传（3个，包含完整的故事背景）

输出格式要求结构化、具体、可操作。""",

        "design_inner": """你是一个资深的内容架构师。基于项目意图和用户调研，设计3个不同的内容生产方案供用户选择。

你必须输出严格的JSON格式（不要添加任何其他内容），包含3个方案：

```json
{
  "proposals": [
    {
      "id": "proposal_1",
      "name": "方案名称（简洁有力）",
      "description": "方案核心思路描述（2-3句话）",
      "fields": [
        {
          "id": "field_1",
          "name": "字段名称",
          "field_type": "richtext",
          "ai_prompt": "生成这个字段时的AI提示词",
          "depends_on": [],
          "order": 1,
          "need_review": true
        },
        {
          "id": "field_2",
          "name": "第二个字段",
          "field_type": "richtext",
          "ai_prompt": "生成提示词",
          "depends_on": ["field_1"],
          "order": 2,
          "need_review": false
        }
      ]
    },
    { ... },
    { ... }
  ]
}
```

要求：
1. 3个方案要有明显差异（如：模块化 vs 线性 vs 场景驱动）
2. 每个方案5-10个字段
3. 字段依赖关系要合理（depends_on 填写依赖的字段id）
4. need_review=true 表示重要字段需要人工确认
5. 紧扣用户痛点和项目意图""",

        "produce_inner": """你是一个专业的内容创作者。根据内涵设计方案，生产具体的内容。

要求：
1. 严格遵循创作者特质和风格
2. 紧扣项目意图
3. 回应用户痛点
4. 输出高质量、可直接使用的内容""",

        "design_outer": """你是一个资深的营销策略专家。基于已生产的内涵内容，设计外延传播方案。

你需要输出：
1. 推荐的传播渠道及理由
2. 各渠道的内容策略
3. 核心传播信息提炼
4. 关键注意事项""",

        "produce_outer": """你是一个全渠道内容运营专家。根据外延设计方案，为指定渠道生产内容。

要求：
1. 严格遵循渠道规范和限制
2. 保持与内涵内容的一致性
3. 适配渠道用户的阅读习惯
4. 输出可直接发布的内容""",

        "simulate": """你是一个真实的目标用户。请根据你的人物设定，真实地体验和评价内容。

注意：
1. 完全代入人物角色
2. 给出真实、具体的反馈
3. 指出优点和不足
4. 提供改进建议""",

        "evaluate": """你是一个资深的内容评审专家。请对整个项目进行全面评估。

评估维度：
1. 意图对齐度
2. 用户匹配度
3. 内容质量
4. 模拟反馈综合

输出：
1. 各维度评分和评语
2. 具体的修改建议（可操作）
3. 总体评价""",
    }
    
    def __init__(self):
        pass
    
    def build_golden_context(
        self,
        project: Project,
        creator_profile: Optional[CreatorProfile] = None,
        intent_field: Optional[ProjectField] = None,
        research_field: Optional[ProjectField] = None,
    ) -> GoldenContext:
        """
        构建Golden Context
        
        Args:
            project: 项目对象
            creator_profile: 创作者特质（可选，如未提供则从project关联获取）
            intent_field: 意图分析字段（可选）
            research_field: 消费者调研字段（可选）
        """
        gc = GoldenContext()
        
        # 创作者特质
        profile = creator_profile or getattr(project, 'creator_profile', None)
        if profile:
            gc.creator_profile = profile.to_prompt_context()
        
        # 项目意图
        if intent_field and intent_field.content:
            gc.intent = intent_field.content
        elif project.golden_context and project.golden_context.get("intent"):
            gc.intent = project.golden_context["intent"]
        
        # 用户画像
        if research_field and research_field.content:
            gc.consumer_personas = research_field.content
        elif project.golden_context and project.golden_context.get("consumer_personas"):
            gc.consumer_personas = project.golden_context["consumer_personas"]
        
        return gc
    
    def build_prompt_context(
        self,
        project: Project,
        phase: str,
        golden_context: Optional[GoldenContext] = None,
        dependent_fields: Optional[list[ProjectField]] = None,
        channel: Optional[Channel] = None,
        custom_prompt: str = "",
    ) -> PromptContext:
        """
        构建完整的提示词上下文
        
        Args:
            project: 项目对象
            phase: 当前阶段
            golden_context: Golden Context（如未提供则自动构建）
            dependent_fields: 依赖的字段列表
            channel: 目标渠道（外延生产时）
            custom_prompt: 自定义提示词
        """
        ctx = PromptContext()
        
        # Golden Context
        ctx.golden_context = golden_context or self.build_golden_context(project)
        
        # 阶段提示词
        ctx.phase_context = self.PHASE_PROMPTS.get(phase, "")
        
        # 字段依赖上下文
        if dependent_fields:
            field_parts = []
            for f in dependent_fields:
                if f.content:
                    field_parts.append(f"## {f.name}\n{f.content}")
            ctx.field_context = "\n\n".join(field_parts)
        
        # 渠道上下文
        if channel:
            ctx.channel_context = channel.to_prompt_context()
        
        # 自定义提示词
        ctx.custom_context = custom_prompt
        
        return ctx
    
    def parse_references(
        self,
        text: str,
        fields_by_name: Dict[str, ProjectField],
    ) -> Tuple[str, List[ProjectField]]:
        """
        解析@引用语法
        
        格式: @字段名 或 @阶段.字段名
        例如: @意图分析 或 @内涵.课程目标
        
        Args:
            text: 包含@引用的文本
            fields_by_name: {字段名: ProjectField} 映射
        
        Returns:
            (替换后的文本, 引用的字段列表)
        """
        # 匹配 @xxx 或 @xxx.yyy
        # 使用非贪婪匹配，遇到常见中文虚词/标点时停止
        # 支持中文、英文、数字、下划线和点号
        word_chars = r'a-zA-Z0-9_\u4e00-\u9fff'
        stop_chars = r'的了吗呢吧啊是在有和与或及到从把被让给对比跟向往于着过'
        punct_chars = r'，。！？、：；""''（）'
        pattern = rf'@([{word_chars}]+(?:\.[{word_chars}]+)?)(?=[{stop_chars}]|[{punct_chars}\s]|$)'
        
        referenced_fields = []
        
        def replace_ref(match):
            ref = match.group(1)
            
            # 尝试直接匹配字段名
            if ref in fields_by_name:
                field = fields_by_name[ref]
                referenced_fields.append(field)
                return f"\n\n---\n引用 [{field.name}]:\n{field.content}\n---\n\n"
            
            # 尝试匹配 阶段.字段名 格式
            if '.' in ref:
                _, field_name = ref.split('.', 1)
                if field_name in fields_by_name:
                    field = fields_by_name[field_name]
                    referenced_fields.append(field)
                    return f"\n\n---\n引用 [{field.name}]:\n{field.content}\n---\n\n"
            
            # 未找到，保持原样
            return match.group(0)
        
        replaced_text = re.sub(pattern, replace_ref, text)
        
        return replaced_text, referenced_fields
    
    def get_field_generation_prompt(
        self,
        field: ProjectField,
        context: PromptContext,
    ) -> str:
        """
        获取字段生成的完整提示词
        
        Args:
            field: 要生成的字段
            context: 提示词上下文
        
        Returns:
            完整的系统提示词
        """
        parts = [context.to_system_prompt()]
        
        # 添加字段基本信息
        parts.append(f"# 当前要生成的字段\n字段名称：{field.name}")
        
        # 添加字段约束（非常重要！）
        constraints = field.constraints or {}
        constraints_lines = []
        
        if constraints.get("max_length"):
            constraints_lines.append(f"- 字数限制：不超过 {constraints['max_length']} 字")
        if constraints.get("output_format"):
            format_names = {
                "markdown": "Markdown 富文本",
                "plain_text": "纯文本",
                "json": "JSON 格式",
                "list": "列表格式（每行一项）"
            }
            constraints_lines.append(f"- 输出格式：{format_names.get(constraints['output_format'], constraints['output_format'])}")
        if constraints.get("structure"):
            constraints_lines.append(f"- 结构要求：{constraints['structure']}")
        if constraints.get("example"):
            constraints_lines.append(f"- 参考示例：\n{constraints['example']}")
        
        if constraints_lines:
            parts.append(f"# 生成约束（必须严格遵守！）\n" + "\n".join(constraints_lines))
        
        # 添加字段特定的AI提示词（核心指令）
        if field.ai_prompt and field.ai_prompt.strip() and field.ai_prompt != "请在这里编写生成提示词...":
            parts.append(f"# 具体生成要求\n{field.ai_prompt}")
        
        # 添加用户回答的预问题
        if field.pre_answers:
            answers_text = "\n".join(
                f"- {q}: {a}" 
                for q, a in field.pre_answers.items()
            )
            parts.append(f"# 用户补充信息\n{answers_text}")
        
        return "\n\n---\n\n".join(parts)


# 单例
prompt_engine = PromptEngine()

