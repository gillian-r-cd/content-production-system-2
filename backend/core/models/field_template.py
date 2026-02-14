# backend/core/models/field_template.py
# 功能: 字段模板模型，全局共享的可复用模板
# 主要类: FieldTemplate
# 常量: EVAL_TEMPLATE_V2 — 综合评估模板的规范定义（单一事实来源）
# 数据结构: 存储字段定义、依赖关系、AI提示词等

"""
字段模板模型
全局共享，可在多个项目中复用
每个模板包含若干字段定义及其关联关系
"""

from typing import Optional, List

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# ============================================================
# 综合评估模板 V2 — 单一事实来源（init_db / startup 共用）
# 如需修改评估模板，只需修改此处，系统启动时会自动同步到数据库
# ============================================================
EVAL_TEMPLATE_V2_NAME = "综合评估模板"
EVAL_TEMPLATE_V2_DESCRIPTION = (
    "Eval V2 综合评估模板：目标画像 → 任务配置 → 评估报告（执行+评分+诊断一体化）。"
    "支持自定义 simulator × persona × grader 组合，并行执行无限 trial。"
)
EVAL_TEMPLATE_V2_CATEGORY = "评估"
EVAL_TEMPLATE_V2_FIELDS = [
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


class FieldTemplate(BaseModel):
    """
    字段模板（全局共享）
    
    Attributes:
        name: 模板名称
        description: 模板描述
        category: 分类（如"课程"、"文章"、"营销"）
        fields: 字段定义列表，每个字段包含:
            - name: 字段名
            - type: 类型 (text/richtext/list/structured)
            - ai_prompt: AI生成提示词
            - pre_questions: 生成前提问列表
            - depends_on: 依赖的字段名列表
            - dependency_type: 依赖类型 (all/any)
    
    Example fields:
        [
            {
                "name": "课程目标",
                "type": "text",
                "ai_prompt": "基于项目意图，明确课程的核心学习目标...",
                "pre_questions": ["目标学员的现有水平是？"],
                "depends_on": [],
                "dependency_type": "all"
            },
            {
                "name": "课程大纲",
                "type": "structured",
                "ai_prompt": "根据课程目标，设计详细的课程大纲...",
                "pre_questions": [],
                "depends_on": ["课程目标"],
                "dependency_type": "all"
            }
        ]
    """
    __tablename__ = "field_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="通用")
    fields: Mapped[list] = mapped_column(JSON, default=list)

    def get_field_names(self) -> List[str]:
        """获取所有字段名"""
        return [f["name"] for f in self.fields]

    def get_field_by_name(self, name: str) -> Optional[dict]:
        """根据名称获取字段定义"""
        for field in self.fields:
            if field["name"] == name:
                return field
        return None

    def validate_dependencies(self) -> List[str]:
        """验证依赖关系，返回错误列表"""
        errors = []
        field_names = set(self.get_field_names())
        
        for field in self.fields:
            for dep in field.get("depends_on", []):
                if dep not in field_names:
                    errors.append(
                        f"字段'{field['name']}'依赖的'{dep}'不存在"
                    )
        
        # 检测循环依赖
        # TODO: 实现拓扑排序检测
        
        return errors


