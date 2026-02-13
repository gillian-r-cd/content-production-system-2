# backend/core/phase_service.py
# 功能: 阶段推进的唯一业务逻辑入口
# 主要函数: advance_phase()
# 数据结构: PhaseAdvanceResult (dataclass)
#
# 设计原则: agent_tools 和 api/agent 的推进逻辑曾各写一遍，现统一到此

"""
阶段推进服务。

提供 advance_phase() 作为推进项目到下一组/跳转指定组的唯一逻辑。
调用者（agent tool / API endpoint）负责 commit 和返回格式。
"""

from dataclasses import dataclass
from typing import Optional, Dict

from core.phase_config import PHASE_ALIAS, PHASE_DISPLAY_NAMES  # 从统一配置导入


@dataclass
class PhaseAdvanceResult:
    """阶段推进结果"""
    success: bool
    prev_phase: Optional[str] = None
    next_phase: Optional[str] = None
    phase_status: Optional[dict] = None
    error: Optional[str] = None

    @property
    def display_name(self) -> str:
        """下一组的中文显示名"""
        if self.next_phase:
            return PHASE_DISPLAY_NAMES.get(self.next_phase, self.next_phase)
        return ""


def advance_phase(project, target_phase: str = "") -> PhaseAdvanceResult:
    """
    推进项目到下一组或跳转到指定组。

    核心逻辑（调用者负责 db.commit()）：
    1. 如果 target_phase 非空 → 解析中文别名 → 跳转到指定组
    2. 如果 target_phase 为空 → 自动推进到下一组

    Args:
        project: Project ORM 对象（会被直接修改 current_phase 和 phase_status）
        target_phase: 目标组名称（中文或代码），为空表示自动下一组

    Returns:
        PhaseAdvanceResult: 推进结果
    """
    phase_order = project.phase_order or []
    if not phase_order:
        return PhaseAdvanceResult(success=False, error="项目未定义组顺序")

    # ---- 跳转到指定组 ----
    if target_phase:
        resolved = PHASE_ALIAS.get(target_phase.strip(), target_phase.strip())
        if resolved not in phase_order:
            return PhaseAdvanceResult(
                success=False,
                error=f"找不到组「{target_phase}」，可选: {', '.join(phase_order)}",
            )
        prev = project.current_phase
        ps = dict(project.phase_status or {})
        if prev:
            ps[prev] = "completed"
        ps[resolved] = "in_progress"
        project.phase_status = ps
        project.current_phase = resolved
        return PhaseAdvanceResult(
            success=True, prev_phase=prev, next_phase=resolved, phase_status=ps,
        )

    # ---- 自动下一组 ----
    try:
        idx = phase_order.index(project.current_phase)
    except ValueError:
        return PhaseAdvanceResult(
            success=False,
            error=f"无法确定当前组位置 (current_phase={project.current_phase})",
        )

    if idx >= len(phase_order) - 1:
        return PhaseAdvanceResult(success=False, error="已经是最后一个组了")

    prev = project.current_phase
    next_p = phase_order[idx + 1]
    ps = dict(project.phase_status or {})
    ps[prev] = "completed"
    ps[next_p] = "in_progress"
    project.phase_status = ps
    project.current_phase = next_p
    return PhaseAdvanceResult(
        success=True, prev_phase=prev, next_phase=next_p, phase_status=ps,
    )

