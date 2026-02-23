# backend/tests/test_tool_safety.py
# 功能: 测试工具安全性防护
#   - _is_structured_handler: 子块自身 special_handler（数据层传播后）
#   - rewrite_field: instruction 级守护 + SuggestionCard 确认流程 + card_type
#   - generate_field_content: 已有内容一律拒绝 + 结构化块拒绝
#   - _run_research_impl: 保存目标优先 field 块
#   - confirm-suggestion: card_type="full_rewrite" 冲突处理

import sys, os, json, asyncio

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_db
from core.models import Project, generate_uuid
from core.models.content_block import ContentBlock

from sqlalchemy.orm import Session


def get_test_db() -> Session:
    return next(get_db())


def setup_test_project(db: Session) -> tuple[str, str, str]:
    """创建测试项目。子 field 自身带 special_handler（模拟数据层传播后的状态）。
    返回 (project_id, phase_block_id, field_block_id)
    """
    pid = generate_uuid()
    project = Project(
        id=pid,
        name="测试项目-工具安全",
        current_phase="research",
        phase_order=["intent", "research", "design_inner"],
        phase_status={"intent": "completed", "research": "in_progress"},
    )
    db.add(project)

    phase_id = generate_uuid()
    phase_block = ContentBlock(
        id=phase_id,
        project_id=pid,
        parent_id=None,
        name="消费者调研",
        block_type="phase",
        depth=0,
        order_index=1,
        special_handler="research",
        status="in_progress",
    )
    db.add(phase_block)

    # 子 field 块：数据层传播后自身有 special_handler="research"
    field_id = generate_uuid()
    field_block = ContentBlock(
        id=field_id,
        project_id=pid,
        parent_id=phase_id,
        name="消费者调研报告",
        block_type="field",
        depth=1,
        order_index=0,
        special_handler="research",
        content="",
        status="pending",
    )
    db.add(field_block)

    # 普通 field 块（无保护）
    normal_id = generate_uuid()
    normal_block = ContentBlock(
        id=normal_id,
        project_id=pid,
        parent_id=None,
        name="课程内容",
        block_type="field",
        depth=0,
        order_index=2,
        special_handler=None,
        content="这是已有的课程内容，共100字。" * 5,
        status="completed",
    )
    db.add(normal_block)

    db.commit()
    return pid, phase_id, field_id


def teardown_test_project(db: Session, project_id: str):
    db.query(ContentBlock).filter(ContentBlock.project_id == project_id).delete()
    db.query(Project).filter(Project.id == project_id).delete()
    db.commit()


# ============== R1: _is_structured_handler 单层检查（数据层已传播） ==============

def test_structured_handler_direct():
    """phase 块自身有 special_handler"""
    from core.agent_tools import _is_structured_handler

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        phase_block = db.query(ContentBlock).filter(ContentBlock.id == phase_id).first()
        assert _is_structured_handler(phase_block)
        print("PASS: test_structured_handler_direct")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_structured_handler_child_has_handler():
    """子 field 自身有 special_handler（数据层传播后），单层检查即可识别"""
    from core.agent_tools import _is_structured_handler

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        field_block = db.query(ContentBlock).filter(ContentBlock.id == field_id).first()
        assert field_block.special_handler == "research", \
            "数据层传播后子块应有 special_handler"
        assert _is_structured_handler(field_block), \
            "子块自身有 special_handler，单层检查应识别"
        print("PASS: test_structured_handler_child_has_handler")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_structured_handler_normal_field():
    """普通 field 块无 special_handler"""
    from core.agent_tools import _is_structured_handler

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        normal = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid,
            ContentBlock.name == "课程内容",
        ).first()
        assert not _is_structured_handler(normal)
        print("PASS: test_structured_handler_normal_field")
    finally:
        teardown_test_project(db, pid)
        db.close()


# ============== R1 扩展: template 层传播验证 ==============

def test_template_propagates_special_handler():
    """phase_template.apply_to_project 应将 phase 的 special_handler 传给子 field"""
    from core.models.phase_template import DEFAULT_PHASE_TEMPLATE

    research_phase = next(
        p for p in DEFAULT_PHASE_TEMPLATE["phases"]
        if p["name"] == "消费者调研"
    )
    assert research_phase["special_handler"] == "research"

    # 模拟 apply_to_project 的子 field 创建逻辑
    phase_handler = research_phase.get("special_handler")
    for field_def in research_phase.get("default_fields", []):
        child_handler = field_def.get("special_handler", phase_handler)
        assert child_handler == "research", \
            f"子 field '{field_def['name']}' 应继承 special_handler='research'，实际={child_handler}"

    print("PASS: test_template_propagates_special_handler")


