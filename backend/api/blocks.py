# backend/api/blocks.py
# 功能: 统一内容块 API，支持 CRUD、移动、生成
# 主要路由: /api/blocks
# 数据结构: ContentBlock 的树形操作

"""
内容块 API
统一管理项目中的所有内容块（阶段、字段、方案等）
支持无限层级、拖拽排序、依赖引用
"""

import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from datetime import datetime
from core.models import (
    ContentBlock,
    BlockHistory,
    Project,
    PhaseTemplate,
    generate_uuid,
    BLOCK_TYPES,
    BLOCK_STATUS,
)
from core.prompt_engine import PromptEngine, GoldenContext

router = APIRouter(prefix="/api/blocks", tags=["content-blocks"])


def _build_constraints_text(constraints: Optional[Dict]) -> str:
    """构建约束文本，强调 Markdown 格式"""
    lines = []
    
    if constraints:
        if constraints.get("max_length"):
            lines.append(f"- 字数限制：不超过 {constraints['max_length']} 字")
        
        output_format = constraints.get("output_format", "markdown")
    else:
        output_format = "markdown"
    
    if output_format == "markdown":
        lines.append("- 输出格式：**Markdown 富文本**")
        lines.append("  - 必须使用标准 Markdown 语法")
        lines.append("  - 标题使用 # ## ### 格式")
        lines.append("  - 表格必须包含表头分隔行（如 | --- | --- |）")
        lines.append("  - 列表使用 - 或 1. 格式")
        lines.append("  - 重点内容使用 **粗体** 或 *斜体*")
    elif output_format:
        format_map = {
            "plain_text": "纯文本（不使用任何格式化符号）",
            "json": "JSON 格式（必须是有效的 JSON）",
            "list": "列表格式（每行一项）",
        }
        lines.append(f"- 输出格式：{format_map.get(output_format, output_format)}")
    
    return "\n".join(lines)


# ========== Pydantic 模型 ==========

class BlockCreate(BaseModel):
    """创建内容块请求"""
    project_id: str
    parent_id: Optional[str] = None
    name: str
    block_type: str = "field"
    content: str = ""
    ai_prompt: str = ""
    constraints: Optional[Dict] = None
    depends_on: List[str] = Field(default_factory=list)
    special_handler: Optional[str] = None
    need_review: bool = True
    order_index: Optional[int] = None
    pre_questions: List[str] = Field(default_factory=list)  # 生成前提问


class BlockUpdate(BaseModel):
    """更新内容块请求"""
    name: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    ai_prompt: Optional[str] = None
    constraints: Optional[Dict] = None
    pre_questions: Optional[List[str]] = None
    pre_answers: Optional[Dict] = None
    depends_on: Optional[List[str]] = None
    need_review: Optional[bool] = None
    is_collapsed: Optional[bool] = None


class BlockMove(BaseModel):
    """移动内容块请求"""
    new_parent_id: Optional[str] = None  # None = 移动到顶级
    new_order_index: int


class BlockResponse(BaseModel):
    """内容块响应"""
    id: str
    project_id: str
    parent_id: Optional[str]
    name: str
    block_type: str
    depth: int
    order_index: int
    content: str
    status: str
    ai_prompt: str
    constraints: Dict
    pre_questions: List[str] = Field(default_factory=list)
    pre_answers: Dict = Field(default_factory=dict)
    depends_on: List[str]
    special_handler: Optional[str]
    need_review: bool
    is_collapsed: bool
    children: List["BlockResponse"] = Field(default_factory=list)
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class BlockTreeResponse(BaseModel):
    """项目内容块树响应"""
    project_id: str
    blocks: List[BlockResponse]
    total_count: int


# ========== 辅助函数 ==========

def _block_to_response(block: ContentBlock, include_children: bool = False) -> BlockResponse:
    """转换 ContentBlock 为响应模型（排除已删除的子块）"""
    children = []
    if include_children and block.children:
        # 过滤已删除的子块
        active_children = [c for c in block.children if c.deleted_at is None]
        children = [_block_to_response(c, include_children=True) for c in active_children]
    
    return BlockResponse(
        id=block.id,
        project_id=block.project_id,
        parent_id=block.parent_id,
        name=block.name,
        block_type=block.block_type,
        depth=block.depth,
        order_index=block.order_index,
        content=block.content or "",
        status=block.status or "pending",
        ai_prompt=block.ai_prompt or "",
        constraints=block.constraints or {},
        pre_questions=block.pre_questions or [],  # 生成前提问
        pre_answers=block.pre_answers or {},      # 用户回答
        depends_on=block.depends_on or [],
        special_handler=block.special_handler,
        need_review=block.need_review,
        is_collapsed=block.is_collapsed,
        children=children,
        created_at=block.created_at.isoformat() if block.created_at else None,
        updated_at=block.updated_at.isoformat() if block.updated_at else None,
    )


