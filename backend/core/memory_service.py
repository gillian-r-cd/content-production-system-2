# backend/core/memory_service.py
# 功能: Memory 系统核心服务 — 提炼、去重、合并、筛选、注入记忆
# 主要函数:
#   extract_memories() — 从一轮对话中提炼 MemoryItem（异步，用 llm_mini）
#   save_memories() — 去重后存入 DB，过多时自动触发合并
#   consolidate_memories() — LLM 合并相似记忆（记忆 > CONSOLIDATE_THRESHOLD 时触发）
#   load_memory_context() — 加载项目记忆文本（> FILTER_THRESHOLD 时 LLM 预筛选）
# 数据结构:
#   MemoryItem: project_id, content, source_mode, source_phase, related_blocks
# 设计:
#   - 提炼用 llm_mini（低成本）
#   - 入库前做文本去重（简单包含关系判断）
#   - 记忆 > 50 条时自动合并相似条目（consolidate_memories）
#   - 记忆 > 100 条时注入前 LLM 预筛选 top-N（load_memory_context）
#   - 全量注入：load_memory_context 返回拼接文本，传入 AgentState.memory_context

"""
Memory Service

核心流程:
1. 对话结束 → extract_memories() 提炼关键信息
2. 去重后存入 memory_items 表
3. 下次对话前 → load_memory_context() 全量加载 → 注入 system prompt
"""

import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage
from core.llm_compat import normalize_content

logger = logging.getLogger("memory_service")

# ============== 阈值 ==============

CONSOLIDATE_THRESHOLD = 50   # 记忆超过此数时触发 LLM 合并
FILTER_THRESHOLD = 100       # 记忆超过此数时注入前 LLM 预筛选
FILTER_TOP_N = 30            # 预筛选保留的条数

# Token 预算（first-principles 版本）
MODEL_WINDOW_DEFAULT = 128_000
OUTPUT_RESERVE = 16_000
SAFETY_MARGIN = 2_000
SOFT_CAP_DEFAULT = 96_000


# ============== 提炼 Prompt ==============

EXTRACT_PROMPT = """以下是用户和 Agent 在「{mode}」模式中的最近一轮对话。
请提取值得长期记住的信息——任何可能影响未来内容生产决策的内容。
包括但不限于：用户表达的偏好、做出的选择、给出的反馈、明确的要求、重要的结论。
如果没有值得记住的新信息，返回空数组 []。

对话内容：
{conversation}

返回 JSON 数组，每项格式：
{{"content": "一句话描述", "related_blocks": ["相关内容块名，没有则为空数组"]}}

只输出 JSON，不要其他文字。"""


# ============== 记忆提炼 ==============

async def extract_memories(
    project_id: str,
    mode: str,
    phase: str,
    messages: list[dict],
) -> list[dict]:
    """
    从一轮对话中提炼 MemoryItem。

    Args:
        project_id: 项目 ID
        mode: 当前模式名（如 "assistant", "critic"）
        phase: 当前阶段（如 "intent", "content_core"）
        messages: 对话消息列表 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        提炼出的记忆列表 [{"content": "...", "related_blocks": [...]}]
        入库由调用方处理
    """
    # 过滤出 user/assistant 文本消息
    conversation_parts = []
    for m in messages:
        if m.get("role") in ("user", "assistant"):
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                # 单条消息截取 500 字（提炼不需要全文）
                conversation_parts.append(f'[{m["role"]}] {content[:500]}')

    if not conversation_parts:
        return []

    conversation = "\n\n".join(conversation_parts)
    prompt = EXTRACT_PROMPT.format(mode=mode, conversation=conversation)

    try:
        from core.llm import llm_mini
        response = await llm_mini.ainvoke([HumanMessage(content=prompt)])
        raw = normalize_content(response.content).strip()

        # 尝试提取 JSON（兼容 markdown code block 包裹）
        if raw.startswith("```"):
            # 去掉 ```json ... ```
            lines = raw.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(json_lines).strip()

        result = json.loads(raw)
        if not isinstance(result, list):
            return []

        # 校验每项格式
        valid = []
        for item in result:
            if isinstance(item, dict) and "content" in item:
                valid.append({
                    "content": str(item["content"]).strip(),
                    "related_blocks": item.get("related_blocks", []) or [],
                })
        return valid

    except json.JSONDecodeError as e:
        logger.warning("[memory] JSON 解析失败: %s, raw=%s", e, raw[:200] if raw else "")
        return []
    except Exception as e:
        logger.warning("[memory] extract_memories 失败: %s", e)
        return []


# ============== 记忆去重 ==============

