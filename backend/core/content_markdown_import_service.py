# 功能: 将多个 Markdown 文件按 heading_tree / raw_file 规则追加导入为 ContentBlock
# 主要函数: import_markdown_files
# 数据结构: MarkdownImportNode / MarkdownHeadingNode / MarkdownImportSummary

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from core.locale_text import rt
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.models import ContentBlock, Project, generate_uuid

ImportMode = Literal["heading_tree", "raw_file"]
_ATX_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$")
_SETEXT_HEADING_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


@dataclass
class MarkdownHeadingNode:
    title: str
    level: int
    content_lines: list[str] = field(default_factory=list)
    children: list["MarkdownHeadingNode"] = field(default_factory=list)


@dataclass
class MarkdownImportNode:
    name: str
    block_type: str
    content: str
    children: list["MarkdownImportNode"] = field(default_factory=list)


def _file_label(file_data: dict[str, Any], index: int) -> str:
    path = str(file_data.get("path") or "").strip()
    name = str(file_data.get("name") or "").strip()
    return path or name or f"file[{index + 1}]"


def _file_root_name(file_data: dict[str, Any], *, locale: str, index: int) -> str:
    label = _file_label(file_data, index)
    normalized = label.replace("\\", "/")
    basename = PurePosixPath(normalized).name or label
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    return stem.strip() or rt(locale, "project.markdown_import.default_file_name")


def _normalize_markdown_content(lines: list[str]) -> str:
    return "\n".join(lines).strip("\n")


def _push_heading_node(
    roots: list[MarkdownHeadingNode],
    stack: list[MarkdownHeadingNode],
    *,
    title: str,
    level: int,
) -> None:
    node = MarkdownHeadingNode(title=title, level=level)
    while stack and stack[-1].level >= level:
        stack.pop()
    if stack:
        stack[-1].children.append(node)
    else:
        roots.append(node)
    stack.append(node)


def _parse_markdown_headings(content: str) -> tuple[list[str], list[MarkdownHeadingNode]]:
    preamble_lines: list[str] = []
    heading_roots: list[MarkdownHeadingNode] = []
    heading_stack: list[MarkdownHeadingNode] = []
    lines = content.splitlines()
    in_fence = False
    active_fence_marker = ""

    def _append_line(line: str) -> None:
        target = heading_stack[-1].content_lines if heading_stack else preamble_lines
        target.append(line)

    index = 0
    while index < len(lines):
        line = lines[index]

        fence_match = _FENCE_RE.match(line)
        if in_fence:
            _append_line(line)
            if fence_match and fence_match.group(1)[0] == active_fence_marker[0] and len(fence_match.group(1)) >= len(active_fence_marker):
                in_fence = False
                active_fence_marker = ""
            index += 1
            continue

        if fence_match:
            in_fence = True
            active_fence_marker = fence_match.group(1)
            _append_line(line)
            index += 1
            continue

        atx_match = _ATX_HEADING_RE.match(line)
        if atx_match:
            _push_heading_node(
                heading_roots,
                heading_stack,
                title=atx_match.group(2).strip(),
                level=len(atx_match.group(1)),
            )
            index += 1
            continue

        if index + 1 < len(lines) and line.strip():
            setext_match = _SETEXT_HEADING_RE.match(lines[index + 1])
            if setext_match:
                underline = setext_match.group(1)
                _push_heading_node(
                    heading_roots,
                    heading_stack,
                    title=line.strip(),
                    level=1 if underline.startswith("=") else 2,
                )
                index += 2
                continue

        _append_line(line)
        index += 1

    return preamble_lines, heading_roots


def _convert_heading_node(node: MarkdownHeadingNode) -> MarkdownImportNode:
    children = [_convert_heading_node(child) for child in node.children]
    return MarkdownImportNode(
        name=node.title,
        block_type="group" if children else "field",
        content=_normalize_markdown_content(node.content_lines),
        children=children,
    )


def _build_raw_file_node(
    file_data: dict[str, Any],
    *,
    locale: str,
    index: int,
) -> MarkdownImportNode:
    return MarkdownImportNode(
        name=_file_root_name(file_data, locale=locale, index=index),
        block_type="field",
        content=str(file_data.get("content") or ""),
    )