def _calculate_depth(block: ContentBlock, db: Session) -> int:
    """计算内容块的层级深度"""
    if not block.parent_id:
        return 0
    parent = db.query(ContentBlock).filter(ContentBlock.id == block.parent_id).first()
    if not parent:
        return 0
    return parent.depth + 1


def _get_next_order_index(project_id: str, parent_id: Optional[str], db: Session) -> int:
    """获取下一个排序索引"""
    query = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
    )
    max_order = query.count()
    return max_order


def _reorder_siblings(project_id: str, parent_id: Optional[str], db: Session):
    """重新排序同级内容块（排除已删除）"""
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    for idx, sibling in enumerate(siblings):
        sibling.order_index = idx


# ========== API 路由 ==========

@router.get("/project/{project_id}", response_model=BlockTreeResponse)
def get_project_blocks(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取项目的所有内容块（树形结构，排除已删除）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 自动修复卡住的块：in_progress 但无内容 → 重置为 pending
    stuck_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
        ContentBlock.status == "in_progress",
        (ContentBlock.content == None) | (ContentBlock.content == ""),
    ).all()
    if stuck_blocks:
        for sb in stuck_blocks:
            print(f"[RECOVERY] 重置卡住的块: {sb.name} (in_progress → pending)")
            sb.status = "pending"
        db.commit()
    
    # 获取所有顶级块（parent_id = None，排除已删除）
    top_level_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == None,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    # 转换为响应（包含子块）
    blocks = [_block_to_response(b, include_children=True) for b in top_level_blocks]
    
    # 统计总数（排除已删除）
    total = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).count()
    
    return BlockTreeResponse(
        project_id=project_id,
        blocks=blocks,
        total_count=total,
    )


@router.get("/{block_id}", response_model=BlockResponse)
def get_block(
    block_id: str,
    include_children: bool = False,
    db: Session = Depends(get_db),
):
    """获取单个内容块（排除已删除）"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    return _block_to_response(block, include_children=include_children)


@router.post("/", response_model=BlockResponse)
def create_block(
    data: BlockCreate,
    db: Session = Depends(get_db),
):
    """创建内容块"""
    # 验证项目存在
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 验证父块存在（如果指定）
    depth = 0
    if data.parent_id:
        parent = db.query(ContentBlock).filter(ContentBlock.id == data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父内容块不存在")
        depth = parent.depth + 1
    
    # 验证块类型
    if data.block_type not in BLOCK_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的块类型: {data.block_type}")
    
    # 计算排序索引
    order_index = data.order_index
    if order_index is None:
        order_index = _get_next_order_index(data.project_id, data.parent_id, db)
    
    block = ContentBlock(
        id=generate_uuid(),
        project_id=data.project_id,
        parent_id=data.parent_id,
        name=data.name,
        block_type=data.block_type,
        depth=depth,
        order_index=order_index,
        content=data.content,
        status="pending",
        ai_prompt=data.ai_prompt,
        constraints=data.constraints or {},
        depends_on=data.depends_on,
        special_handler=data.special_handler,
        need_review=data.need_review,
        pre_questions=data.pre_questions,  # 保存生成前提问
    )
    
    db.add(block)
    db.commit()
    db.refresh(block)
    
    return _block_to_response(block)


@router.put("/{block_id}", response_model=BlockResponse)
def update_block(
    block_id: str,
    data: BlockUpdate,
    db: Session = Depends(get_db),
):
    """更新内容块"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    # 更新字段
    from sqlalchemy.orm.attributes import flag_modified
    
    if data.name is not None:
        block.name = data.name
    if data.content is not None:
        block.content = data.content
    if data.status is not None:
        if data.status not in BLOCK_STATUS:
            raise HTTPException(status_code=400, detail=f"无效的状态: {data.status}")
        block.status = data.status
    if data.ai_prompt is not None:
        block.ai_prompt = data.ai_prompt
    if data.constraints is not None:
        block.constraints = data.constraints
        flag_modified(block, "constraints")
    if data.pre_questions is not None:
        block.pre_questions = data.pre_questions
        flag_modified(block, "pre_questions")
    if data.pre_answers is not None:
        block.pre_answers = data.pre_answers
        flag_modified(block, "pre_answers")
    if data.depends_on is not None:
        block.depends_on = data.depends_on
        flag_modified(block, "depends_on")
    if data.need_review is not None:
        block.need_review = data.need_review
    if data.is_collapsed is not None:
        block.is_collapsed = data.is_collapsed
    
    db.commit()
    db.refresh(block)
    
    return _block_to_response(block)