def _is_duplicate(new_content: str, existing_contents: list[str]) -> bool:
    """
    简单去重：新记忆内容是否已被现有记忆覆盖。

    策略：
    1. 完全相同 → 重复
    2. 新内容是已有某条的子串 → 重复（已有的更完整）
    3. 已有某条是新内容的子串 → 不算重复（新的更完整，应更新）

    不用向量相似度 — 记忆量小（<300），简单文本匹配足够。
    """
    new_norm = new_content.strip().lower()
    for existing in existing_contents:
        existing_norm = existing.strip().lower()
        if new_norm == existing_norm:
            return True
        if new_norm in existing_norm:
            return True
    return False


# ============== 记忆存储 ==============

async def save_memories(
    project_id: str,
    mode: str,
    phase: str,
    extracted: list[dict],
) -> int:
    """
    将提炼出的记忆去重后存入 DB。

    Returns:
        实际新增的记忆条数
    """
    if not extracted:
        return 0

    from core.database import get_db
    from core.models.memory_item import MemoryItem

    db = next(get_db())
    try:
        # 加载已有记忆
        existing = db.query(MemoryItem).filter(
            MemoryItem.project_id == project_id,
        ).all()
        existing_contents = [m.content for m in existing]

        saved = 0
        for item in extracted:
            content = item.get("content", "").strip()
            if not content:
                continue
            if _is_duplicate(content, existing_contents):
                logger.debug("[memory] 跳过重复: %s", content[:60])
                continue

            mem = MemoryItem(
                project_id=project_id,
                content=content,
                source_mode=mode,
                source_phase=phase,
                related_blocks=item.get("related_blocks", []),
            )
            db.add(mem)
            existing_contents.append(content)  # 本批次内也要检查
            saved += 1

        if saved:
            db.commit()
            logger.info("[memory] 保存了 %d 条新记忆 (project=%s, mode=%s)", saved, project_id, mode)

            # 检查是否需要触发合并
            total = len(existing_contents) + saved
            if total > CONSOLIDATE_THRESHOLD:
                logger.info("[memory] 记忆达 %d 条，触发自动合并", total)
                try:
                    await consolidate_memories(project_id)
                except Exception as ce:
                    logger.warning("[memory] 自动合并失败（不影响保存）: %s", ce)

        return saved

    except Exception as e:
        db.rollback()
        logger.warning("[memory] save_memories 失败: %s", e)
        return 0
    finally:
        db.close()


# ============== 记忆加载（注入） ==============

def load_memory_context(
    project_id: str,
    mode: str = "assistant",
    phase: str = "",
) -> str:
    """
    从 DB 加载项目记忆，拼接为文本。

    策略:
    - 记忆 ≤ FILTER_THRESHOLD: 全量注入
    - 记忆 > FILTER_THRESHOLD: 异步 LLM 预筛选 top-N（回退：全量注入）

    返回格式（直接传入 AgentState.memory_context）:
        - 用户偏好口语化表达 (助手/意图分析)
        - 已选定方案B: 7模块结构 (策略顾问/内涵设计)
        ...

    如果无记忆返回空字符串。
    """
    from core.database import get_db
    from core.models.memory_item import MemoryItem

    db = next(get_db())
    try:
        from sqlalchemy import or_
        # 加载项目记忆 + 全局记忆（project_id IS NULL）
        memories = db.query(MemoryItem).filter(
            or_(
                MemoryItem.project_id == project_id,
                MemoryItem.project_id.is_(None),
            )
        ).order_by(MemoryItem.created_at).all()

        if not memories:
            return ""

        lines = []
        for m in memories:
            source = f"{m.source_mode}/{m.source_phase}" if m.source_phase else m.source_mode
            prefix = "[全局] " if m.project_id is None else ""
            lines.append(f"- {prefix}{m.content} ({source})")

        if len(memories) > FILTER_THRESHOLD:
            logger.info("[memory] 记忆 %d 条超阈值，建议使用 load_memory_context_async",
                        len(memories))

        return "\n".join(lines)

    except Exception as e:
        logger.warning("[memory] load_memory_context 失败: %s", e)
        return ""
    finally:
        db.close()


