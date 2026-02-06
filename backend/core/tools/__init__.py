# backend/core/tools/__init__.py
# 功能: 工具包入口，导出所有LangGraph工具
# 包含: deep_research, field_generator, simulator, evaluator, architecture_reader

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

from core.tools.architecture_reader import (
    get_project_architecture,
    get_phase_fields,
    get_field_content,
    get_content_block_tree,
    format_architecture_for_llm,
    ProjectArchitecture,
    PhaseInfo,
    FieldInfo,
    ContentBlockInfo,
)

from core.tools.architecture_writer import (
    modify_architecture,
    add_phase,
    remove_phase,
    reorder_phases,
    add_field,
    remove_field,
    update_field,
    move_field,
    ArchitectureOperation,
    OperationResult,
)

from core.tools.outline_generator import (
    generate_outline,
    apply_outline_to_project,
    ContentOutline,
    OutlineNode,
)

from core.tools.persona_manager import (
    manage_persona,
    create_persona,
    update_persona,
    select_persona,
    delete_persona,
    generate_persona,
    list_personas,
    PersonaOperation,
    Persona,
    PersonaResult,
)

from core.tools.skill_manager import (
    manage_skill,
    create_skill,
    update_skill,
    delete_skill,
    apply_skill,
    list_skills,
    get_skill,
    SkillOperation,
    Skill,
    SkillResult,
)

from core.tools.eval_engine import (
    run_eval,
    run_review_trial,
    run_consumer_dialogue_trial,
    run_seller_dialogue_trial,
    run_diagnoser,
    format_trial_result_markdown,
    format_diagnosis_markdown,
    TrialResult,
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
    
    # Architecture Reader
    "get_project_architecture",
    "get_phase_fields",
    "get_field_content",
    "get_content_block_tree",
    "format_architecture_for_llm",
    "ProjectArchitecture",
    "PhaseInfo",
    "FieldInfo",
    "ContentBlockInfo",
    
    # Architecture Writer
    "modify_architecture",
    "add_phase",
    "remove_phase",
    "reorder_phases",
    "add_field",
    "remove_field",
    "update_field",
    "move_field",
    "ArchitectureOperation",
    "OperationResult",
    
    # Outline Generator
    "generate_outline",
    "apply_outline_to_project",
    "ContentOutline",
    "OutlineNode",
    
    # Persona Manager
    "manage_persona",
    "create_persona",
    "update_persona",
    "select_persona",
    "delete_persona",
    "generate_persona",
    "list_personas",
    "PersonaOperation",
    "Persona",
    "PersonaResult",
    
    # Skill Manager
    "manage_skill",
    "create_skill",
    "update_skill",
    "delete_skill",
    "apply_skill",
    "list_skills",
    "get_skill",
    "SkillOperation",
    "Skill",
    "SkillResult",
    
    # Eval Engine
    "run_eval",
    "run_review_trial",
    "run_consumer_dialogue_trial",
    "run_seller_dialogue_trial",
    "run_diagnoser",
    "format_trial_result_markdown",
    "format_diagnosis_markdown",
    "TrialResult",
]