@router.delete("/{block_id}")
def delete_block(
    block_id: str,
    db: Session = Depends(get_db),
):
    """
    软删除内容块（级联软删除子块）
    保存历史记录，支持撤回
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    project_id = block.project_id
    parent_id = block.parent_id
    
    # 1. 保存块快照
    block_snapshot = block.to_tree_dict()
    # 移除 children 避免重复
    block_snapshot.pop("children", None)
    
    # 2. 收集并保存所有子块快照
    def collect_descendants(parent: ContentBlock):
        """递归收集所有后代"""
        descendants = []
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == parent.id,
            ContentBlock.deleted_at == None,
        ).all()
        for child in children:
            snapshot = child.to_tree_dict()
            snapshot.pop("children", None)
            descendants.append(snapshot)
            descendants.extend(collect_descendants(child))
        return descendants
    
    children_snapshots = collect_descendants(block)
    
    # 3. 创建历史记录
    history = BlockHistory(
        id=generate_uuid(),
        project_id=project_id,
        action="delete",
        block_id=block.id,
        block_snapshot=block_snapshot,
        children_snapshots=children_snapshots,
        undone=False,
    )
    db.add(history)
    
    # 4. 软删除主块和所有子块
    now = datetime.utcnow()
    block.deleted_at = now
    
    def soft_delete_children(parent_id: str):
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == parent_id,
            ContentBlock.deleted_at == None,
        ).all()
        for child in children:
            child.deleted_at = now
            soft_delete_children(child.id)
    
    soft_delete_children(block_id)
    
    # 5. 重新排序同级
    _reorder_siblings(project_id, parent_id, db)
    
    db.commit()
    
    return {
        "message": "删除成功",
        "history_id": history.id,
        "can_undo": True,
    }


@router.post("/{block_id}/move", response_model=BlockResponse)
def move_block(
    block_id: str,
    data: BlockMove,
    db: Session = Depends(get_db),
):
    """移动内容块（改变父级或排序）"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    old_parent_id = block.parent_id
    
    # 验证新父块（如果指定）
    new_depth = 0
    if data.new_parent_id:
        new_parent = db.query(ContentBlock).filter(
            ContentBlock.id == data.new_parent_id
        ).first()
        if not new_parent:
            raise HTTPException(status_code=404, detail="目标父内容块不存在")
        
        # 防止移动到自己的子孙节点下
        ancestors = []
        current = new_parent
        while current:
            if current.id == block_id:
                raise HTTPException(status_code=400, detail="不能移动到自己的子节点下")
            ancestors.append(current.id)
            current = current.parent
        
        new_depth = new_parent.depth + 1
    
    # 更新父级和深度
    block.parent_id = data.new_parent_id
    block.depth = new_depth
    block.order_index = data.new_order_index
    
    # 递归更新子块深度
    def update_children_depth(parent_block: ContentBlock):
        for child in parent_block.children:
            child.depth = parent_block.depth + 1
            update_children_depth(child)
    
    update_children_depth(block)
    
    # 重新排序旧位置的同级
    if old_parent_id != data.new_parent_id:
        _reorder_siblings(block.project_id, old_parent_id, db)
    
    # 调整新位置的同级排序（排除已删除）
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.parent_id == data.new_parent_id,
        ContentBlock.id != block_id,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    # 插入到指定位置
    for idx, sibling in enumerate(siblings):
        if idx >= data.new_order_index:
            sibling.order_index = idx + 1
        else:
            sibling.order_index = idx
    
    db.commit()
    db.refresh(block)
    
    return _block_to_response(block)