async def load_memory_context_async(
    project_id: str,
    mode: str = "assistant",
    phase: str = "",
    budget: Optional[dict] = None,
    query_ctx: str = "",
) -> str:
    """
    异步版 load_memory_context — 超过 FILTER_THRESHOLD 时调用 LLM 预筛选。
    同时加载项目记忆和全局记忆（project_id IS NULL）。

    调用方（api/agent.py stream_chat）应优先使用此函数。
    """
    from core.database import get_db
    from core.models.memory_item import MemoryItem

    db = next(get_db())
    try:
        from sqlalchemy import or_
        memories = db.query(MemoryItem).filter(
            or_(
                MemoryItem.project_id == project_id,
                MemoryItem.project_id.is_(None),
            )
        ).order_by(MemoryItem.created_at).all()

        if not memories:
            return ""

        # 构建 (index, text) 列表
        all_lines: list[tuple[int, str]] = []
        for i, m in enumerate(memories):
            source = f"{m.source_mode}/{m.source_phase}" if m.source_phase else m.source_mode
            prefix = "[全局] " if m.project_id is None else ""
            all_lines.append((i, f"{prefix}{m.content} ({source})"))

        zone = (budget or {}).get("zone", "A")
        memory_token_cap = (budget or {}).get("memory_token_cap", 12_000)

        if zone == "A":
            # 未超限不干预：保持完整上下文连续性
            selected_lines = all_lines
        elif zone == "B":
            # 轻量收敛：仅在条目很多时做 top-N 预筛选
            if len(memories) > FILTER_THRESHOLD:
                selected_indices = await filter_memories_by_relevance(all_lines, mode, phase)
                selected_lines = [all_lines[i] for i in selected_indices if i < len(all_lines)]
            else:
                selected_lines = all_lines
        else:
            # Zone C/D: token 预算驱动选择（utility/token 最大化）
            selected_lines = select_memory_under_budget(
                memories=all_lines,
                budget_tokens=memory_token_cap,
                query_ctx=query_ctx,
            )

        logger.info(
            "[memory] budget zone=%s, selected=%d/%d",
            zone,
            len(selected_lines),
            len(all_lines),
        )

        return "\n".join(f"- {text}" for _, text in selected_lines)

    except Exception as e:
        logger.warning("[memory] load_memory_context_async 失败: %s", e)
        return ""
    finally:
        db.close()


def compute_context_budget(model_name: str = "") -> dict:
    """
    计算上下文预算与触发区间阈值。
    当前默认按 128k 窗口模型配置；保留参数用于后续按模型映射扩展。
    """
    _ = model_name
    model_window = MODEL_WINDOW_DEFAULT
    soft_cap = SOFT_CAP_DEFAULT
    return {
        "model_window": model_window,
        "output_reserve": OUTPUT_RESERVE,
        "safety_margin": SAFETY_MARGIN,
        "soft_cap": soft_cap,
        "zone_a": int(0.7 * soft_cap),
        "zone_b": int(0.9 * soft_cap),
        "zone_c": soft_cap,
    }


def _count_tokens(text: str) -> int:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text or "", disallowed_special=()))


def _memory_utility_score(text: str, query_ctx: str, recency_rank: int, total: int) -> float:
    query_tokens = set((query_ctx or "").lower().split())
    text_tokens = set((text or "").lower().split())
    overlap = len(query_tokens.intersection(text_tokens))
    relevance = min(1.0, overlap / max(1, len(query_tokens))) if query_tokens else 0.2
    recency = 1.0 - (recency_rank / max(1, total))
    constraint_strength = 1.0 if any(k in text for k in ["必须", "禁止", "不要", "约束", "偏好"]) else 0.2
    cross_mode_value = 0.8 if "[全局]" in text or "(consolidated" in text else 0.3
    return relevance + recency + constraint_strength + cross_mode_value


def select_memory_under_budget(
    memories: list[tuple[int, str]],
    budget_tokens: int,
    query_ctx: str = "",
) -> list[tuple[int, str]]:
    """
    在 token 约束下最大化 memory utility。
    采用贪心近似：按 utility/token 排序选择。
    """
    if not memories:
        return []
    scored = []
    total = len(memories)
    for rank, (idx, text) in enumerate(memories):
        token_cost = max(1, _count_tokens(text))
        utility = _memory_utility_score(text, query_ctx=query_ctx, recency_rank=rank, total=total)
        scored.append((utility / token_cost, idx, text, token_cost))
    scored.sort(key=lambda x: x[0], reverse=True)

    selected: list[tuple[int, str]] = []
    used = 0
    for _, idx, text, token_cost in scored:
        if used + token_cost > budget_tokens:
            continue
        selected.append((idx, text))
        used += token_cost
    selected.sort(key=lambda x: x[0])
    return selected


# ============== 记忆合并（M3-3） ==============

CONSOLIDATE_PROMPT = """以下是一个项目中积累的 {count} 条记忆。
请合并相似、重复或可归纳的条目，保留最有价值的信息。

规则：
- 完全重复的条目合为一条
- 同一主题的多条记忆归纳为一条更完整的描述
- 已被后续条目更新/推翻的旧信息可以删除
- 保留所有独特的偏好、决策、反馈
- 每条记忆应是独立的一句话描述

当前记忆列表：
{memories}

返回合并后的 JSON 数组，每项格式：
{{"content": "合并后的描述", "related_blocks": ["相关内容块名"]}}

只输出 JSON，不要其他文字。"""


