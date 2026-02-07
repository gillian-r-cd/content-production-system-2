# backend/core/models/grader.py
# 功能: Grader（评分器）模型 - Eval 体系的独立评分器
# 主要类: Grader
# 数据结构:
#   - grader_type: "content_only" (仅评内容) 或 "content_and_process" (评内容+互动过程)
#   - prompt_template: 用户自写的评分提示词，支持 {{field:字段名}} 动态引用
#   - dimensions: 评分维度列表
#   - scoring_criteria: {维度名: 评分标准描述}

"""
Grader 模型 - 独立的评分器实体
可在后台设置中管理，EvalTask 的每个 Trial 引用一个 Grader
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# Grader 类型
GRADER_TYPE_CHOICES = {
    "content_only": {
        "name": "仅评内容",
        "description": "直接评价内容本身的质量，不传递互动过程上下文",
    },
    "content_and_process": {
        "name": "评内容+互动过程",
        "description": "同时评价内容和 Simulator 互动过程，传递完整对话上下文",
    },
}

# 预置 Grader 模板
PRESET_GRADERS = [
    {
        "name": "策略对齐评分器",
        "grader_type": "content_only",
        "prompt_template": """请从战略策略层面评估以下内容：

【评估内容】
{{content}}

【评估维度】
1. 策略对齐度 (1-10): 内容方向是否与项目意图一致？
2. 定位清晰度 (1-10): 目标受众是否明确？
3. 差异化程度 (1-10): 与同类内容相比，差异化是否足够？
4. 完整性 (1-10): 是否有战略性的遗漏或偏差？

请输出 JSON 格式：
{"scores": {"策略对齐度": N, "定位清晰度": N, "差异化程度": N, "完整性": N}, "overall": N, "feedback": "..."}""",
        "dimensions": ["策略对齐度", "定位清晰度", "差异化程度", "完整性"],
        "scoring_criteria": {},
        "is_preset": True,
    },
    {
        "name": "内容质量评分器",
        "grader_type": "content_only",
        "prompt_template": """请从内容质量层面评估以下内容：

【评估内容】
{{content}}

【评估维度】
1. 结构合理性 (1-10): 结构是否清晰、逻辑是否连贯？
2. 语言质量 (1-10): 表达是否准确、流畅、无冗余？
3. 风格一致性 (1-10): 风格是否统一、符合创作者特质？
4. 可读性 (1-10): 目标读者是否能轻松理解？

请输出 JSON 格式：
{"scores": {"结构合理性": N, "语言质量": N, "风格一致性": N, "可读性": N}, "overall": N, "feedback": "..."}""",
        "dimensions": ["结构合理性", "语言质量", "风格一致性", "可读性"],
        "scoring_criteria": {},
        "is_preset": True,
    },
    {
        "name": "消费者体验评分器",
        "grader_type": "content_and_process",
        "prompt_template": """请从消费者体验角度评估以下内容及互动过程：

【评估内容】
{{content}}

【互动过程】
{{process}}

【评估维度】
1. 需求匹配度 (1-10): 内容是否解决了消费者的核心痛点？
2. 理解难度 (1-10): 内容是否容易被目标读者理解？
3. 价值感知 (1-10): 消费者是否感受到明确的价值？
4. 行动意愿 (1-10): 消费者看完后是否有行动意愿（购买/分享/收藏）？

请输出 JSON 格式：
{"scores": {"需求匹配度": N, "理解难度": N, "价值感知": N, "行动意愿": N}, "overall": N, "feedback": "..."}""",
        "dimensions": ["需求匹配度", "理解难度", "价值感知", "行动意愿"],
        "scoring_criteria": {},
        "is_preset": True,
    },
    {
        "name": "销售转化评分器",
        "grader_type": "content_and_process",
        "prompt_template": """请从销售转化角度评估以下内容及销售互动过程：

【评估内容】
{{content}}

【互动过程】
{{process}}

【评估维度】
1. 价值传达 (1-10): 内容的核心价值是否被有效传达？
2. 需求匹配 (1-10): 是否成功匹配了消费者需求？
3. 异议处理 (1-10): 消费者的疑虑是否被有效回应？
4. 转化结果 (1-10): 最终是否达成转化（或接近转化）？

请输出 JSON 格式：
{"scores": {"价值传达": N, "需求匹配": N, "异议处理": N, "转化结果": N}, "overall": N, "feedback": "..."}""",
        "dimensions": ["价值传达", "需求匹配", "异议处理", "转化结果"],
        "scoring_criteria": {},
        "is_preset": True,
    },
]


class Grader(BaseModel):
    """
    评分器 - Eval 体系的独立评分实体
    
    grader_type 决定传给 LLM 的上下文范围：
      - content_only: 只传内容
      - content_and_process: 传内容 + Simulator 互动过程日志
    
    prompt_template 支持动态占位符：
      - {{content}}: 被评估内容（自动填充）
      - {{process}}: 互动过程日志（仅 content_and_process 时填充）
      - {{field:字段名}}: 引用项目中指定字段的内容
    """
    __tablename__ = "graders"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    grader_type: Mapped[str] = mapped_column(
        String(30), default="content_only"
    )  # content_only / content_and_process
    
    prompt_template: Mapped[str] = mapped_column(
        Text, default=""
    )  # 自定义评分提示词
    
    dimensions: Mapped[list] = mapped_column(
        JSON, default=list
    )  # 评分维度名称列表
    
    scoring_criteria: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {维度名: 评分标准描述}
    
    is_preset: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # 是否系统预置

    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )  # null = 全局 / 预置，有值 = 项目专用