@router.post("/{block_id}/generate")
async def generate_block_content(
    block_id: str,
    db: Session = Depends(get_db),
):
    """生成内容块内容"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查依赖是否满足（只要有内容就满足，不需要 status 是 completed）
    if block.depends_on:
        deps = db.query(ContentBlock).filter(
            ContentBlock.id.in_(block.depends_on)
        ).all()
        
        # 改为检查是否有内容，而不是状态
        incomplete = [d for d in deps if not d.content or not d.content.strip()]
        if incomplete:
            raise HTTPException(
                status_code=400,
                detail=f"依赖内容为空: {', '.join([d.name for d in incomplete])}"
            )
    
    # 获取创作者特质（从关系获取，转换为提示词格式）
    creator_profile_text = ""
    if project.creator_profile:
        creator_profile_text = project.creator_profile.to_prompt_context()
    
    # 构建 Golden Context（只包含 creator_profile）
    gc = GoldenContext(
        creator_profile=creator_profile_text,
    )
    
    # 获取依赖内容
    dependency_content = ""
    if block.depends_on:
        all_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == block.project_id
        ).all()
        blocks_by_id = {b.id: b for b in all_blocks}
        dependency_content = block.get_dependency_content(blocks_by_id)
    
    # 构建提示词
    prompt_engine = PromptEngine()
    
    constraints_text = _build_constraints_text(block.constraints)
    
    # 构建预提问答案文本
    pre_answers_text = ""
    if block.pre_answers:
        answers = [f"- {q}: {a}" for q, a in block.pre_answers.items() if a]
        if answers:
            pre_answers_text = f"---\n# 用户补充信息（生成前提问的回答）\n" + "\n".join(answers)
    
    system_prompt = f"""{gc.to_prompt()}

---

# 当前任务
{block.ai_prompt or '请生成内容。'}

{pre_answers_text}

{f'---{chr(10)}# 参考内容{chr(10)}{dependency_content}' if dependency_content else ''}

