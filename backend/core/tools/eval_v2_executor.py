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
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.llm import get_chat_model
from core.llm_compat import normalize_content
from core.locale_text import rt


@dataclass
class ExperienceExecutionResult:
    process: list
    llm_calls: list
    exploration_score: float | None
    summary: dict
    error: str = ""


async def _call_json(system_prompt: str, user_prompt: str, step: str, temperature: float = 0.6) -> tuple[dict, dict]:
    start = time.time()
    model = get_chat_model(temperature=temperature)  # 自动选择 provider 对应的默认模型
    response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    duration_ms = int((time.time() - start) * 1000)
    usage = getattr(response, "usage_metadata", {}) or {}
    text = normalize_content(response.content)
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


def _normalize_blocks(blocks: List[Dict[str, Any]], locale: str) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for b in blocks or []:
        bid = str(b.get("id", "") or "").strip()
        title = str(b.get("title", "") or "").strip()
        content = str(b.get("content", "") or "").strip()
        if not content:
            continue
        normalized.append({
            "id": bid or title or f"block_{len(normalized) + 1}",
            "title": title or rt(locale, "eval.experience.block_fallback_title", index=len(normalized) + 1),
            "content": content,
        })
    return normalized


async def run_experience_trial(
    *,
    persona_name: str,
    persona_prompt: str,
    probe: str,
    blocks: List[Dict[str, Any]],
    locale: str = DEFAULT_LOCALE,
) -> ExperienceExecutionResult:
    """
    Experience 三步流程：
    1. 探索规划
    2. 逐块探索（每块一次 LLM）
    3. 总结评价
    """
    locale = normalize_locale(locale)
    normalized_blocks = _normalize_blocks(blocks, locale)
    if not normalized_blocks:
        return ExperienceExecutionResult(
            process=[],
            llm_calls=[],
            exploration_score=None,
            summary={},
            error=rt(locale, "eval.experience.no_blocks"),
        )

    llm_calls: list = []
    process: list = []
    probe_section = rt(locale, "eval.experience.probe_section", probe=probe) if probe else ""
    block_list = "\n".join([f"- {b['id']} | {b['title']}" for b in normalized_blocks])

    # Step 1: 规划
    plan_system = rt(locale, "eval.experience.plan.system")
    plan_user = rt(
        locale,
        "eval.experience.plan.user",
        persona_prompt=persona_prompt,
        probe_section=probe_section,
        block_list=block_list,
    )
    plan_data, plan_call = await _call_json(plan_system, plan_user, "experience_plan", temperature=0.7)
    llm_calls.append(plan_call)
    process.append({"type": "plan", "stage": rt(locale, "eval.experience.stage_plan"), "data": plan_data})

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
        memory_text = "；".join(memory_lines) if memory_lines else rt(locale, "eval.experience.memory_none")
        per_system = rt(locale, "eval.experience.per_block.system")
        per_user = rt(
            locale,
            "eval.experience.per_block.user",
            persona_prompt=persona_prompt,
            probe_section=probe_section,
            exploration_memory=memory_text,
            block_title=block["title"],
            block_content=block["content"],
            persona_name=persona_name,
        )
        per_data, per_call = await _call_json(per_system, per_user, f"experience_per_block_{idx + 1}", temperature=0.7)
        llm_calls.append(per_call)
        per_block_results.append({
            "block_id": block["id"],
            "block_title": block["title"],
            "result": per_data,
        })
        process.append({
            "type": "per_block",
            "stage": rt(locale, "eval.experience.stage_per_block"),
            "block_id": block["id"],
            "block_title": block["title"],
            "data": per_data,
        })
        score = per_data.get("score") if isinstance(per_data, dict) else None
        memory_lines.append(
            rt(
                locale,
                "eval.experience.memory_line",
                block_title=block["title"],
                doubt=per_data.get("doubt", rt(locale, "eval.experience.no_doubt")),
                score=score if isinstance(score, (int, float)) else "-",
            )
        )

    # Step 3: 总结
    all_block_results = json.dumps(per_block_results, ensure_ascii=False)
    summary_system = rt(locale, "eval.experience.summary.system")
    summary_user = rt(
        locale,
        "eval.experience.summary.user",
        persona_prompt=persona_prompt,
        probe_section=probe_section,
        all_block_results=all_block_results,
        persona_name=persona_name,
    )
    summary_data, summary_call = await _call_json(summary_system, summary_user, "experience_summary", temperature=0.6)
    llm_calls.append(summary_call)
    process.append({"type": "summary", "stage": rt(locale, "eval.experience.stage_summary"), "data": summary_data})

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

