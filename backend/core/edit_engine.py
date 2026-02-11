# backend/core/edit_engine.py
"""
编辑引擎 - 将 LLM 输出的 edits 确定性地应用到原始内容上
主要函数: apply_edits(), generate_revision_markdown()
"""
import difflib
from typing import Optional


def apply_edits(
    original: str,
    edits: list,
    accepted_ids: Optional[set] = None,
) -> tuple:
    """
    将编辑操作应用到原始内容。

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
        pos = original.find(anchor)
        positioned_edits.append((pos, edit))
    positioned_edits.sort(key=lambda x: x[0], reverse=True)

    # 3. 逐个处理
    for pos, edit in positioned_edits:
        edit_id = edit["id"]
        anchor = edit.get("anchor", "")
        new_text = edit.get("new_text", "")
        edit_type = edit.get("type", "replace")

        # 3a. 部分接受检查
        if accepted_ids is not None and edit_id not in accepted_ids:
            changes.append({
                **edit,
                "status": "rejected",
                "reason": None,
                "position": {"start": pos, "end": pos + len(anchor) if pos >= 0 else -1},
            })
            continue

        # 3b. anchor 找不到
        if pos == -1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_found",
                "position": {"start": -1, "end": -1},
            })
            continue

        # 3c. anchor 不唯一
        if result.count(anchor) > 1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_unique",
                "position": {"start": pos, "end": pos + len(anchor)},
            })
            continue

        # 3d. 执行编辑
        if edit_type == "replace":
            result = result[:pos] + new_text + result[pos + len(anchor):]
            changes.append({
                **edit, "old_text": anchor,
                "status": "applied", "reason": None,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "insert_after":
            insert_pos = pos + len(anchor)
            result = result[:insert_pos] + "\n" + new_text + result[insert_pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "position": {"start": insert_pos + 1, "end": insert_pos + 1 + len(new_text)},
            })
        elif edit_type == "insert_before":
            result = result[:pos] + new_text + "\n" + result[pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "delete":
            result = result[:pos] + result[pos + len(anchor):]
            changes.append({
                **edit, "old_text": anchor,
                "status": "applied", "reason": None,
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