---
# 生成约束（必须严格遵守！）
{constraints_text}
"""
    
    # 调用 AI
    from core.ai_client import AIClient, ChatMessage
    ai_client = AIClient()
    
    block.status = "in_progress"
    db.commit()
    
    try:
        # 将 system_prompt 作为第一条消息，使用 ChatMessage 对象
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"请生成「{block.name}」的内容。"),
        ]
        response = await ai_client.async_chat(messages=messages)
        
        block.content = response.content
        block.status = "completed"  # 生成成功即为完成，need_review 是独立的审核标记
        
        # 创建 GenerationLog 记录
        from core.models import GenerationLog, generate_uuid
        gen_log = GenerationLog(
            id=generate_uuid(),
            project_id=block.project_id,
            field_id=block.id,  # 使用 block.id 作为 field_id
            phase=block.parent_id or "content_block",  # 使用父级作为阶段标识
            operation=f"block_generate_{block.name}",
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            duration_ms=response.duration_ms,
            prompt_input=system_prompt,
            prompt_output=response.content,
            cost=response.cost,
            status="success",
        )
        db.add(gen_log)
        db.commit()
        
        # 自动触发依赖此块的其他块（使用独立 DB session 避免冲突）
        from core.database import get_session_maker
        SessionLocal = get_session_maker()
        trigger_db = SessionLocal()
        try:
            auto_triggered = await _trigger_dependent_blocks(block.id, block.project_id, trigger_db)
        except Exception as trigger_error:
            print(f"[AUTO-TRIGGER] 触发依赖块失败: {trigger_error}")
            auto_triggered = []
        finally:
            trigger_db.close()
        
        return {
            "block_id": block.id,
            "content": response.content,
            "status": block.status,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost": response.cost,
            "auto_triggered": auto_triggered,  # 返回被自动触发的块列表
        }
        
    except Exception as e:
        block.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


async def _trigger_dependent_blocks(completed_block_id: str, project_id: str, db: Session) -> List[str]:
    """
    自动触发依赖已完成块的其他块（并行执行）
    
    条件：
    1. 依赖了刚完成的块
    2. need_review = False（自动执行模式）
    3. 所有依赖都有内容（满足生成条件）
    4. 当前状态是 pending / failed / in_progress（无内容，即卡住的块）
    5. 如果有 pre_questions，必须已填写 pre_answers
    
    Returns:
        被触发的块 ID 列表
    """
    import asyncio
    from core.ai_client import AIClient, ChatMessage
    from core.prompt_engine import PromptEngine, GoldenContext
    from core.models import GenerationLog, generate_uuid, Project
    
    print(f"\n[AUTO-TRIGGER] ========== 检查自动触发 ==========")
    print(f"[AUTO-TRIGGER] 触发源块 ID: {completed_block_id}")
    print(f"[AUTO-TRIGGER] 项目 ID: {project_id}")
    
    triggered_ids = []
    
    # 查找所有可能被触发的块（自动模式 + 可重新生成的状态）
    dependent_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
        ContentBlock.need_review == False,  # 只有自动执行的才触发
        ContentBlock.status.in_(["pending", "failed"]),  # pending 或 failed 可重试
    ).all()
    
    # 也包含 in_progress 但没有内容的块（卡住的块）
    stuck_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
        ContentBlock.need_review == False,
        ContentBlock.status == "in_progress",
        (ContentBlock.content == None) | (ContentBlock.content == ""),
    ).all()
    dependent_blocks.extend(stuck_blocks)
    
    print(f"[AUTO-TRIGGER] 找到 {len(dependent_blocks)} 个自动模式块 (pending/failed/stuck)")
    
    # 也检查 need_review=True 但有未回答提问的块（信息补充完即可触发）——不自动触发这些
    # need_review=True 的块需要用户手动确认后再生成
    
    # 筛选出确实依赖了 completed_block_id 的块
    blocks_to_trigger = []
    for dep_block in dependent_blocks:
        if completed_block_id in (dep_block.depends_on or []):
            blocks_to_trigger.append(dep_block)
        else:
            print(f"[AUTO-TRIGGER]   - {dep_block.name}: 不依赖触发源块，跳过")
    
    if not blocks_to_trigger:
        print(f"[AUTO-TRIGGER] 没有找到依赖触发源块的自动块，退出")
        return []
    
    print(f"[AUTO-TRIGGER] 找到 {len(blocks_to_trigger)} 个依赖触发源块的块: {[b.name for b in blocks_to_trigger]}")
    
    # 检查每个块的所有依赖是否都满足
    all_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).all()
    blocks_by_id = {b.id: b for b in all_blocks}
    
    project = db.query(Project).filter(Project.id == project_id).first()
    
    # 筛选出满足所有条件的块
    ready_blocks = []
    for block in blocks_to_trigger:
        # 检查所有依赖是否都有内容
        all_deps_ready = True
        for dep_id in (block.depends_on or []):
            dep = blocks_by_id.get(dep_id)
            if not dep or not dep.content or not dep.content.strip():
                all_deps_ready = False
                print(f"[AUTO-TRIGGER]   - {block.name}: 依赖 '{dep.name if dep else dep_id}' 无内容，跳过")
                break
        
        if not all_deps_ready:
            continue
        
        # 检查 pre_questions：如果有提问但没有回答，不自动触发
        if block.pre_questions and len(block.pre_questions) > 0:
            answers = block.pre_answers or {}
            unanswered = [q for q in block.pre_questions if not answers.get(q, "").strip()]
            if unanswered:
                print(f"[AUTO-TRIGGER]   - {block.name}: 有 {len(unanswered)} 个生成前提问未回答，跳过")
                continue
        
        print(f"[AUTO-TRIGGER]   ✓ {block.name}: 所有条件满足，准备生成")
        ready_blocks.append(block)
    
    if not ready_blocks:
        print(f"[AUTO-TRIGGER] 没有满足所有条件的块，退出")
        return []
    
    print(f"[AUTO-TRIGGER] 🚀 开始顺序生成 {len(ready_blocks)} 个块: {[b.name for b in ready_blocks]}")
    
    # 顺序执行每个块的生成（SQLite 不支持并行写入同一 session）
    for block in ready_blocks:
        block.status = "in_progress"
        db.commit()
        
        try:
            # 获取创作者特质
            creator_profile_text = ""
            if project and project.creator_profile:
                creator_profile_text = project.creator_profile.to_prompt_context()
            
            gc = GoldenContext(creator_profile=creator_profile_text)
            
            # 获取依赖内容（每次重新加载，因为前面的块可能刚生成了新内容）
            db.refresh(block)
            # 重新构建 blocks_by_id（可能有更新）
            fresh_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.deleted_at == None,
            ).all()
            fresh_blocks_by_id = {b.id: b for b in fresh_blocks}
            
            dependency_content = block.get_dependency_content(fresh_blocks_by_id)
            
            # 构建约束文本
            constraints_text = _build_constraints_text(block.constraints)
            
            # 构建预提问答案文本
            pre_answers_text = ""
            if block.pre_answers:
                answers = [f"- {q}: {a}" for q, a in block.pre_answers.items() if a]
                if answers:
                    pre_answers_text = f"---\n# 用户补充信息（生成前提问的回答）\n" + "\n".join(answers)
            
            system_prompt = f"""{gc.to_prompt()}

---

# 当前任务
{block.ai_prompt or '请生成内容。'}

{pre_answers_text}

{f'---{chr(10)}# 参考内容{chr(10)}{dependency_content}' if dependency_content else ''}

