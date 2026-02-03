# backend/core/tools/__init__.py
# 功能: 工具包入口，导出所有LangGraph工具
# 包含: deep_research, field_generator, simulator, evaluator

"""
LangGraph 工具包
提供 Agent 可调用的各种工具
"""

from core.tools.deep_research import (
    deep_research,
    quick_research,
    ResearchReport,
    ConsumerPersona,
)

from core.tools.field_generator import (
    generate_field,
    generate_field_stream,
    generate_fields_parallel,
    resolve_field_order,
    FieldGenerationResult,
)

from core.tools.simulator import (
    run_simulation,
    run_reading_simulation,
    run_dialogue_simulation,
    run_decision_simulation,
    run_exploration_simulation,
    run_experience_simulation,
    SimulationResult,
    SimulationFeedback,
)

from core.tools.evaluator import (
    evaluate_project,
    evaluate_section,
    generate_suggestions,
    EvaluationResult,
    SectionScore,
    Suggestion,
)

__all__ = [
    # DeepResearch
    "deep_research",
    "quick_research",
    "ResearchReport",
    "ConsumerPersona",
    
    # Field Generator
    "generate_field",
    "generate_field_stream",
    "generate_fields_parallel",
    "resolve_field_order",
    "FieldGenerationResult",
    
    # Simulator
    "run_simulation",
    "run_reading_simulation",
    "run_dialogue_simulation",
    "run_decision_simulation",
    "run_exploration_simulation",
    "run_experience_simulation",
    "SimulationResult",
    "SimulationFeedback",
    
    # Evaluator
    "evaluate_project",
    "evaluate_section",
    "generate_suggestions",
    "EvaluationResult",
    "SectionScore",
    "Suggestion",
]