def _build_heading_tree_node(
    file_data: dict[str, Any],
    *,
    locale: str,
    index: int,
) -> tuple[MarkdownImportNode, list[str], str]:
    content = str(file_data.get("content") or "")
    preamble_lines, heading_roots = _parse_markdown_headings(content)
    if not heading_roots:
        warning = rt(locale, "project.markdown_import.fallback_to_raw_file", file_label=_file_label(file_data, index))
        return _build_raw_file_node(file_data, locale=locale, index=index), [warning], "raw_file"

    children: list[MarkdownImportNode] = []
    preamble_content = _normalize_markdown_content(preamble_lines)
    if preamble_content:
        children.append(
            MarkdownImportNode(
                name=rt(locale, "project.markdown_import.intro_node"),
                block_type="field",
                content=preamble_content,
            )
        )
    children.extend(_convert_heading_node(node) for node in heading_roots)
    return (
        MarkdownImportNode(
            name=_file_root_name(file_data, locale=locale, index=index),
            block_type="group",
            content="",
            children=children,
        ),
        [],
        "heading_tree",
    )


def _count_nodes(node: MarkdownImportNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def import_markdown_files(
    *,
    db: Session,
    project_id: str,
    files: list[dict[str, Any]],
    import_mode: ImportMode,
) -> dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(rt(DEFAULT_LOCALE, "project.markdown_import.project_missing"))

    locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))
    if import_mode not in {"heading_tree", "raw_file"}:
        raise ValueError(rt(locale, "project.markdown_import.invalid_mode", mode=import_mode))
    if not files:
        raise ValueError(rt(locale, "project.markdown_import.empty_files"))

    prepared_roots: list[MarkdownImportNode] = []
    warnings: list[str] = []
    file_summaries: list[dict[str, Any]] = []

    for index, raw_file in enumerate(files):
        if not isinstance(raw_file, dict):
            raise ValueError(rt(locale, "project.markdown_import.invalid_file_payload", file_label=f"file[{index + 1}]"))
        if not isinstance(raw_file.get("name"), str) or not str(raw_file.get("name") or "").strip():
            raise ValueError(rt(locale, "project.markdown_import.invalid_file_name", file_label=_file_label(raw_file, index)))
        if not isinstance(raw_file.get("content"), str):
            raise ValueError(rt(locale, "project.markdown_import.invalid_file_content", file_label=_file_label(raw_file, index)))

        if import_mode == "raw_file":
            node = _build_raw_file_node(raw_file, locale=locale, index=index)
            file_warnings: list[str] = []
            mode_used: ImportMode = "raw_file"
        else:
            node, file_warnings, mode_used = _build_heading_tree_node(raw_file, locale=locale, index=index)

        warnings.extend(file_warnings)
        prepared_roots.append(node)
        file_summaries.append(
            {
                "name": str(raw_file.get("name") or ""),
                "path": str(raw_file.get("path") or ""),
                "mode_used": mode_used,
                "root_name": node.name,
                "blocks_created": _count_nodes(node),
                "warning_count": len(file_warnings),
            }
        )

    existing_top_level_count = (
        db.query(ContentBlock)
        .filter(
            ContentBlock.project_id == project_id,
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.deleted_at == None,  # noqa: E711
        )
        .count()
    )

    created_count = 0

    def _persist(node: MarkdownImportNode, parent_id: str | None, depth: int, order_index: int) -> None:
        nonlocal created_count
        block = ContentBlock(
            id=generate_uuid(),
            project_id=project_id,
            parent_id=parent_id,
            name=node.name,
            block_type=node.block_type,
            depth=depth,
            order_index=order_index,
            content=node.content,
            status="completed" if node.content.strip() else "pending",
            ai_prompt="",
            constraints={},
            pre_questions=[],
            pre_answers={},
            guidance_input="",
            guidance_output="",
            depends_on=[],
            special_handler=None,
            need_review=True,
            auto_generate=False,
            is_collapsed=False,
            model_override=None,
            digest=None,
        )
        db.add(block)
        created_count += 1
        for child_index, child in enumerate(node.children):
            _persist(child, block.id, depth + 1, child_index)

    for root_index, root in enumerate(prepared_roots):
        _persist(root, None, 0, existing_top_level_count + root_index)

    db.commit()

    deduped_warnings = list(dict.fromkeys(warnings))
    return {
        "message": rt(
            locale,
            "project.markdown_import.success",
            file_count=len(prepared_roots),
            blocks_created=created_count,
        ),
        "import_mode": import_mode,
        "file_count": len(prepared_roots),
        "root_count": len(prepared_roots),
        "blocks_created": created_count,
        "warning_count": len(deduped_warnings),
        "warnings": deduped_warnings,
        "files": file_summaries,
    }