---
# 生成约束（必须严格遵守！）
{constraints_text}
"""
            
            print(f"[AUTO-TRIGGER] 📝 {block.name} - 系统提示词长度: {len(system_prompt)} 字符")
            
            ai_client = AIClient()
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=f"请生成「{block.name}」的内容。"),
            ]
            response = await ai_client.async_chat(messages=messages)
            
            block.content = response.content
            block.status = "completed"
            
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=block.project_id,
                field_id=block.id,
                phase=block.parent_id or "auto_trigger",
                operation=f"auto_generate_{block.name}",
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                duration_ms=response.duration_ms,
                prompt_input=system_prompt,
                prompt_output=response.content,
                cost=response.cost,
                status="success",
            )
            db.add(gen_log)
            db.commit()
            
            print(f"[AUTO-TRIGGER] ✅ 自动生成 {block.name} 成功 (tokens: {response.tokens_in}+{response.tokens_out})")
            triggered_ids.append(block.id)
            
        except Exception as e:
            print(f"[AUTO-TRIGGER] ❌ 自动生成 {block.name} 失败: {e}")
            import traceback
            traceback.print_exc()
            block.status = "pending"  # 重置为 pending 以便下次重试
            db.commit()
    
    print(f"[AUTO-TRIGGER] 完成: {len(triggered_ids)}/{len(ready_blocks)} 成功")
    
    # 对所有成功完成的块，递归触发它们的下游依赖
    for completed_id in list(triggered_ids):  # 用 list() 复制，因为递归会修改 triggered_ids
        print(f"[AUTO-TRIGGER] 递归检查 {completed_id} 的下游依赖...")
        try:
            sub_triggered = await _trigger_dependent_blocks(completed_id, project_id, db)
            triggered_ids.extend(sub_triggered)
        except Exception as sub_error:
            print(f"[AUTO-TRIGGER] 递归触发异常: {sub_error}")
    
    print(f"[AUTO-TRIGGER] ========== 触发完毕，共 {len(triggered_ids)} 个块 ==========\n")
    return triggered_ids


@router.post("/{block_id}/generate/stream")
async def generate_block_content_stream(
    block_id: str,
    db: Session = Depends(get_db),
):
    """流式生成内容块内容"""
    import json
    import time
    from fastapi.responses import StreamingResponse
    
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查依赖是否满足
    if block.depends_on:
        deps = db.query(ContentBlock).filter(
            ContentBlock.id.in_(block.depends_on)
        ).all()
        incomplete = [d for d in deps if not d.content or not d.content.strip()]
        if incomplete:
            raise HTTPException(
                status_code=400,
                detail=f"依赖内容为空: {', '.join([d.name for d in incomplete])}"
            )
    
    # 获取创作者特质
    creator_profile_text = ""
    if project.creator_profile:
        creator_profile_text = project.creator_profile.to_prompt_context()
    
    gc = GoldenContext(creator_profile=creator_profile_text)
    
    # 获取依赖内容
    dependency_content = ""
    if block.depends_on:
        all_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == block.project_id
        ).all()
        blocks_by_id = {b.id: b for b in all_blocks}
        dependency_content = block.get_dependency_content(blocks_by_id)
    
    # 构建约束文本
    constraints_text = _build_constraints_text(block.constraints)
    
    # 构建预提问答案文本
    pre_answers_text = ""
    if block.pre_answers:
        answers = [f"- {q}: {a}" for q, a in block.pre_answers.items() if a]
        if answers:
            pre_answers_text = f"---\n# 用户补充信息（生成前提问的回答）\n" + "\n".join(answers)
    
    system_prompt = f"""{gc.to_prompt()}

---

# 当前任务
{block.ai_prompt or '请生成内容。'}

{pre_answers_text}

{f'---{chr(10)}# 参考内容{chr(10)}{dependency_content}' if dependency_content else ''}

