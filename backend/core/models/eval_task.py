# backend/core/models/eval_task.py
# 功能: 评估任务模型 - EvalRun 和 EvalTrial 之间的可组合配置层
# 主要类: EvalTask
# 数据结构:
#   - simulator_type: 模拟器角色类型 (coach/editor/expert/consumer/seller/custom)
#   - interaction_mode: 交互模式 (review/dialogue/scenario)
#   - persona_config: 使用的消费者画像配置
#   - target_block_ids: 评估的内容块范围
#   - grader_config: 评分器配置 (评估维度、评分标准、评分模式)

"""
EvalTask 模型
一个 Task = 一个可组合的评估配置单元
用户可以自由组合 simulator_type × interaction_mode × persona × grader 来创建任务
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.eval_run import EvalRun
    from core.models.eval_trial import EvalTrial


# 预置的 Simulator 角色类型
SIMULATOR_TYPES = {
    "coach": {
        "name": "教练",
        "icon": "🎯",
        "description": "策略视角：内容方向是否正确？意图是否对齐？",
        "default_interaction": "review",
        "default_dimensions": ["策略对齐度", "定位清晰度", "差异化程度", "完整性"],
        "system_prompt": """你是一位资深的内容策略教练。你的视角是**战略层面**：
【你的身份】你拥有丰富的内容策略经验，擅长判断内容方向是否正确、定位是否清晰。
【评估任务】从策略视角审查内容，评估：
1. 内容方向是否与项目意图一致？
2. 定位是否清晰？目标受众是否明确？
3. 与同类内容相比，差异化在哪？
4. 是否有战略性的遗漏或偏差？""",
    },
    "editor": {
        "name": "编辑",
        "icon": "✍️",
        "description": "手艺视角：内容质量是否过关？结构是否合理？",
        "default_interaction": "review",
        "default_dimensions": ["结构合理性", "语言质量", "风格一致性", "可读性"],
        "system_prompt": """你是一位资深的内容编辑。你的视角是**手艺层面**：
【你的身份】你有多年编辑经验，对内容的结构、语言、节奏有极高的标准。
【评估任务】从编辑专业视角审查内容，评估：
1. 结构是否合理？逻辑是否连贯？
2. 语言质量如何？是否有表达不清、冗余或矛盾？
3. 风格是否一致？是否符合创作者特质？
4. 开头是否吸引人？结尾是否有力？""",
    },
    "expert": {
        "name": "领域专家",
        "icon": "🔬",
        "description": "专业视角：内容是否准确？是否具有专业性？",
        "default_interaction": "review",
        "default_dimensions": ["事实准确性", "专业深度", "数据支撑", "行业相关性"],
        "system_prompt": """你是一位该领域的资深专家。你的视角是**专业层面**：
【你的身份】你在这个领域有深厚的知识积累和实践经验。
【评估任务】从专业视角审查内容，评估：
1. 内容是否准确？有没有事实性错误？
2. 专业深度是否足够？
3. 是否有数据/案例支撑关键论点？
4. 有没有遗漏的重要方面？""",
    },
    "consumer": {
        "name": "消费者",
        "icon": "👤",
        "description": "用户视角：内容对我有用吗？能解决我的问题吗？",
        "default_interaction": "dialogue",
        "default_dimensions": ["需求匹配度", "理解难度", "价值感知", "行动意愿"],
        "system_prompt": """你是一位真实的目标消费者。请完全代入以下角色：
【行为要求】
1. 完全代入角色，基于你的背景和真实需求做出判断
2. 如果内容对你有帮助，具体说明是哪些部分
3. 如果有困惑或不满，诚实表达
4. 最终判断：你会推荐这个内容给朋友吗？""",
    },
    "seller": {
        "name": "内容销售",
        "icon": "💰",
        "description": "转化视角：能把这个内容卖出去吗？",
        "default_interaction": "dialogue",
        "default_dimensions": ["价值传达", "需求匹配", "异议处理", "转化结果"],
        "system_prompt": """你是这个内容的销售顾问。你深入了解内容的每个细节。