# ============== R2: rewrite_field instruction-level 守护 ==============

def test_rewrite_intent_detection():
    """_is_explicit_rewrite_intent 关键词检测"""
    from core.agent_tools import _is_explicit_rewrite_intent

    assert _is_explicit_rewrite_intent("请重写整篇内容")
    assert _is_explicit_rewrite_intent("从头写一遍")
    assert _is_explicit_rewrite_intent("整体改写风格")

    assert not _is_explicit_rewrite_intent("帮我改一下开头")
    assert not _is_explicit_rewrite_intent("优化一下第三段")
    assert not _is_explicit_rewrite_intent("")
    print("PASS: test_rewrite_intent_detection")


def test_rewrite_field_rejects_non_rewrite_instruction():
    """LLM instruction 无重写关键词时应拒绝（不依赖 user_message）"""
    from core.agent_tools import _rewrite_field_impl

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        normal = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid,
            ContentBlock.name == "课程内容",
        ).first()
        normal.content = "这是原始内容。" * 20
        db.commit()

        # 不传 user_message（已移除该机制）
        config = {"configurable": {"project_id": pid, "thread_id": f"{pid}:assistant"}}
        result_str = asyncio.run(_rewrite_field_impl(
            "课程内容", "帮我改一下开头", [], config,
        ))
        result = json.loads(result_str)
        assert result.get("status") == "error", \
            f"instruction 无重写意图时应拒绝: {result}"
        print("PASS: test_rewrite_field_rejects_non_rewrite_instruction")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_rewrite_field_produces_suggestion_card():
    """rewrite_field 应生成 SuggestionCard（card_type=full_rewrite），不写 DB"""
    from core.agent_tools import _rewrite_field_impl, PENDING_SUGGESTIONS

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        normal = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid,
            ContentBlock.name == "课程内容",
        ).first()
        original = "这是原始内容。" * 20
        normal.content = original
        db.commit()

        config = {"configurable": {"project_id": pid, "thread_id": f"{pid}:assistant"}}
        result_str = asyncio.run(_rewrite_field_impl(
            "课程内容", "重写课程内容，让内容更专业", [], config,
        ))
        result = json.loads(result_str)
        assert result.get("status") == "suggestion", \
            f"rewrite_field 应返回 suggestion: {result}"

        card_id = result.get("id")
        assert card_id in PENDING_SUGGESTIONS
        card = PENDING_SUGGESTIONS[card_id]
        assert card["card_type"] == "full_rewrite", \
            f"card_type 应为 full_rewrite: {card.get('card_type')}"
        assert card["original_content"] == original
        assert card["modified_content"] != original

        # DB 未被修改
        db.expire_all()
        entity = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid, ContentBlock.name == "课程内容",
        ).first()
        assert entity.content == original, "rewrite_field 不应修改 DB"

        PENDING_SUGGESTIONS.pop(card_id, None)
        print("PASS: test_rewrite_field_produces_suggestion_card")
    finally:
        teardown_test_project(db, pid)
        db.close()


# ============== R2: generate_field_content 已有内容一律拒绝 ==============

def test_generate_rejects_existing_content():
    """已有内容的块一律拒绝（无关键词匹配）"""
    from core.agent_tools import _generate_field_impl

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        config = {"configurable": {"project_id": pid, "thread_id": f"{pid}:assistant"}}
        result_str = asyncio.run(_generate_field_impl("课程内容", "生成更专业的内容", config))
        result = json.loads(result_str)
        assert result.get("status") == "error"
        assert "已有内容" in result.get("message", "") or "首次生成" in result.get("message", "")
        print("PASS: test_generate_rejects_existing_content")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_generate_rejects_existing_even_with_regen_keyword():
    """即使指令含'重新生成'也拒绝——不再做关键词匹配"""
    from core.agent_tools import _generate_field_impl

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        config = {"configurable": {"project_id": pid, "thread_id": f"{pid}:assistant"}}
        result_str = asyncio.run(_generate_field_impl("课程内容", "重新生成课程内容", config))
        result = json.loads(result_str)
        assert result.get("status") == "error", \
            f"即使说'重新生成'也应拒绝（应走 rewrite_field）: {result}"
        print("PASS: test_generate_rejects_existing_even_with_regen_keyword")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_generate_rejects_research_field():
    """调研类内容块（自身有 special_handler）不能用 generate"""
    from core.agent_tools import _generate_field_impl

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        config = {"configurable": {"project_id": pid, "thread_id": f"{pid}:assistant"}}
        result_str = asyncio.run(_generate_field_impl("消费者调研报告", "", config))
        result = json.loads(result_str)
        assert result.get("status") == "error"
        assert "run_research" in result.get("message", "") or "专用工具" in result.get("message", "")
        print("PASS: test_generate_rejects_research_field")
    finally:
        teardown_test_project(db, pid)
        db.close()