---
# 生成约束（必须严格遵守！）
{constraints_text}
"""
    
    from core.ai_client import AIClient, ChatMessage
    ai_client = AIClient()
    
    block.status = "in_progress"
    db.commit()
    
    start_time = time.time()
    
    async def stream_generator():
        content_parts = []
        try:
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=f"请生成「{block.name}」的内容。"),
            ]
            
            async for chunk in ai_client.stream_chat(messages=messages):
                content_parts.append(chunk)
                data = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            
            # 保存完整内容
            full_content = "".join(content_parts)
            block.content = full_content
            block.status = "completed"  # 生成成功即为完成，need_review 是独立的审核标记
            
            # 计算耗时和tokens（估算）
            duration_ms = int((time.time() - start_time) * 1000)
            tokens_in = len(system_prompt) // 4
            tokens_out = len(full_content) // 4
            
            # 创建日志记录
            from core.models import GenerationLog, generate_uuid
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=block.project_id,
                field_id=block.id,
                phase=block.parent_id or "content_block",
                operation=f"block_generate_stream_{block.name}",
                model="gpt-5.1",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration_ms=duration_ms,
                prompt_input=system_prompt,
                prompt_output=full_content,
                cost=GenerationLog.calculate_cost("gpt-5.1", tokens_in, tokens_out),
                status="success",
            )
            db.add(gen_log)
            db.commit()
            
            # 在发送完成事件之前，启动后台自动触发任务
            # 必须在 yield 之前启动，因为 yield done 后客户端会关闭连接，
            # 导致 generator 被取消，后续代码不会执行
            completed_block_id = block.id
            completed_project_id = block.project_id
            
            async def _background_auto_trigger():
                """后台自动触发任务（使用独立的 DB session）"""
                from core.database import get_session_maker
                SessionLocal = get_session_maker()
                bg_db = SessionLocal()
                try:
                    print(f"[STREAM] 流式生成完成，后台检查自动触发...")
                    auto_triggered = await _trigger_dependent_blocks(
                        completed_block_id, completed_project_id, bg_db
                    )
                    if auto_triggered:
                        print(f"[STREAM] ✅ 后台自动触发了 {len(auto_triggered)} 个块: {auto_triggered}")
                    else:
                        print(f"[STREAM] 没有需要自动触发的块")
                except Exception as trigger_error:
                    print(f"[AUTO-TRIGGER] 后台触发依赖块失败: {trigger_error}")
                    import traceback
                    traceback.print_exc()
                finally:
                    bg_db.close()
            
            # 启动后台任务（不等待完成）
            asyncio.create_task(_background_auto_trigger())
            
            # 发送完成事件
            done_data = json.dumps({
                "done": True,
                "block_id": block.id,
                "content": full_content,
                "status": block.status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"
            
        except Exception as e:
            block.status = "failed"
            db.commit()
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/project/{project_id}/apply-template")
def apply_template_to_project(
    project_id: str,
    template_id: str,
    db: Session = Depends(get_db),
):
    """将阶段模板应用到项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 检查项目是否已有内容块
    existing = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id
    ).count()
    
    if existing > 0:
        raise HTTPException(
            status_code=400,
            detail="项目已有内容块，请先清空或创建新项目"
        )
    
    # 应用模板
    blocks_to_create = template.apply_to_project(project_id)
    
    for block_data in blocks_to_create:
        block = ContentBlock(**block_data)
        db.add(block)
    
    db.commit()
    
    return {
        "message": f"已应用模板「{template.name}」",
        "blocks_created": len(blocks_to_create),
    }


