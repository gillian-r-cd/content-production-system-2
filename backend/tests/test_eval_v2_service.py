# backend/tests/test_eval_v2_service.py
# 功能: 验证 Eval V2 纯函数工具的关键计算逻辑（hash、加权分、任务聚合）
# 主要函数: test_compute_content_hash_is_order_insensitive, test_weighted_grader_score, test_aggregate_task_scores
# 数据结构:
#   - grader_results: 多评分器维度分
#   - trial_results: 多次执行的 overall + dimension_scores

from core.tools.eval_v2_service import (
    compute_content_hash,
    compute_weighted_grader_score,
    aggregate_task_scores,
    is_task_stale,
)


def test_compute_content_hash_is_order_insensitive():
    a = compute_content_hash(["A", "B", "C"])
    b = compute_content_hash(["C", "B", "A"])
    assert a == b


def test_weighted_grader_score():
    overall, dims = compute_weighted_grader_score(
        grader_results=[
            {"grader_id": "g1", "scores": {"结构": 6, "价值": 8}},
            {"grader_id": "g2", "scores": {"结构": 8, "价值": 8}},
        ],
        grader_weights={"g1": 1.0, "g2": 2.0},
    )
    assert overall == 7.67
    assert dims["结构"] == 7.0
    assert dims["价值"] == 8.0


def test_aggregate_task_scores():
    agg = aggregate_task_scores(
        [
            {"overall_score": 6.0, "dimension_scores": {"结构": 6, "价值": 7}},
            {"overall_score": 8.0, "dimension_scores": {"结构": 8, "价值": 8}},
            {"overall_score": 7.0, "dimension_scores": {"结构": 7, "价值": 9}},
        ]
    )
    assert agg["overall"]["mean"] == 7.0
    assert agg["overall"]["min"] == 6.0
    assert agg["overall"]["max"] == 8.0
    assert agg["dimensions"]["结构"]["mean"] == 7.0
    assert agg["dimensions"]["价值"]["mean"] == 8.0


def test_is_task_stale():
    old_hash = compute_content_hash(["x", "y"])
    same_hash = compute_content_hash(["y", "x"])
    new_hash = compute_content_hash(["x", "z"])
    assert not is_task_stale(old_hash, same_hash)
    assert is_task_stale(old_hash, new_hash)


