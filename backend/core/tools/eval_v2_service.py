# backend/core/tools/eval_v2_service.py
# 功能: Eval V2 执行与聚合的纯函数工具（内容 hash、加权分、Task 聚合、过期检测）
# 主要函数: compute_content_hash, compute_weighted_grader_score, aggregate_task_scores, is_task_stale
# 数据结构:
#   - grader_results: [{grader_id, scores: {维度: 分数}, ...}]
#   - aggregate: {overall, dimensions, trial_count}

"""
Eval V2 纯函数工具层

约束：
1) 仅做计算，不直接访问数据库。
2) 对缺失数据保持容错，确保 API 层可稳定返回。
"""

from __future__ import annotations

import hashlib
from statistics import mean, pstdev


def compute_content_hash(content_list: list[str]) -> str:
    """对目标内容列表计算稳定 hash（顺序无关）。"""
    normalized = [c.strip() for c in content_list if isinstance(c, str) and c.strip()]
    payload = "||".join(sorted(normalized))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def compute_weighted_grader_score(grader_results: list, grader_weights: dict | None = None) -> tuple[float | None, dict]:
    """
    计算单次 Trial 的加权分数与维度均值。

    Returns:
        (overall_score, dimension_scores)
    """
    grader_weights = grader_weights or {}
    if not grader_results:
        return None, {}

    weighted_sum = 0.0
    weight_total = 0.0
    dimension_buckets: dict[str, list[float]] = {}

    for gr in grader_results:
        if not isinstance(gr, dict):
            continue
        gid = str(gr.get("grader_id", "") or gr.get("grader_name", ""))
        scores = gr.get("scores", {}) or {}
        numeric_scores = [float(v) for v in scores.values() if isinstance(v, (int, float))]
        if not numeric_scores:
            continue

        g_avg = mean(numeric_scores)
        w = float(grader_weights.get(gid, 1.0))
        weighted_sum += g_avg * w
        weight_total += w

        for dim, value in scores.items():
            if isinstance(value, (int, float)):
                dimension_buckets.setdefault(str(dim), []).append(float(value))

    if weight_total <= 0:
        return None, {}

    overall = round(weighted_sum / weight_total, 2)
    dim_scores = {k: round(mean(v), 2) for k, v in dimension_buckets.items() if v}
    return overall, dim_scores


def aggregate_task_scores(trial_results: list[dict]) -> dict:
    """
    聚合 Task 下全部 TrialResult 的统计分（mean/std/min/max）。
    """
    valid = [r for r in trial_results if isinstance(r, dict) and isinstance(r.get("overall_score"), (int, float))]
    trial_scores = [float(r["overall_score"]) for r in valid]

    if not trial_scores:
        return {"overall": None, "dimensions": {}, "trial_count": 0}

    overall_stats = {
        "mean": round(mean(trial_scores), 2),
        "std": round(pstdev(trial_scores), 2) if len(trial_scores) > 1 else 0.0,
        "min": round(min(trial_scores), 2),
        "max": round(max(trial_scores), 2),
    }

    dim_bucket: dict[str, list[float]] = {}
    for row in valid:
        dims = row.get("dimension_scores", {}) or {}
        for dim, value in dims.items():
            if isinstance(value, (int, float)):
                dim_bucket.setdefault(str(dim), []).append(float(value))

    dim_stats = {}
    for dim, values in dim_bucket.items():
        dim_stats[dim] = {
            "mean": round(mean(values), 2),
            "std": round(pstdev(values), 2) if len(values) > 1 else 0.0,
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    return {"overall": overall_stats, "dimensions": dim_stats, "trial_count": len(trial_scores)}


def is_task_stale(saved_hash: str, current_hash: str) -> bool:
    """判断 Task 是否过期。"""
    if not saved_hash or not current_hash:
        return False
    return saved_hash != current_hash