@router.post("/project/{project_id}/migrate")
def migrate_project_to_blocks(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    将传统项目的 project_fields 迁移到 content_blocks 架构
    
    这会：
    1. 为每个阶段创建一个 phase 类型的 ContentBlock
    2. 将每个 ProjectField 转换为 field 类型的 ContentBlock
    3. 保持原有的依赖关系
    """
    from core.models import ProjectField
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 如果已经是灵活架构，无需迁移
    if project.use_flexible_architecture:
        raise HTTPException(
            status_code=400,
            detail="项目已使用灵活架构，无需迁移"
        )
    
    # 清理可能存在的旧内容块（重新迁移）
    existing_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id
    ).all()
    
    if existing_blocks:
        for block in existing_blocks:
            db.delete(block)
        db.flush()  # 确保删除生效
    
    # 获取所有传统字段
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id
    ).all()
    
    # 阶段到特殊处理器的映射
    phase_handler_map = {
        "intent": "intent",
        "research": "research",
        "simulate": "simulate",
        "evaluate": "evaluate",
    }
    
    # 阶段显示名称映射
    display_names = {
        "intent": "意图分析",
        "research": "消费者调研",
        "design_inner": "内涵设计",
        "produce_inner": "内涵生产",
        "design_outer": "外延设计",
        "produce_outer": "外延生产",
        "simulate": "消费者模拟",
        "evaluate": "评估",
    }
    
    # 创建阶段块
    phase_blocks = {}
    for idx, phase_name in enumerate(project.phase_order):
        phase_id = generate_uuid()
        
        phase_block = ContentBlock(
            id=phase_id,
            project_id=project.id,
            parent_id=None,
            name=display_names.get(phase_name, phase_name),
            block_type="phase",
            depth=0,
            order_index=idx,
            status=project.phase_status.get(phase_name, "pending"),
            special_handler=phase_handler_map.get(phase_name),
            need_review=not project.agent_autonomy.get(phase_name, True),
        )
        db.add(phase_block)
        phase_blocks[phase_name] = phase_id
    
    db.flush()  # 确保阶段块有 ID
    
    # 字段 ID 映射（旧 ProjectField.id -> 新 ContentBlock.id）
    field_id_map = {}
    
    # 按阶段分组统计字段顺序
    phase_field_counters = {phase: 0 for phase in phase_blocks.keys()}
    
    # 创建字段块
    for field in fields:
        parent_phase_id = phase_blocks.get(field.phase)
        if not parent_phase_id:
            continue
        
        new_id = generate_uuid()
        field_id_map[field.id] = new_id
        
        # 获取当前阶段的字段顺序
        order_idx = phase_field_counters.get(field.phase, 0)
        phase_field_counters[field.phase] = order_idx + 1
        
        field_block = ContentBlock(
            id=new_id,
            project_id=project.id,
            parent_id=parent_phase_id,
            name=field.name,
            block_type="field",
            depth=1,
            order_index=order_idx,
            content=field.content or "",
            status=field.status or "pending",
            ai_prompt=field.ai_prompt or "",
            constraints=field.constraints or {},
            depends_on=[],  # 稍后更新
            need_review=getattr(field, 'need_review', True),
        )
        db.add(field_block)
    
    db.flush()
    
    # 更新依赖关系
    for field in fields:
        new_id = field_id_map.get(field.id)
        if not new_id:
            continue
        
        old_depends = []
        if field.dependencies and isinstance(field.dependencies, dict):
            old_depends = field.dependencies.get("depends_on", [])
        
        new_depends = [field_id_map[old_id] for old_id in old_depends if old_id in field_id_map]
        
        if new_depends:
            block = db.query(ContentBlock).filter(ContentBlock.id == new_id).first()
            if block:
                block.depends_on = new_depends
    
    # 更新项目为灵活架构
    project.use_flexible_architecture = True
    
    db.commit()
    
    return {
        "message": "迁移成功",
        "phases_created": len(phase_blocks),
        "fields_migrated": len(field_id_map),
    }


# ========== 撤回功能 ==========

@router.post("/undo/{history_id}")
def undo_delete(
    history_id: str,
    db: Session = Depends(get_db),
):
    """
    撤回删除操作
    恢复被软删除的内容块及其子块
    """
    history = db.query(BlockHistory).filter(
        BlockHistory.id == history_id,
        BlockHistory.undone == False,
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="历史记录不存在或已撤回")
    
    if history.action != "delete":
        raise HTTPException(status_code=400, detail="仅支持撤回删除操作")
    
    # 恢复主块
    block = db.query(ContentBlock).filter(
        ContentBlock.id == history.block_id
    ).first()
    
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    if block.deleted_at is None:
        raise HTTPException(status_code=400, detail="内容块未被删除")
    
    # 恢复主块
    block.deleted_at = None
    
    # 恢复所有子块
    for child_snapshot in history.children_snapshots:
        child_id = child_snapshot.get("id")
        if child_id:
            child = db.query(ContentBlock).filter(
                ContentBlock.id == child_id
            ).first()
            if child:
                child.deleted_at = None
    
    # 标记历史已撤回
    history.undone = True
    
    # 重新排序同级（插入恢复的块）
    _reorder_siblings(block.project_id, block.parent_id, db)
    
    db.commit()
    
    return {
        "message": "撤回成功",
        "restored_block_id": block.id,
        "restored_children_count": len(history.children_snapshots),
    }


@router.get("/project/{project_id}/history")
def get_project_undo_history(
    project_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    获取项目的可撤回操作历史
    """
    histories = db.query(BlockHistory).filter(
        BlockHistory.project_id == project_id,
        BlockHistory.undone == False,
        BlockHistory.action == "delete",
    ).order_by(BlockHistory.created_at.desc()).limit(limit).all()
    
    return {
        "project_id": project_id,
        "undo_available": [
            {
                "history_id": h.id,
                "action": h.action,
                "block_name": h.block_snapshot.get("name", "未知"),
                "block_type": h.block_snapshot.get("block_type", "未知"),
                "children_count": len(h.children_snapshots),
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in histories
        ],
    }