async def consolidate_memories(project_id: str) -> int:
    """
    LLM 合并相似记忆，减少冗余。

    在 save_memories 后自动触发（当记忆数 > CONSOLIDATE_THRESHOLD）。
    用 LLM 将全部记忆重新整理为更精简的列表，然后清空旧记忆、写入新列表。

    Returns:
        合并后的记忆条数（0 表示未执行或失败）
    """
    from core.database import get_db
    from core.models.memory_item import MemoryItem

    db = next(get_db())
    try:
        old_memories = db.query(MemoryItem).filter(
            MemoryItem.project_id == project_id,
        ).order_by(MemoryItem.created_at).all()

        count = len(old_memories)
        if count <= CONSOLIDATE_THRESHOLD:
            return 0  # 未达阈值，不执行

        # 构建记忆列表文本
        mem_lines = []
        for i, m in enumerate(old_memories, 1):
            blocks_str = ", ".join(m.related_blocks) if m.related_blocks else ""
            source = f"{m.source_mode}/{m.source_phase}" if m.source_phase else m.source_mode
            mem_lines.append(f"{i}. {m.content} [{source}] {f'({blocks_str})' if blocks_str else ''}")

        prompt = CONSOLIDATE_PROMPT.format(
            count=count,
            memories="\n".join(mem_lines),
        )

        from core.llm import llm_mini
        response = await llm_mini.ainvoke([HumanMessage(content=prompt)])
        raw = normalize_content(response.content).strip()

        # 解析 JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(json_lines).strip()

        result = json.loads(raw)
        if not isinstance(result, list) or len(result) == 0:
            logger.warning("[memory] consolidate 返回无效结果，跳过")
            return 0

        # 校验：合并后不应比原来更多
        if len(result) >= count:
            logger.info("[memory] consolidate 未减少条目（%d→%d），跳过", count, len(result))
            return 0

        # 删除旧记忆，写入合并后的新记忆
        for old in old_memories:
            db.delete(old)
        db.flush()

        new_count = 0
        for item in result:
            if isinstance(item, dict) and item.get("content", "").strip():
                mem = MemoryItem(
                    project_id=project_id,
                    content=str(item["content"]).strip(),
                    source_mode="consolidated",
                    source_phase="",
                    related_blocks=item.get("related_blocks", []) or [],
                )
                db.add(mem)
                new_count += 1

        db.commit()
        logger.info("[memory] 合并完成: %d → %d 条 (project=%s)", count, new_count, project_id)
        return new_count

    except json.JSONDecodeError as e:
        db.rollback()
        logger.warning("[memory] consolidate JSON 解析失败: %s", e)
        return 0
    except Exception as e:
        db.rollback()
        logger.warning("[memory] consolidate_memories 失败: %s", e)
        return 0
    finally:
        db.close()


# ============== 记忆预筛选（M3-4） ==============

FILTER_PROMPT = """以下是一个项目的 {count} 条记忆。
当前 Agent 模式是「{mode}」，当前阶段是「{phase}」。

请从中选出对当前模式和阶段最有用的 {top_n} 条记忆。
优先选择：
1. 明确的用户偏好和要求
2. 与当前阶段直接相关的决策
3. 通用的创作约束和反馈

记忆列表：
{memories}

返回选中的记忆编号数组，如 [1, 3, 5, 7, ...]（编号从1开始）。
只输出 JSON 数组，不要其他文字。"""


async def filter_memories_by_relevance(
    memories_text_lines: list[tuple[int, str]],
    mode: str,
    phase: str,
) -> list[int]:
    """
    LLM 预筛选：从大量记忆中选出与当前模式/阶段最相关的 top-N。

    Args:
        memories_text_lines: [(index, "memory text"), ...] 全部记忆
        mode: 当前模式名
        phase: 当前阶段名

    Returns:
        选中的记忆索引列表（0-based）
    """
    count = len(memories_text_lines)
    if count <= FILTER_THRESHOLD:
        return list(range(count))  # 不超阈值，全部返回

    # 构建记忆列表
    mem_lines = []
    for idx, (_, text) in enumerate(memories_text_lines, 1):
        mem_lines.append(f"{idx}. {text}")

    prompt = FILTER_PROMPT.format(
        count=count,
        mode=mode,
        phase=phase or "未指定",
        top_n=FILTER_TOP_N,
        memories="\n".join(mem_lines),
    )

    try:
        from core.llm import llm_mini
        response = await llm_mini.ainvoke([HumanMessage(content=prompt)])
        raw = normalize_content(response.content).strip()

        if raw.startswith("```"):
            lines = raw.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(json_lines).strip()

        result = json.loads(raw)
        if not isinstance(result, list):
            return list(range(count))

        # 转为 0-based 索引并校验范围
        selected = []
        for num in result:
            if isinstance(num, int) and 1 <= num <= count:
                selected.append(num - 1)

        if not selected:
            return list(range(count))

        return selected

    except Exception as e:
        logger.warning("[memory] filter_memories 失败，回退全量: %s", e)
        return list(range(count))