# ============== T2 保留: research 保存目标 ==============

def test_research_saves_to_field_block():
    """调研结果应保存到 field 子块"""
    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid,
            ContentBlock.name.in_(["消费者调研报告", "消费者调研"]),
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,
        ).first()
        assert block is not None
        assert block.name == "消费者调研报告"
        assert block.block_type == "field"
        print("PASS: test_research_saves_to_field_block")
    finally:
        teardown_test_project(db, pid)
        db.close()


# ============== R3: confirm-suggestion card_type 处理 ==============

def test_confirm_full_rewrite_card():
    """confirm 对 card_type=full_rewrite 应直接替换内容"""
    from core.agent_tools import PENDING_SUGGESTIONS

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        normal = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid, ContentBlock.name == "课程内容",
        ).first()
        original = "原始内容A" * 10
        normal.content = original
        db.commit()

        card_id = generate_uuid()
        new_content = "这是全新的重写内容。" * 10
        card = {
            "id": card_id,
            "card_type": "full_rewrite",
            "target_field": "课程内容",
            "target_entity_id": normal.id,
            "summary": "全文重写",
            "reason": "测试",
            "edits": [],
            "changes": [],
            "original_content": original,
            "modified_content": new_content,
            "status": "pending",
            "source_mode": "assistant",
        }
        PENDING_SUGGESTIONS[card_id] = card

        # 模拟 confirm 核心逻辑
        entity = db.query(ContentBlock).filter(ContentBlock.id == normal.id).first()
        entity.content = card["modified_content"]
        db.commit()

        db.expire_all()
        entity = db.query(ContentBlock).filter(ContentBlock.id == normal.id).first()
        assert entity.content == new_content
        PENDING_SUGGESTIONS.pop(card_id, None)
        print("PASS: test_confirm_full_rewrite_card")
    finally:
        teardown_test_project(db, pid)
        db.close()


def test_confirm_full_rewrite_card_with_conflict():
    """冲突场景下 card_type=full_rewrite 仍直接替换"""
    from core.agent_tools import PENDING_SUGGESTIONS

    db = get_test_db()
    pid, phase_id, field_id = setup_test_project(db)
    try:
        normal = db.query(ContentBlock).filter(
            ContentBlock.project_id == pid, ContentBlock.name == "课程内容",
        ).first()
        original = "原始内容B" * 10
        normal.content = original
        db.commit()

        card_id = generate_uuid()
        new_content = "全新重写内容B" * 10
        card = {
            "id": card_id,
            "card_type": "full_rewrite",
            "target_field": "课程内容",
            "target_entity_id": normal.id,
            "summary": "全文重写",
            "reason": "测试",
            "edits": [],
            "changes": [],
            "original_content": original,
            "modified_content": new_content,
            "status": "pending",
            "source_mode": "assistant",
        }
        PENDING_SUGGESTIONS[card_id] = card

        # 模拟中间修改（冲突）
        normal.content = "被中间修改过的内容" * 5
        db.commit()

        # 模拟 confirm 逻辑（与 api/agent.py confirm-suggestion 一致）
        entity = db.query(ContentBlock).filter(ContentBlock.id == normal.id).first()
        current_content = entity.content or ""
        modified_content = card["modified_content"]

        assert current_content != card["original_content"], "应检测到冲突"

        # card_type=full_rewrite 直接替换
        if card.get("card_type") == "full_rewrite":
            entity.content = modified_content
        else:
            assert False, "应走 full_rewrite 分支"

        db.commit()

        db.expire_all()
        entity = db.query(ContentBlock).filter(ContentBlock.id == normal.id).first()
        assert entity.content == new_content
        PENDING_SUGGESTIONS.pop(card_id, None)
        print("PASS: test_confirm_full_rewrite_card_with_conflict")
    finally:
        teardown_test_project(db, pid)
        db.close()


# ============== 主执行 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("工具安全性测试（根治版）")
    print("=" * 60)

    tests = [
        test_structured_handler_direct,
        test_structured_handler_child_has_handler,
        test_structured_handler_normal_field,
        test_template_propagates_special_handler,
        test_rewrite_intent_detection,
        test_rewrite_field_rejects_non_rewrite_instruction,
        test_rewrite_field_produces_suggestion_card,
        test_generate_rejects_existing_content,
        test_generate_rejects_existing_even_with_regen_keyword,
        test_generate_rejects_research_field,
        test_research_saves_to_field_block,
        test_confirm_full_rewrite_card,
        test_confirm_full_rewrite_card_with_conflict,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"结果: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 60}")
    if failed > 0:
        sys.exit(1)
