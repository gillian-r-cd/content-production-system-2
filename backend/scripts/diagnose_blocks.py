"""诊断块状态 - 检查为什么自动触发没有生效"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_session_maker
from core.models import ContentBlock, Project

db = get_session_maker()()

projects = db.query(Project).all()
for p in projects:
    print(f"Project: {p.name} (id={p.id})")
    print(f"  use_flexible_architecture: {p.use_flexible_architecture}")
    
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == p.id,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    print(f"  Blocks ({len(blocks)}):")
    for b in blocks:
        deps = b.depends_on or []
        pq = b.pre_questions or []
        pa = b.pre_answers or {}
        has_content = bool(b.content and b.content.strip())
        
        # Check if pre_answers are filled
        if pq:
            answers_filled = all(pa.get(q, "").strip() for q in pq)
            unanswered = [q for q in pq if not pa.get(q, "").strip()]
        else:
            answers_filled = True
            unanswered = []
        
        # Resolve dependency names
        blocks_by_id = {bb.id: bb for bb in blocks}
        dep_names = []
        for d in deps:
            dep_block = blocks_by_id.get(d)
            if dep_block:
                dep_has_content = bool(dep_block.content and dep_block.content.strip())
                dep_names.append(f"{dep_block.name}(content={dep_has_content}, status={dep_block.status})")
            else:
                dep_names.append(f"UNKNOWN({d})")
        
        print(f"    [{b.block_type}] {b.name}")
        print(f"      id: {b.id}")
        print(f"      status: {b.status}")
        print(f"      need_review: {b.need_review}")
        print(f"      has_content: {has_content}")
        print(f"      depends_on: {dep_names}")
        print(f"      pre_questions: {pq}")
        print(f"      pre_answers filled: {answers_filled}")
        if unanswered:
            print(f"      UNANSWERED: {unanswered}")
        
        # Auto-trigger eligibility
        eligible = (
            not b.need_review 
            and b.status in ("pending", "failed") 
            and has_content == False
        )
        print(f"      AUTO-TRIGGER eligible: {eligible}")
        if not eligible:
            reasons = []
            if b.need_review:
                reasons.append("need_review=True")
            if b.status not in ("pending", "failed"):
                reasons.append(f"status={b.status}")
            if has_content:
                reasons.append("already has content")
            print(f"      BLOCKED BY: {', '.join(reasons)}")
        print()

db.close()


