# backend/core/tools/eval_v2_executor.py
# 功能: Eval V2 专用执行器（当前实现体验形态的三步分块探索）
# 主要函数: run_experience_trial
# 数据结构:
#   - blocks: [{id, title, content}]
#   - result: {process, llm_calls, exploration_score, summary, error}

"""
Eval V2 执行器

说明：
1) 该模块聚焦新链路需要的执行逻辑，避免改动旧 eval_engine 主流程。
2) 当前优先实现 Experience 形态的“规划 -> 逐块 -> 总结”三步流程。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List
from dataclasses import dataclass
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage

from core.config import settings
from core.llm import get_chat_model


@dataclass
class ExperienceExecutionResult:
    process: list
    llm_calls: list
    exploration_score: float | None
    summary: dict
    error: str = ""


async def _call_json(system_prompt: str, user_prompt: str, step: str, temperature: float = 0.6) -> tuple[dict, dict]:
    start = time.time()
    model = get_chat_model(model=settings.openai_model, temperature=temperature)
    response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    duration_ms = int((time.time() - start) * 1000)
    usage = getattr(response, "usage_metadata", {}) or {}
    text = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _parse_json(text)
    call = {
        "step": step,
        "input": {"system_prompt": system_prompt, "user_message": user_prompt},
        "output": text,
        "tokens_in": usage.get("input_tokens", 0),
        "tokens_out": usage.get("output_tokens", 0),
        "cost": 0.0,
        "duration_ms": duration_ms,
        "timestamp": datetime.now().isoformat(),
    }
    return parsed, call


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {"raw_output": text, "parse_error": True}


def _normalize_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for b in blocks or []:
        bid = str(b.get("id", "") or "").strip()
        title = str(b.get("title", "") or "").strip()
        content = str(b.get("content", "") or "").strip()
        if not content:
            continue
        normalized.append({
            "id": bid or title or f"block_{len(normalized) + 1}",
            "title": title or f"内容块{len(normalized) + 1}",
            "content": content,
        })
    return normalized


async def run_experience_trial(
    *,
    persona_name: str,
    persona_prompt: str,
    probe: str,
    blocks: List[Dict[str, Any]],
) -> ExperienceExecutionResult:
    """
    Experience 三步流程：
    1. 探索规划
    2. 逐块探索（每块一次 LLM）
    3. 总结评价
    """
    normalized_blocks = _normalize_blocks(blocks)
    if not normalized_blocks:
        return ExperienceExecutionResult(process=[], llm_calls=[], exploration_score=None, summary={}, error="没有可探索的内容块")

    llm_calls: list = []
    process: list = []
    probe_section = f"【你的核心关切】\n{probe}" if probe else ""
    block_list = "\n".join([f"- {b['id']} | {b['title']}" for b in normalized_blocks])

    # Step 1: 规划
    plan_system = (
        "你是一位真实的消费者，请严格按 JSON 输出，不要输出额外文字。"
    )
    plan_user = f"""【你的身份】
{persona_prompt}

{probe_section}

你面前有以下内容块：
{block_list}

请严格输出 JSON（不允许 Markdown/解释）:
{{"plan":[{{"block_id":"id","block_title":"标题","reason":"为什么先看","expectation":"期望找到什么"}}],"overall_goal":"1句话目标"}}

强约束：
1) plan 必须包含 3-5 个步骤；若内容块少于3个，则全部列出且不得为空。
2) 每个步骤都必须引用有效 block_id（来自上方列表），不得杜撰。
3) 如果无法判断优先级，也必须给出默认顺序，不能省略步骤。"""
    plan_data, plan_call = await _call_json(plan_system, plan_user, "experience_plan", temperature=0.7)
    llm_calls.append(plan_call)
    process.append({"type": "plan", "stage": "阶段1-探索规划", "data": plan_data})

    block_map = {b["id"]: b for b in normalized_blocks}
    ordered_blocks = []
    for item in plan_data.get("plan", []) if isinstance(plan_data, dict) else []:
        bid = str((item or {}).get("block_id", "")).strip()
        if bid and bid in block_map and block_map[bid] not in ordered_blocks:
            ordered_blocks.append(block_map[bid])
    for b in normalized_blocks:
        if b not in ordered_blocks:
            ordered_blocks.append(b)

    # Step 2: 逐块探索
    per_block_results = []
    memory_lines: list[str] = []
    for idx, block in enumerate(ordered_blocks):
        memory_text = "；".join(memory_lines) if memory_lines else "（无）"
        per_system = "你是一位真实消费者，请按要求输出 JSON。"
        per_user = f"""【你的身份】
{persona_prompt}

{probe_section}

【之前的阅读记忆】
{memory_text}

【当前内容块】
标题：{block["title"]}
内容：
{block["content"]}

请严格输出 JSON（不允许 Markdown/解释）:
{{"concern_match":"...","discovery":"...","doubt":"...","missing":"...","feeling":"作为{persona_name}的感受","score":1-10}}

强约束：
1) score 必须是 1-10 的整数；不确定时给保守分并在 doubt 说明原因。
2) missing 必须是可执行的补充项（具体到信息/案例/步骤），禁止抽象空话。
3) discovery / doubt 需要基于当前内容块证据，不得脱离文本臆测。"""
        per_data, per_call = await _call_json(per_system, per_user, f"experience_per_block_{idx + 1}", temperature=0.7)
        llm_calls.append(per_call)
        per_block_results.append({
            "block_id": block["id"],
            "block_title": block["title"],
            "result": per_data,
        })
        process.append({
            "type": "per_block",
            "stage": "阶段2-逐块探索",
            "block_id": block["id"],
            "block_title": block["title"],
            "data": per_data,
        })
        score = per_data.get("score") if isinstance(per_data, dict) else None
        memory_lines.append(f"{block['title']}:{per_data.get('doubt', '无疑虑')}({score if isinstance(score, (int, float)) else '-' }分)")

    # Step 3: 总结
    all_block_results = json.dumps(per_block_results, ensure_ascii=False)
    summary_system = "你是一位真实消费者，请按 JSON 输出总结。"
    summary_user = f"""【你的身份】
{persona_prompt}

{probe_section}

以下是你逐块探索结果：
{all_block_results}

请严格输出 JSON（不允许 Markdown/解释）:
{{"overall_impression":"...","concerns_addressed":[],"concerns_unaddressed":[],"would_recommend":true,"summary":"作为{persona_name}的总体评价"}}

强约束：
1) concerns_addressed / concerns_unaddressed 的每一项，都必须能在逐块结果中找到依据。
2) summary 必须明确包含“是否推荐 + 推荐条件/不推荐原因”，不得只写笼统结论。
3) 如果信息不足，必须在 concerns_unaddressed 中明确指出缺口。"""
    summary_data, summary_call = await _call_json(summary_system, summary_user, "experience_summary", temperature=0.6)
    llm_calls.append(summary_call)
    process.append({"type": "summary", "stage": "阶段3-总体总结", "data": summary_data})

    scores = []
    for item in per_block_results:
        result = item.get("result", {}) or {}
        score = result.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    exploration_score = round(sum(scores) / len(scores), 2) if scores else None

    return ExperienceExecutionResult(
        process=process,
        llm_calls=llm_calls,
        exploration_score=exploration_score,
        summary=summary_data if isinstance(summary_data, dict) else {},
    )

