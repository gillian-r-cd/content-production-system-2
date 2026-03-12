# backend/core/prompt_engine.py
# 功能: 提示词引擎，负责创作者特质注入、字段依赖解析、@引用解析
# 主要类: PromptEngine, GoldenContext
# 主要函数: build_golden_context(), build_prompt_context(), parse_references()

"""
提示词引擎

核心设计原则（2026-02重构）:
1. 创作者特质（creator_profile）是唯一的全局上下文，注入到每个 LLM 调用
2. 意图分析、消费者调研等阶段输出通过「字段依赖关系」传递，而非全局上下文
3. @引用语法用于用户手动引用特定字段内容

关键概念区分:
- GoldenContext: 只包含 creator_profile，每次 LLM 调用必须注入
- field_context: 通过 depends_on 配置的字段内容，作为参考信息注入
- 两者职责不同，不应混淆
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from core.content_block_reference import build_block_reference_lookup
from core.locale_text import markdown_instructions, rt, rt_template
from core.localization import DEFAULT_LOCALE, locale_fallback_chain, normalize_locale
from core.models import (
    Project, 
    CreatorProfile, 
    ContentBlock,
    Channel,
)
from core.pre_question_utils import iter_answered_pre_question_items

PHASE_PROMPT_RUNTIME_KEYS = {
    "intent": "phase_prompt.intent.questioning",
    "research": "phase_prompt.research",
    "design_inner": "phase_prompt.design_inner",
    "produce_inner": "phase_prompt.produce_inner",
    "design_outer": "phase_prompt.design_outer",
    "produce_outer": "phase_prompt.produce_outer",
    "evaluate": "phase_prompt.evaluate",
}

PHASE_PROMPTS_ZH = {
    phase: rt_template(DEFAULT_LOCALE, runtime_key)
    for phase, runtime_key in PHASE_PROMPT_RUNTIME_KEYS.items()
}

PHASE_PROMPTS_JA = {
    phase: rt_template("ja-JP", runtime_key)
    for phase, runtime_key in PHASE_PROMPT_RUNTIME_KEYS.items()
}


@dataclass
class GoldenContext:
    """
    创作者特质上下文 - 每次LLM调用必须注入的唯一全局上下文
    
    设计说明:
    - 只包含 creator_profile（创作者的风格、语气、禁忌等）
    - 这是项目级别的全局设置，与具体字段无关
    
    不属于此处的内容（应通过字段依赖传递）:
    - 意图分析结果 → 配置 depends_on: ["意图分析"]
    - 消费者调研结果 → 配置 depends_on: ["消费者调研"] 
    - 其他阶段输出 → 通过字段依赖关系获取
    """
    creator_profile: str = ""
    locale: str = DEFAULT_LOCALE
    
    def to_prompt(self) -> str:
        """转换为提示词格式"""
        if self.creator_profile:
            if self.creator_profile.lstrip().startswith("#"):
                return self.creator_profile
            return f"{rt(self.locale, 'golden_context.creator_profile_header')}\n{self.creator_profile}"
        return ""
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return not self.creator_profile


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
        """
        构建完整的系统提示词。
        
        核心原则：phase_context 就是完整模板（所见即所得）。
        引擎只负责替换占位符 {creator_profile} / {dependencies} / {channel}。
        如果模板中没有占位符（旧格式兼容），则使用传统拼接方式。
        """
        locale = normalize_locale(getattr(self.golden_context, "locale", DEFAULT_LOCALE))
        creator_profile_text = self.golden_context.creator_profile or rt(locale, "fallback.no_creator_profile")
        dependencies_text = self.field_context or rt(locale, "fallback.no_dependencies")
        channel_text = self.channel_context or rt(locale, "fallback.no_channel")
        
        template = self.phase_context or ""
        
        # 检测是否为新格式模板（包含占位符）
        has_placeholders = (
            "{creator_profile}" in template
            or "{dependencies}" in template
            or "{channel}" in template
        )
        
        if has_placeholders:
            # 新格式：直接替换占位符，模板即最终提示词
            result = template
            result = result.replace("{creator_profile}", creator_profile_text)
            result = result.replace("{dependencies}", dependencies_text)
            result = result.replace("{channel}", channel_text)
            
            # 追加自定义上下文（如有）
            if self.custom_context:
                result += f"\n\n---\n\n{self.custom_context}"
            
            return result
        else:
            # 旧格式兼容：拼接各段
            parts = []
            
            gc = self.golden_context.to_prompt()
            if gc:
                parts.append(gc)
            
            if self.phase_context:
                parts.append(f"{rt(locale, 'block.task_header')}\n{self.phase_context}")
            
            if self.field_context:
                parts.append(f"{rt(locale, 'block.reference_header')}\n{self.field_context}")
            
            if self.channel_context:
                parts.append(f"{rt(locale, 'prompt_context.channel_header')}\n{self.channel_context}")
            
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
    
    INTENT_QUESTIONING_PROMPT = PHASE_PROMPTS_ZH["intent"]
    INTENT_PRODUCING_PROMPT = rt_template(DEFAULT_LOCALE, "phase_prompt.intent.producing")
    JA_PHASE_PROMPTS = PHASE_PROMPTS_JA
    PHASE_PROMPTS = PHASE_PROMPTS_ZH
    
    def __init__(self):
        pass
    
    def _get_phase_prompt(self, phase: str, db=None, locale: Optional[str] = None) -> str:
        """
        获取阶段提示词。
        优先级：DB system_prompts 表（后台可编辑）> 内置 PHASE_PROMPTS
        
        Args:
            phase: 阶段标识 (intent, research, design_inner, ...)
            db: SQLAlchemy Session（可选）
        """
        if db:
            try:
                from core.models.system_prompt import SystemPrompt
                for candidate in locale_fallback_chain(locale):
                    db_prompt = db.query(SystemPrompt).filter(
                        SystemPrompt.phase == phase,
                        SystemPrompt.locale == candidate,
                    ).first()
                    if db_prompt and db_prompt.content:
                        return db_prompt.content
            except Exception:
                pass
        # 兜底使用内置
        prompt_map = self.JA_PHASE_PROMPTS if normalize_locale(locale) == "ja-JP" else self.PHASE_PROMPTS
        return prompt_map.get(phase, "")

    def build_golden_context(
        self,
        project: Project,
        creator_profile: Optional[CreatorProfile] = None,
    ) -> GoldenContext:
        """
        构建Golden Context - 只包含创作者特质
        
        重要说明（2026-02重构）:
        - GoldenContext 只包含 creator_profile，全局注入到每个 LLM 调用
        - intent 和 consumer_personas 应通过字段依赖关系传递
        - 不再从 project.golden_context 读取任何内容
        
        Args:
            project: 项目对象
            creator_profile: 创作者特质（可选，如未提供则从project关联获取）
        """
        gc = GoldenContext(locale=normalize_locale(getattr(project, "locale", DEFAULT_LOCALE)))
        
        # 创作者特质 - 唯一的全局上下文
        profile = creator_profile or getattr(project, 'creator_profile', None)
        if profile:
            gc.creator_profile = profile.to_prompt_context(locale=gc.locale)
        
        return gc
    
    def build_prompt_context(
        self,
        project: Project,
        phase: str,
        golden_context: Optional[GoldenContext] = None,
        dependent_fields: Optional[list[ContentBlock]] = None,
        channel: Optional[Channel] = None,
        custom_prompt: str = "",
        db=None,
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
            db: SQLAlchemy Session（可选，传入则从 DB 加载后台配置的提示词）
        """
        ctx = PromptContext()
        
        # Golden Context
        ctx.golden_context = golden_context or self.build_golden_context(project)
        
        # 阶段提示词：优先从DB加载（后台可编辑），兜底使用内置
        ctx.phase_context = self._get_phase_prompt(
            phase,
            db=db,
            locale=normalize_locale(getattr(project, "locale", DEFAULT_LOCALE)),
        )
        
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

    def build_reference_lookup(self, fields: List[ContentBlock]) -> Dict[str, ContentBlock]:
        """
        构建稳定引用映射。

        规则：
        - `id:块ID` 与裸 `块ID` 始终可用
        - 名称仅在项目内唯一时才可用，避免重名字段静默覆盖
        """
        return build_block_reference_lookup(fields)
    
    def parse_references(
        self,
        text: str,
        fields_by_name: Dict[str, ContentBlock],
        locale: Optional[str] = None,
    ) -> Tuple[str, List[ContentBlock]]:
        """
        解析@引用语法，支持含空格的字段名
        
        策略：优先按已知字段名贪婪匹配（最长优先），
        兼容 @xxx.yyy 阶段.字段名格式，
        最后回退到简单正则。
        
        Args:
            text: 包含@引用的文本
            fields_by_name: {字段名: ContentBlock} 映射
        
        Returns:
            (替换后的文本, 引用的字段列表)
        """
        target_locale = normalize_locale(locale)
        referenced_fields = []
        seen_field_ids = set()

        all_fields = [field for field in fields_by_name.values() if field]
        fields_by_ref = self.build_reference_lookup(all_fields)

        # 兼容调用方显式传入的额外引用键（例如阶段别名），但不覆盖稳定 ID / 唯一名称策略。
        for key, field in fields_by_name.items():
            ref_key = str(key).strip()
            if ref_key and ref_key not in fields_by_ref and field:
                fields_by_ref[ref_key] = field

        # 按字段名长度降序排列，确保最长名称优先匹配
        # 这样 "Eval test" 会优先于 "Eval" 被匹配
        sorted_names = sorted(fields_by_ref.keys(), key=len, reverse=True)
        
        # 边界字符（名称后必须跟这些字符或字符串结尾）
        boundary_chars = set(' \t\n，。！？、：；""''（）@')
        stop_words = set('的了吗呢吧啊是在有和与或及到从把被让给对比跟向往于着过')
        
        result = text
        used_ranges = []  # 已匹配的区间，防止重复
        
        # 第一遍：按已知字段名贪婪匹配
        for name in sorted_names:
            search_start = 0
            while True:
                pos = result.find(f"@{name}", search_start)
                if pos < 0:
                    break
                
                end_pos = pos + 1 + len(name)
                
                # 检查是否与已有匹配区间重叠
                overlaps = any(s <= pos < e for s, e in used_ranges)
                if overlaps:
                    search_start = pos + 1
                    continue
                
                # 检查边界
                if end_pos < len(result):
                    char_after = result[end_pos]
                    if char_after not in boundary_chars and char_after not in stop_words:
                        search_start = pos + 1
                        continue
                
                field = fields_by_ref[name]
                field_id = getattr(field, "id", None)
                if field_id not in seen_field_ids:
                    referenced_fields.append(field)
                    if field_id:
                        seen_field_ids.add(field_id)
                replacement = self._format_reference_block(field, name, locale=target_locale)
                result = result[:pos] + replacement + result[end_pos:]
                used_ranges.append((pos, pos + len(replacement)))
                search_start = pos + len(replacement)
        
        # 第二遍：处理 @阶段.字段名 格式 和 未匹配的 @引用（回退正则）
        word_chars = r'a-zA-Z0-9_\-\u4e00-\u9fff'
        stop_chars_re = r'的了吗呢吧啊是在有和与或及到从把被让给对比跟向往于着过'
        punct_chars_re = r'，。！？、：；""''（）'
        pattern = rf'@((?:id:)?[{word_chars}]+(?:\.[{word_chars}]+)?)(?=[{stop_chars_re}]|[{punct_chars_re}\s]|$)'
        
        def replace_ref(match):
            ref = match.group(1)
            
            # 直接匹配（可能在第一遍已处理）
            if ref in fields_by_ref:
                field = fields_by_ref[ref]
                field_id = getattr(field, "id", None)
                if field_id not in seen_field_ids:
                    referenced_fields.append(field)
                    if field_id:
                        seen_field_ids.add(field_id)
                return self._format_reference_block(field, ref, locale=target_locale)
            
            # 阶段.字段名 格式
            if '.' in ref:
                _, field_name = ref.split('.', 1)
                if field_name in fields_by_ref:
                    field = fields_by_ref[field_name]
                    field_id = getattr(field, "id", None)
                    if field_id not in seen_field_ids:
                        referenced_fields.append(field)
                        if field_id:
                            seen_field_ids.add(field_id)
                    return self._format_reference_block(field, ref, locale=target_locale)
            
            return match.group(0)
        
        result = re.sub(pattern, replace_ref, result)
        
        return result, referenced_fields

    def _format_reference_block(
        self,
        field: ContentBlock,
        reference_key: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> str:
        """将引用块格式化为稳定、可回显的文本。"""
        label = getattr(field, "name", "") or reference_key
        field_id = getattr(field, "id", "") or ""
        content = getattr(field, "content", "") or rt(locale, "agent.reference_context.empty_content")
        id_suffix = f" | id:{field_id}" if field_id else ""
        return (
            f"\n\n---\n"
            f"{rt(locale, 'agent.reference_context.target', label=f'{label}{id_suffix}')}\n"
            f"{content}\n"
            f"---\n\n"
        )
    
    def get_field_generation_prompt(
        self,
        field: ContentBlock,
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
        locale = normalize_locale(getattr(context.golden_context, "locale", DEFAULT_LOCALE))
        parts = [context.to_system_prompt()]
        
        # 添加字段基本信息
        parts.append(
            f"{rt(locale, 'prompt_context.field_target_header')}\n"
            f"{rt(locale, 'prompt_context.field_name_line', name=field.name)}"
        )
        
        # 固定 Markdown 输出格式指令（前端统一使用 ReactMarkdown 渲染）
        parts.append(markdown_instructions(locale))
        
        # 添加字段特定的AI提示词（核心指令）
        if field.ai_prompt and field.ai_prompt.strip() and field.ai_prompt != "请在这里编写生成提示词...":
            parts.append(f"{rt(locale, 'prompt_context.field_requirement_header')}\n{field.ai_prompt}")

        # 添加用户回答的预问题
        if field.pre_answers:
            answers_text = "\n".join(
                f"- {item['question']}: {answer}"
                for item, answer in iter_answered_pre_question_items(
                    getattr(field, "pre_questions", None) or [],
                    field.pre_answers or {},
                )
            )
            if answers_text:
                parts.append(rt(locale, "prompt_context.field_pre_answers_header", answers=answers_text))
        
        return "\n\n---\n\n".join(parts)


# 单例
prompt_engine = PromptEngine()

