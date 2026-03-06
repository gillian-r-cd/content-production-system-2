# backend/core/project_split_service.py
# 功能: 项目级自动拆分服务，负责按份数/按字数/按规则生成初始 chunk 列表
# 主要函数: split_source_text
# 数据结构: 返回可直接写入 ProjectStructureDraft.draft_payload["chunks"] 的标准 chunk dict

"""
项目级拆分服务

职责边界：
- 只负责“初始拆分”
- 不负责后续人工修订、编排、应用
- 规则模式可借助 LLM 做语义拆分，但输出仍统一收敛为标题 + 正文 + 顺序
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import ainvoke_with_retry, get_chat_model
from core.models import generate_uuid


DEFAULT_TITLE_PREFIX = "内容片段"


def _normalize_split_config(split_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(split_config or {})
    mode = str(config.get("mode") or "count").strip().lower()
    if mode in {"parts", "count"}:
        mode = "count"
    elif mode in {"chars", "length", "size"}:
        mode = "chars"
    elif mode in {"rule", "rules"}:
        mode = "rule"
    else:
        raise ValueError(f"不支持的拆分模式: {mode}")

    target_count = max(int(config.get("target_count") or 3), 1)
    max_chars_per_chunk = max(int(config.get("max_chars_per_chunk") or 1200), 1)
    overlap_chars = max(int(config.get("overlap_chars") or 0), 0)
    title_prefix = str(config.get("title_prefix") or "").strip()
    rule_prompt = str(config.get("rule_prompt") or "").strip()
    return {
        "mode": mode,
        "target_count": target_count,
        "max_chars_per_chunk": max_chars_per_chunk,
        "overlap_chars": overlap_chars,
        "title_prefix": title_prefix or DEFAULT_TITLE_PREFIX,
        "rule_prompt": rule_prompt,
    }


def _clean_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _make_title(prefix: str, index: int) -> str:
    return f"{prefix} {index + 1:02d}"


def _snap_boundary(text: str, index: int, *, forward: bool) -> int:
    if index <= 0:
        return 0
    if index >= len(text):
        return len(text)
    window = 80
    if forward:
        search = text[index:min(len(text), index + window)]
        for pattern in ("\n\n", "\n", "。", "！", "？", ".", "!", "?"):
            pos = search.find(pattern)
            if pos >= 0:
                return min(len(text), index + pos + len(pattern))
        return index
    search = text[max(0, index - window):index]
    for pattern in ("\n\n", "\n", "。", "！", "？", ".", "!", "?"):
        pos = search.rfind(pattern)
        if pos >= 0:
            return max(0, index - (len(search) - pos - len(pattern)))
    return index


def _split_by_count(text: str, target_count: int, overlap_chars: int) -> list[str]:
    if target_count <= 1 or len(text) <= 1:
        return [text]

    chunks: list[str] = []
    total_length = len(text)
    for index in range(target_count):
        raw_start = math.floor(total_length * index / target_count)
        raw_end = math.floor(total_length * (index + 1) / target_count)
        start = max(0, raw_start - overlap_chars if index > 0 else raw_start)
        end = min(total_length, raw_end + overlap_chars if index < target_count - 1 else raw_end)
        start = _snap_boundary(text, start, forward=False)
        end = _snap_boundary(text, end, forward=True)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [text]


def _split_by_chars(text: str, max_chars_per_chunk: int, overlap_chars: int) -> list[str]:
    paragraphs = [
        part.strip()
        for part in re.split(r"\n{2,}", text)
        if part and part.strip()
    ]
    if len(paragraphs) > 1:
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if current and len(candidate) > max_chars_per_chunk:
                chunks.append(current)
                if overlap_chars > 0:
                    overlap = current[-overlap_chars:].strip()
                    current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
                else:
                    current = paragraph
            else:
                current = candidate
        if current:
            chunks.append(current)
        if chunks:
            return chunks

    chunks: list[str] = []
    cursor = 0
    total_length = len(text)
    while cursor < total_length:
        tentative_end = min(total_length, cursor + max_chars_per_chunk)
        end = _snap_boundary(text, tentative_end, forward=False)
        if end <= cursor:
            end = _snap_boundary(text, tentative_end, forward=True)
        if end <= cursor:
            end = tentative_end
        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= total_length:
            break
        cursor = max(end - overlap_chars, cursor + 1)
        cursor = _snap_boundary(text, cursor, forward=False)
    return chunks or [text]


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    fenced = re.search(r"```json\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("规则拆分返回中未找到 JSON 数组")
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, list):
        raise ValueError("规则拆分返回不是 JSON 数组")
    return [item for item in parsed if isinstance(item, dict)]


async def _split_by_rule_with_llm(text: str, config: dict[str, Any]) -> list[str]:
    rule_prompt = config["rule_prompt"]
    if not rule_prompt:
        raise ValueError("规则模式必须提供拆分规则")

    chat_model = get_chat_model(temperature=0.2, streaming=False)
    response = await ainvoke_with_retry(chat_model, [
        SystemMessage(content=(
            "你是内容拆分助手。"
            "请根据用户给定的拆分规则，把原文拆成若干段。"
            "只返回 JSON 数组，每一项包含 title 和 content 两个字段。"
            "不要输出解释，不要输出 Markdown 之外的额外文本。"
        )),
        HumanMessage(content=(
            f"# 拆分规则\n{rule_prompt}\n\n"
            f"# 原文\n{text}\n\n"
            "请输出 JSON 数组，例如："
            '[{"title":"片段 01","content":"..."},{"title":"片段 02","content":"..."}]'
        )),
    ])
    items = _extract_json_array(getattr(response, "content", "") or "")
    chunks: list[str] = []
    for item in items:
        content = _clean_text(str(item.get("content") or ""))
        if content:
            chunks.append(content)
    if not chunks:
        raise ValueError("规则拆分未生成有效内容")
    return chunks


async def split_source_text(source_text: str, split_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    text = _clean_text(source_text)
    if not text:
        raise ValueError("原文不能为空")

    config = _normalize_split_config(split_config)
    if config["mode"] == "count":
        raw_chunks = _split_by_count(text, config["target_count"], config["overlap_chars"])
    elif config["mode"] == "chars":
        raw_chunks = _split_by_chars(text, config["max_chars_per_chunk"], config["overlap_chars"])
    else:
        raw_chunks = await _split_by_rule_with_llm(text, config)

    chunks: list[dict[str, Any]] = []
    for index, chunk_text in enumerate(raw_chunks):
        cleaned_chunk = _clean_text(chunk_text)
        if not cleaned_chunk:
            continue
        chunks.append({
            "chunk_id": generate_uuid(),
            "title": _make_title(config["title_prefix"], index),
            "content": cleaned_chunk,
            "order_index": index,
        })

    if not chunks:
        raise ValueError("拆分后没有可用内容")
    return chunks
