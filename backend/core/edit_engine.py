# backend/core/edit_engine.py
"""
编辑引擎 - 将 LLM 输出的 edits 确定性地应用到原始内容上
主要函数: apply_edits(), generate_revision_markdown()
辅助函数: _find_anchor() — 三级 fallback 锚点定位（exact → normalized → fuzzy）
"""
import difflib
import logging
from typing import Optional

logger = logging.getLogger("edit_engine")

# ============== 锚点定位（三级 fallback） ==============

# 中英文标点映射（归一化用）
_PUNCT_MAP = str.maketrans({
    "\u3001": ",",   # 、 → ,
    "\u3002": ".",   # 。 → .
    "\uff0c": ",",   # ， → ,
    "\uff1a": ":",   # ： → :
    "\uff1b": ";",   # ； → ;
    "\uff01": "!",   # ！ → !
    "\uff1f": "?",   # ？ → ?
    "\u201c": '"',   # " → "
    "\u201d": '"',   # " → "
    "\u2018": "'",   # ' → '
    "\u2019": "'",   # ' → '
    "\uff08": "(",   # （ → (
    "\uff09": ")",   # ） → )
})


def _normalize(text: str) -> tuple[str, list[int]]:
    """归一化文本并建立字符级位置映射。

    归一化规则:
    - 折叠连续空白为单个空格
    - 中文标点统一为英文标点

    返回:
        (normalized_text, positions)
        positions[i] = 归一化文本第 i 个字符在原文中的起始位置
    """
    normalized = []
    positions = []
    prev_is_space = False

    for i, ch in enumerate(text):
        # 标点归一化
        ch = ch.translate(_PUNCT_MAP)

        # 空白折叠
        if ch in (" ", "\t", "\n", "\r", "\u3000"):
            if not prev_is_space:
                normalized.append(" ")
                positions.append(i)
                prev_is_space = True
            continue
        prev_is_space = False
        normalized.append(ch)
        positions.append(i)

    return "".join(normalized), positions


