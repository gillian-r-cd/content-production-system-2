# backend/tests/test_deepresearch_metrics.py
# 功能: DeepResearch 指标工程化评分器测试
# 主要函数: test_score_deepresearch_sample_pass_case, test_score_deepresearch_sample_fail_without_research_tool
# 数据结构: sample(dict) -> DeepResearchScore

from core.deepresearch_metrics import score_deepresearch_sample, aggregate_scores


def test_score_deepresearch_sample_pass_case():
    sample = {
        "request": "调研 2026 年以来发展趋势",
        "report_text": "2026 年以来市场规模扩大 [1]。用户更关注效率 [2]。",
        "sources": ["https://www.oecd.org/x", "https://www.worldbank.org/y"],
        "expected_aspects": ["2026", "市场规模", "效率"],
        "tools_used": ["run_research"],
    }
    score = score_deepresearch_sample(sample)
    assert score.fact_accuracy >= 0.85
    assert score.citation_support >= 0.90
    assert score.coverage_completeness >= 0.85
    assert score.source_quality >= 0.75
    assert score.tool_efficiency >= 0.90


def test_score_deepresearch_sample_fail_without_research_tool():
    sample = {
        "request": "调研某主题",
        "report_text": "这里有一些结论。",
        "sources": ["https://example.com/a"],
        "expected_aspects": ["主题"],
        "tools_used": ["query_field", "read_field"],
    }
    score = score_deepresearch_sample(sample)
    assert score.tool_efficiency == 0.0
    assert score.passed is False

    summary = aggregate_scores([score])
    assert summary["count"] == 1
    assert summary["pass_rate"] == 0.0

