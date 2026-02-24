"""
DeepResearch 20条样本评测入口脚本。

运行:
  cd backend && python -m scripts.eval_deepresearch_metrics --samples scripts/data/deepresearch_samples_20.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.deepresearch_metrics import score_deepresearch_sample, aggregate_scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--samples",
        default="scripts/data/deepresearch_samples_20.json",
        help="样本文件路径（JSON 数组）",
    )
    parser.add_argument(
        "--output",
        default="scripts/data/deepresearch_eval_report.json",
        help="评测输出文件路径",
    )
    parser.add_argument(
        "--ignore-pending",
        action="store_true",
        help="忽略 status=pending_execution 的样本",
    )
    args = parser.parse_args()

    sample_path = Path(args.samples)
    if not sample_path.exists():
        raise FileNotFoundError(f"样本文件不存在: {sample_path}")

    samples = json.loads(sample_path.read_text(encoding="utf-8"))
    if not isinstance(samples, list):
        raise ValueError("样本文件必须是 JSON 数组")

    if args.ignore_pending:
        samples = [s for s in samples if s.get("status") != "pending_execution"]

    score_rows = []
    score_objects = []
    for idx, sample in enumerate(samples, 1):
        score = score_deepresearch_sample(sample)
        score_objects.append(score)
        score_rows.append({
            "index": idx,
            "request": sample.get("request", ""),
            "score": score.to_dict(),
        })

    summary = aggregate_scores(score_objects)
    output = {
        "summary": summary,
        "input_count": len(samples),
        "items": score_rows,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DeepResearch 评测完成:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"详细报告已写入: {out_path}")


if __name__ == "__main__":
    main()

