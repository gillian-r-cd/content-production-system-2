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
from typing import Optional

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
    
    包含:
    - 创作者特质: 风格、语气、禁忌等
    - 项目意图: 意图分析阶段的输出
    - 用户画像: 消费者调研阶段的输出
    """
    creator_profile: str = ""
    intent: str = ""
    consumer_personas: str = ""
    
    def to_prompt(self) -> str:
        """转换为提示词格式"""
        sections = []
        
        if self.creator_profile:
            sections.append(f"# 创作者特质\n{self.creator_profile}")
        
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
    INTENT_QUESTIONING_PROMPT = """你是一个专业的内容策略顾问。你的任务是通过提问帮助用户澄清内容生产的意图。

请根据用户已经提供的信息，提出1-2个最关键的追问，帮助用户明确：
1. 关于「这个内容要解决什么问题」：如果必须用一句话概括，你希望这次要做的内容，在目标客户/读者脑中"纠正/建立哪一个关键认知"？
2. 关于「写给谁看」：在你当前最重要的业务机会里，你最想影响的那一类决策者/使用者具体是谁？请用「岗位/角色 + 所在行业 + 当前面临的1-2个业务痛点」来描述他们，而不是笼统的"企业客户"或"技术人员"。
3. 关于「看到内容之后，你希望他做什么」：假设目标读者认真看完这篇内容，你最希望他立刻采取的一个"可见动作"是什么？

如果用户已经回答了某个问题，不要重复问。根据对话历史判断还需要了解什么。
问题要具体、有针对性，避免泛泛而谈。"""

    INTENT_PRODUCING_PROMPT = """你是一个专业的内容策略顾问。根据用户的回答，生成一份结构化的项目意图分析报告。

请输出以下结构的分析报告：

## 核心意图
[用一句话总结这个内容要解决的核心问题/建立的关键认知]

## 目标受众
- **角色定位**: [岗位/角色]
- **所在行业**: [行业领域]
- **核心痛点**: [1-2个业务痛点]

## 期望行动
[用户看完内容后期望采取的具体可见动作]

## 内容策略建议
- **内容调性**: [基于创作者特质和目标受众的建议]
- **核心价值主张**: [这个内容能提供的独特价值]
- **关键信息点**: [3-5个必须传达的关键点]

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

        "design_inner": """你是一个资深的内容架构师。基于项目意图和用户调研，设计内容生产方案。

你需要输出：
1. 内容策略建议
2. 推荐的内容结构/大纲
3. 建议使用的字段模板（如有）
4. 关键注意事项

设计要紧扣用户痛点和价值主张。""",

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
        fields_by_name: dict[str, ProjectField],
    ) -> tuple[str, list[ProjectField]]:
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
        
        # 添加字段特定的AI提示词
        if field.ai_prompt:
            parts.append(f"# 字段生成指导\n{field.ai_prompt}")
        
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