def _find_anchor(
    original: str, anchor: str,
) -> tuple[int, int, str]:
    """三级 fallback 锚点定位。

    返回:
        (start, end, match_method)
        start/end 是在 **original** 中的字符偏移。
        match_method: "exact" | "normalized" | "fuzzy"
        找不到时返回 (-1, -1, "none")
    """
    if not anchor:
        return -1, -1, "none"

    # ---- Level 1: 精确匹配 ----
    pos = original.find(anchor)
    if pos >= 0:
        return pos, pos + len(anchor), "exact"

    # ---- Level 2: 归一化匹配 ----
    norm_orig, orig_positions = _normalize(original)
    norm_anchor, _ = _normalize(anchor)

    if norm_anchor:
        norm_pos = norm_orig.find(norm_anchor)
        if norm_pos >= 0:
            # 映射回原文坐标
            start_orig = orig_positions[norm_pos]
            norm_end = norm_pos + len(norm_anchor)
            if norm_end < len(orig_positions):
                end_orig = orig_positions[norm_end]
            else:
                end_orig = len(original)

            logger.info(
                "[edit_engine] 归一化匹配成功: anchor='%s' → orig[%d:%d]",
                anchor[:50], start_orig, end_orig,
            )
            return start_orig, end_orig, "normalized"

    # ---- Level 3: 模糊匹配（滑窗 + SequenceMatcher） ----
    # 只对合理长度的 anchor 启用（过长的 anchor 模糊匹配意义不大且性能差）
    if len(anchor) > 500 or len(original) > 50000:
        return -1, -1, "none"

    best_ratio = 0.85  # 最低阈值
    best_start = -1
    best_end = -1
    anchor_len = len(anchor)

    # 搜索窗口: anchor 长度的 80%~120%
    min_window = max(1, int(anchor_len * 0.8))
    max_window = min(len(original), int(anchor_len * 1.2))

    # 优化: 先用归一化文本做粗筛，再映射回原文
    norm_anchor_for_fuzzy = norm_anchor if norm_anchor else anchor

    for window_size in range(min_window, max_window + 1):
        for start in range(len(norm_orig) - window_size + 1):
            candidate = norm_orig[start:start + window_size]
            # 快速预筛: 长度比差太大就跳过
            ratio = difflib.SequenceMatcher(
                None, norm_anchor_for_fuzzy, candidate,
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                # 映射回原文坐标
                best_start = orig_positions[start]
                norm_end_idx = start + window_size
                if norm_end_idx < len(orig_positions):
                    best_end = orig_positions[norm_end_idx]
                else:
                    best_end = len(original)

    if best_start >= 0:
        matched_text = original[best_start:best_end]
        logger.warning(
            "[edit_engine] 模糊匹配: anchor='%s' → ratio=%.3f, matched='%s'",
            anchor[:50], best_ratio, matched_text[:50],
        )
        return best_start, best_end, "fuzzy"

    return -1, -1, "none"


# ============== 核心编辑函数 ==============

def apply_edits(
    original: str,
    edits: list,
    accepted_ids: Optional[set] = None,
) -> tuple:
    """
    将编辑操作应用到原始内容。

    锚点定位使用三级 fallback:
    1. 精确 str.find()
    2. 归一化匹配（空白折叠 + 标点统一）
    3. 模糊匹配（difflib.SequenceMatcher, 阈值 0.85）

    输入:
        original  - 原始内容字符串
        edits     - 编辑操作列表，每个元素:
                     {"type": "replace"|"insert_after"|"insert_before"|"delete",
                      "anchor": str,   # 原文精确引用
                      "new_text": str}  # 替换/插入内容（delete 时为 ""）
        accepted_ids - 如果提供，只应用这些 ID 的 edits（部分接受）
                       None 表示应用所有

    输出:
        (modified_content, changes)
        changes 列表每个元素:
            {**edit, "id": str, "old_text": str|None,
             "status": "applied"|"failed"|"rejected",
             "reason": str|None,
             "match_method": "exact"|"normalized"|"fuzzy"|None,
             "position": {"start": int, "end": int}}
    """
    result = original
    changes = []

    # 1. 分配 ID
    for i, edit in enumerate(edits):
        if "id" not in edit:
            edit["id"] = f"e{i}"

    # 2. 定位并排序（从后往前，避免偏移）
    positioned_edits = []
    for edit in edits:
        anchor = edit.get("anchor", "")
        start, end, match_method = _find_anchor(original, anchor)
        positioned_edits.append((start, end, match_method, edit))
    positioned_edits.sort(key=lambda x: x[0], reverse=True)

    # 3. 逐个处理
    for pos, end_pos, match_method, edit in positioned_edits:
        edit_id = edit["id"]
        anchor = edit.get("anchor", "")
        new_text = edit.get("new_text", "")
        edit_type = edit.get("type", "replace")
        # 实际匹配到的原文片段（可能与 anchor 有细微差异）
        matched_text = original[pos:end_pos] if pos >= 0 else anchor
        matched_len = end_pos - pos if pos >= 0 else len(anchor)

        # 3a. 部分接受检查
        if accepted_ids is not None and edit_id not in accepted_ids:
            changes.append({
                **edit,
                "status": "rejected",
                "reason": None,
                "match_method": match_method if match_method != "none" else None,
                "position": {"start": pos, "end": end_pos if pos >= 0 else -1},
            })
            continue

        # 3b. anchor 找不到（三级 fallback 均失败）
        if pos == -1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_found",
                "match_method": None,
                "position": {"start": -1, "end": -1},
            })
            continue

        # 3c. anchor 不唯一（仅对精确匹配检查；归一化/模糊匹配已定位到最佳位置）
        if match_method == "exact" and result.count(anchor) > 1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_unique",
                "match_method": "exact",
                "position": {"start": pos, "end": end_pos},
            })
            continue

        # 3d. 执行编辑（使用实际匹配位置，而非 anchor 字面量）
        if edit_type == "replace":
            result = result[:pos] + new_text + result[pos + matched_len:]
            changes.append({
                **edit, "old_text": matched_text,
                "status": "applied", "reason": None,
                "match_method": match_method,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "insert_after":
            insert_pos = pos + matched_len
            result = result[:insert_pos] + "\n" + new_text + result[insert_pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "match_method": match_method,
                "position": {"start": insert_pos + 1, "end": insert_pos + 1 + len(new_text)},
            })
        elif edit_type == "insert_before":
            result = result[:pos] + new_text + "\n" + result[pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "match_method": match_method,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "delete":
            result = result[:pos] + result[pos + matched_len:]
            changes.append({
                **edit, "old_text": matched_text,
                "status": "applied", "reason": None,
                "match_method": match_method,
                "position": {"start": pos, "end": pos},
            })

    return result, changes


def generate_revision_markdown(old: str, new: str) -> str:
    """
    生成带修订标记的 markdown。删除用 <del>，新增用 <ins>。

    输入: old - 修改前文本, new - 修改后文本
    输出: 带 <del>/<ins> 标签的字符串
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(old_lines[i1:i2])
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                result.append(f"<del>{line.rstrip()}</del>\n")
            for line in new_lines[j1:j2]:
                result.append(f"<ins>{line.rstrip()}</ins>\n")
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                result.append(f"<del>{line.rstrip()}</del>\n")
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                result.append(f"<ins>{line.rstrip()}</ins>\n")
    return "".join(result)
