# backend/core/deepresearch_metrics.py
# 功能: DeepResearch 质量指标工程化打分器
# 主要函数: score_deepresearch_sample, aggregate_scores
# 数据结构: DeepResearchScore（五维分数 + 通过标记）

"""
DeepResearch 指标工程化模块。

当前实现是首版可运行评分器，目标是把五项指标落到可自动回归的结构化输出：
- FactAccuracy
- CitationSupport
- CoverageCompleteness
- SourceQuality
- ToolEfficiency
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse


HIGH_QUALITY_DOMAINS = {
    "gov.cn",
    "edu.cn",
    "who.int",
    "oecd.org",
    "worldbank.org",
    "imf.org",
    "nature.com",
    "science.org",
    "ieee.org",
    "wikipedia.org",
}


@dataclass
class DeepResearchScore:
    fact_accuracy: float
    citation_support: float
    coverage_completeness: float
    source_quality: float
    tool_efficiency: float
    passed: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_citations(text: str) -> list[int]:
    refs = re.findall(r"\[(?:来源)?(\d+)\]", text or "")
    return [int(x) for x in refs if x.isdigit()]


def _split_claims(text: str) -> list[str]:
    parts = re.split(r"[。！？\n]+", text or "")
    claims = [p.strip() for p in parts if p.strip()]
    return claims


def _domain_quality(url: str) -> float:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return 0.2
    if any(host == d or host.endswith(f".{d}") for d in HIGH_QUALITY_DOMAINS):
        return 1.0
    if any(host.endswith(x) for x in (".gov", ".edu", ".org")):
        return 0.8
    if any(host.endswith(x) for x in (".com", ".cn")):
        return 0.6
    return 0.4


def score_deepresearch_sample(sample: dict[str, Any]) -> DeepResearchScore:
    """
    输入单条 DeepResearch 样本并产出五维评分。

    sample 建议字段：
    - report_text: 最终报告文本
    - sources: 来源 URL 列表
    - expected_aspects: 需要覆盖的方面列表
    - tools_used: 工具调用序列
    """
    report_text = sample.get("report_text", "") or ""
    sources = list(sample.get("sources", []) or [])
    aspects = [str(x).strip().lower() for x in sample.get("expected_aspects", []) if str(x).strip()]
    tools_used = [str(x).strip() for x in sample.get("tools_used", []) if str(x).strip()]

    reasons: list[str] = []

    claims = _split_claims(report_text)
    citations = _extract_citations(report_text)

    # FactAccuracy（首版近似）：报告有实质内容且包含可追溯引用时加分
    if not claims:
        fact_accuracy = 0.0
        reasons.append("报告为空或无法抽取论断")
    else:
        cited_claim_ratio = min(1.0, len(citations) / max(1, len(claims)))
        fact_accuracy = 0.6 + 0.4 * cited_claim_ratio

    # CitationSupport：引用编号覆盖来源范围的比例
    if not sources:
        citation_support = 0.0
        reasons.append("无来源列表")
    else:
        valid_citations = [c for c in citations if 1 <= c <= len(sources)]
        citation_support = min(1.0, len(valid_citations) / max(1, len(citations) or 1))
        if len(valid_citations) < len(citations):
            reasons.append("存在越界或无法映射的引用标记")

    # CoverageCompleteness：方面命中率
    if not aspects:
        coverage_completeness = 1.0
    else:
        report_lower = report_text.lower()
        hit = sum(1 for a in aspects if a in report_lower)
        coverage_completeness = hit / len(aspects)
        if hit < len(aspects):
            reasons.append(f"方面覆盖不足: {hit}/{len(aspects)}")

    # SourceQuality：来源域名质量均值
    if not sources:
        source_quality = 0.0
    else:
        source_quality = sum(_domain_quality(u) for u in sources) / len(sources)

    # ToolEfficiency：应调用 run_research，且不应出现显著绕路
    run_research_calls = sum(1 for t in tools_used if t == "run_research")
    if run_research_calls == 0:
        tool_efficiency = 0.0
        reasons.append("未调用 run_research")
    else:
        extra_calls = max(0, len(tools_used) - run_research_calls - 2)
        tool_efficiency = max(0.0, 1.0 - 0.1 * extra_calls)

    passed = (
        fact_accuracy >= 0.85
        and citation_support >= 0.90
        and coverage_completeness >= 0.85
        and source_quality >= 0.75
        and tool_efficiency >= 0.90
    )
    if not passed and not reasons:
        reasons.append("未达到阈值")

    return DeepResearchScore(
        fact_accuracy=round(fact_accuracy, 4),
        citation_support=round(citation_support, 4),
        coverage_completeness=round(coverage_completeness, 4),
        source_quality=round(source_quality, 4),
        tool_efficiency=round(tool_efficiency, 4),
        passed=passed,
        reasons=reasons,
    )


def aggregate_scores(scores: list[DeepResearchScore]) -> dict[str, Any]:
    if not scores:
        return {
            "count": 0,
            "pass_rate": 0.0,
            "fact_accuracy": 0.0,
            "citation_support": 0.0,
            "coverage_completeness": 0.0,
            "source_quality": 0.0,
            "tool_efficiency": 0.0,
        }

    count = len(scores)
    return {
        "count": count,
        "pass_rate": round(sum(1 for s in scores if s.passed) / count, 4),
        "fact_accuracy": round(sum(s.fact_accuracy for s in scores) / count, 4),
        "citation_support": round(sum(s.citation_support for s in scores) / count, 4),
        "coverage_completeness": round(sum(s.coverage_completeness for s in scores) / count, 4),
        "source_quality": round(sum(s.source_quality for s in scores) / count, 4),
        "tool_efficiency": round(sum(s.tool_efficiency for s in scores) / count, 4),
    }

