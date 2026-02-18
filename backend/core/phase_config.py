# backend/core/phase_config.py
# 功能: 阶段配置的单一真相来源 (Single Source of Truth)
# 主要数据结构: PHASE_DEFINITIONS (有序列表), PHASE_ORDER, PHASE_DISPLAY_NAMES, PHASE_ALIAS
# 设计原则: 所有阶段相关的常量从此文件导入，避免 5+ 处重复定义

"""
项目阶段配置。

全系统唯一的阶段定义来源。新增或修改阶段只需改这一个文件。
"""

from typing import Dict, List

# ---- 阶段完整定义（有序） ----
# 每个阶段包含: code, display_name, special_handler(可选), position(固定位置)
PHASE_DEFINITIONS: List[Dict] = [
    {"code": "intent",        "display_name": "意图分析",   "special_handler": "intent",   "position": "top"},
    {"code": "research",      "display_name": "消费者调研", "special_handler": "research",  "position": "top"},
    {"code": "design_inner",  "display_name": "内涵设计",   "special_handler": None,            "position": "middle"},
    {"code": "produce_inner", "display_name": "内涵生产",   "special_handler": "produce_inner", "position": "middle"},
    {"code": "design_outer",  "display_name": "外延设计",   "special_handler": None,            "position": "middle"},
    {"code": "produce_outer", "display_name": "外延生产",   "special_handler": "produce_outer", "position": "middle"},
    {"code": "evaluate",      "display_name": "评估",       "special_handler": "evaluate",  "position": "bottom"},
]

# ---- 派生常量（不要手工维护，全部从 PHASE_DEFINITIONS 自动生成） ----

# 默认阶段顺序（项目创建时用）
PHASE_ORDER: List[str] = [p["code"] for p in PHASE_DEFINITIONS]

# 代码 → 中文显示名
PHASE_DISPLAY_NAMES: Dict[str, str] = {
    p["code"]: p["display_name"] for p in PHASE_DEFINITIONS
}

# 中文别名 → 代码（Agent 理解用户输入）
PHASE_ALIAS: Dict[str, str] = {
    p["display_name"]: p["code"] for p in PHASE_DEFINITIONS
}
# 额外别名
PHASE_ALIAS.update({
    "调研": "research",
    "消费者模拟": "simulate",  # 旧名称兼容
    "模拟": "simulate",
})

# 阶段状态定义
PHASE_STATUS_LABELS: Dict[str, str] = {
    "pending": "未开始",
    "in_progress": "进行中",
    "completed": "已完成",
}

# 各位置分组（前端排列用）
FIXED_TOP_PHASES: List[str] = [p["code"] for p in PHASE_DEFINITIONS if p["position"] == "top"]
DRAGGABLE_PHASES: List[str] = [p["code"] for p in PHASE_DEFINITIONS if p["position"] == "middle"]
FIXED_BOTTOM_PHASES: List[str] = [p["code"] for p in PHASE_DEFINITIONS if p["position"] == "bottom"]

# 有特殊处理器的阶段
PHASE_SPECIAL_HANDLERS: Dict[str, str] = {
    p["code"]: p["special_handler"]
    for p in PHASE_DEFINITIONS
    if p["special_handler"]
}