【销售策略】
1. 先了解消费者的具体需求（2-3个问题）
2. 根据需求匹配内容中的价值点
3. 如果消费者有疑虑，用内容中的具体事实回应
4. 争取让消费者认可内容的价值""",
    },
}

# 交互模式
INTERACTION_MODES = {
    "review": {
        "name": "审查模式",
        "description": "一次性阅读全部内容，给出结构化反馈",
    },
    "dialogue": {
        "name": "对话模式",
        "description": "多轮交互，模拟真实用户与内容的互动",
    },
    "scenario": {
        "name": "场景模式",
        "description": "模拟特定场景流程（如销售、咨询）",
    },
}

# Grader 类型
GRADER_TYPES = {
    "content": {
        "name": "内容评分器",
        "description": "直接评价内容本身的质量",
    },
    "process": {
        "name": "过程评分器",
        "description": "评价互动过程的质量（对话流畅性、问题解决等）",
    },
    "combined": {
        "name": "综合评分器",
        "description": "同时评价内容和互动过程",
    },
}

# Task 状态
EVAL_TASK_STATUS = {
    "pending": "待运行",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "skipped": "已跳过",
}


class EvalTask(BaseModel):
    """
    评估任务 - 可组合的评估配置单元
    
    一个 Task 定义了「用什么角色 × 什么交互方式 × 什么人设 × 评什么内容 × 怎么评分」
    
    Attributes:
        eval_run_id: 关联的 EvalRun
        name: 任务名称（如"教练审查"、"消费者对话-张晨"）
        simulator_type: 模拟器角色类型 (coach/editor/expert/consumer/seller/custom)
        interaction_mode: 交互模式 (review/dialogue/scenario)
        simulator_config: 模拟器自定义配置
            - system_prompt: 覆盖默认系统提示词
            - max_turns: 最大对话轮数
            - feedback_mode: 反馈方式 (structured/freeform)
        persona_config: 消费者画像配置
            - persona_id: 引用的 persona ID（来自消费者调研）
            - name: 名称
            - background: 背景
            - pain_points: 痛点列表
            - (其他自定义字段)
        target_block_ids: 要评估的内容块 ID 列表（空=全部）
        grader_config: 评分器配置
            - type: content/process/combined
            - dimensions: 评分维度列表
            - criteria: 各维度的评分标准描述
            - custom_prompt: 自定义评分提示词
        order_index: 任务排序
        status: 状态
    """
    __tablename__ = "eval_tasks"

    eval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id"), nullable=False
    )
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    simulator_type: Mapped[str] = mapped_column(String(50), default="coach")
    interaction_mode: Mapped[str] = mapped_column(String(50), default="review")
    
    simulator_config: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "system_prompt": "",  # 空=使用 simulator_type 的默认提示词
            "max_turns": 5,
            "feedback_mode": "structured",
        }
    )
    
    persona_config: Mapped[dict] = mapped_column(JSON, default=dict)
    target_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    
    grader_config: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "type": "content",  # content / process / combined
            "dimensions": [],   # 空=使用 simulator_type 的默认维度
            "criteria": {},     # {维度名: 评分标准描述}
            "custom_prompt": "",
        }
    )
    
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")

    # 关联
    eval_run: Mapped["EvalRun"] = relationship(
        "EvalRun", back_populates="tasks"
    )
    trials: Mapped[List["EvalTrial"]] = relationship(
        "EvalTrial", back_populates="eval_task",
        cascade="all, delete-orphan"
    )

    def get_effective_dimensions(self) -> list:
        """获取生效的评分维度（自定义优先，否则用默认）"""
        custom = self.grader_config.get("dimensions", [])
        if custom:
            return custom
        type_info = SIMULATOR_TYPES.get(self.simulator_type, {})
        return type_info.get("default_dimensions", ["综合评价"])

    def get_effective_prompt(self) -> str:
        """获取生效的系统提示词（自定义优先，否则用默认）"""
        custom = self.simulator_config.get("system_prompt", "")
        if custom:
            return custom
        type_info = SIMULATOR_TYPES.get(self.simulator_type, {})
        return type_info.get("system_prompt", "请评估以下内容。")

