# backend/tests/test_memory_budget_engine.py
# 功能: Token预算引擎单元测试
# 主要函数: test_compute_context_budget_defaults, test_select_memory_under_budget_prefers_relevant_constraints
# 数据结构: memories(tuple[index, text]) 输入与 budget 选择结果

"""
Token预算与记忆选择单元测试。

目标:
1) 验证预算参数输出稳定
2) 验证 select_memory_under_budget 在有限预算下优先选择高效用记忆
"""

from core.memory_service import compute_context_budget, select_memory_under_budget


def test_compute_context_budget_defaults():
    budget = compute_context_budget("any-model")
    assert budget["model_window"] == 128_000
    assert budget["soft_cap"] == 96_000
    assert budget["zone_a"] == int(0.7 * 96_000)
    assert budget["zone_b"] == int(0.9 * 96_000)
    assert budget["zone_c"] == 96_000


def test_select_memory_under_budget_prefers_relevant_constraints():
    memories = [
        (0, "普通记录：今天讨论了标题结构。"),
        (1, "关键约束：必须保留引用来源，禁止编造数据。"),
        (2, "偏好：用户偏好短句和清晰小标题。"),
        (3, "无关背景：团队午餐讨论。"),
    ]
    selected = select_memory_under_budget(
        memories=memories,
        budget_tokens=40,
        query_ctx="请确保引用来源准确且不要编造",
    )
    selected_text = "\n".join(text for _, text in selected)
    assert "必须保留引用来源" in selected_text
    assert "禁止编造数据" in selected_text

