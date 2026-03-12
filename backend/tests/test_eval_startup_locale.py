# backend/tests/test_eval_startup_locale.py
# 功能: 守卫启动自愈流程不会把 ja-JP 的 Eval 模板和锚点块重新中文化
# 主要测试: 模板同步、模板清理、Eval 锚点块去重命名
# 数据结构:
#   - 内存数据库中的 FieldTemplate / Project / ContentBlock
#   - monkeypatch 后的 `core.database.get_session_maker`

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main as backend_main
from core.database import Base
from core.models import ContentBlock, FieldTemplate, Grader, Project, Simulator, generate_uuid
from core.models.field_template import EVAL_TEMPLATE_V2_NAME


EVAL_TEMPLATE_HANDLERS = [
    {"name": "persona", "special_handler": "eval_persona_setup"},
    {"name": "task", "special_handler": "eval_task_config"},
    {"name": "report", "special_handler": "eval_report"},
]


@pytest.fixture
def startup_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("core.database.get_session_maker", lambda: TestingSessionLocal)
    return TestingSessionLocal


def test_sync_eval_template_on_startup_keeps_ja_variant(startup_session_factory):
    session = startup_session_factory()
    session.add(
        FieldTemplate(
            id=generate_uuid(),
            stable_key="eval_template_v2",
            locale="ja-JP",
            name="総合評価テンプレート",
            description="ja description",
            category="評価",
            fields=EVAL_TEMPLATE_HANDLERS,
        )
    )
    session.commit()
    session.close()

    backend_main._sync_eval_template_on_startup()

    check = startup_session_factory()
    templates = (
        check.query(FieldTemplate)
        .filter(FieldTemplate.stable_key == "eval_template_v2")
        .order_by(FieldTemplate.locale.asc())
        .all()
    )
    assert {template.locale for template in templates} == {"ja-JP", "zh-CN"}
    ja_template = next(template for template in templates if template.locale == "ja-JP")
    zh_template = next(template for template in templates if template.locale == "zh-CN")
    assert ja_template.name == "総合評価テンプレート"
    assert zh_template.name == EVAL_TEMPLATE_V2_NAME
    check.close()


def test_cleanup_legacy_eval_templates_keeps_localized_eval_variants(startup_session_factory):
    session = startup_session_factory()
    session.add_all(
        [
            FieldTemplate(
                id=generate_uuid(),
                stable_key="eval_template_v2",
                locale="zh-CN",
                name=EVAL_TEMPLATE_V2_NAME,
                description="zh",
                category="评估",
                fields=EVAL_TEMPLATE_HANDLERS,
            ),
            FieldTemplate(
                id=generate_uuid(),
                stable_key="eval_template_v2",
                locale="ja-JP",
                name="総合評価テンプレート",
                description="ja",
                category="評価",
                fields=EVAL_TEMPLATE_HANDLERS,
            ),
            FieldTemplate(
                id=generate_uuid(),
                stable_key="legacy_eval_template",
                locale="zh-CN",
                name="旧评估模板",
                description="legacy",
                category="评估",
                fields=EVAL_TEMPLATE_HANDLERS,
            ),
        ]
    )
    session.commit()
    session.close()

    backend_main._cleanup_legacy_eval_templates_on_startup()

    check = startup_session_factory()
    templates = check.query(FieldTemplate).order_by(FieldTemplate.locale.asc(), FieldTemplate.name.asc()).all()
    assert len(templates) == 2
    assert {template.locale for template in templates} == {"ja-JP", "zh-CN"}
    assert all(template.stable_key == "eval_template_v2" for template in templates)
    check.close()


def test_dedupe_eval_anchor_blocks_uses_project_locale_names(startup_session_factory):
    session = startup_session_factory()
    project_zh = Project(id=generate_uuid(), name="ZH Project", locale="zh-CN")
    project_ja = Project(id=generate_uuid(), name="JA Project", locale="ja-JP")
    session.add_all([project_zh, project_ja])
    session.flush()
    project_zh_id = project_zh.id
    project_ja_id = project_ja.id

    session.add_all(
        [
            ContentBlock(
                id=generate_uuid(),
                project_id=project_zh.id,
                parent_id=None,
                name="ペルソナ設定",
                block_type="field",
                content="{}",
                special_handler="eval_persona_setup",
                status="completed",
                order_index=1,
            ),
            ContentBlock(
                id=generate_uuid(),
                project_id=project_ja.id,
                parent_id=None,
                name="人物画像设置",
                block_type="field",
                content="{}",
                special_handler="eval_persona_setup",
                status="completed",
                order_index=1,
            ),
            ContentBlock(
                id=generate_uuid(),
                project_id=project_ja.id,
                parent_id=None,
                name="评估任务配置",
                block_type="field",
                content="{}",
                special_handler="eval_task_config",
                status="completed",
                order_index=2,
            ),
            ContentBlock(
                id=generate_uuid(),
                project_id=project_ja.id,
                parent_id=None,
                name="评估报告",
                block_type="field",
                content="{}",
                special_handler="eval_report",
                status="completed",
                order_index=3,
            ),
        ]
    )
    session.commit()
    session.close()

    backend_main._dedupe_eval_anchor_blocks_on_startup()

    check = startup_session_factory()
    blocks = check.query(ContentBlock).order_by(ContentBlock.project_id.asc(), ContentBlock.order_index.asc()).all()
    by_project_handler = {(block.project_id, block.special_handler): block.name for block in blocks}
    assert by_project_handler[(project_zh_id, "eval_persona_setup")] == "人物画像设置"
    assert by_project_handler[(project_ja_id, "eval_persona_setup")] == "ペルソナ設定"
    assert by_project_handler[(project_ja_id, "eval_task_config")] == "評価タスク設定"
    assert by_project_handler[(project_ja_id, "eval_report")] == "評価レポート"
    check.close()


def test_sync_eval_presets_on_startup_populates_both_locales(startup_session_factory):
    backend_main._sync_eval_presets_on_startup()

    check = startup_session_factory()
    graders = check.query(Grader).filter(Grader.is_preset.is_(True)).all()
    simulators = check.query(Simulator).filter(Simulator.is_preset.is_(True)).all()

    assert {"zh-CN", "ja-JP"} <= {grader.locale for grader in graders}
    assert {"zh-CN", "ja-JP"} <= {simulator.locale for simulator in simulators}
    assert any(grader.stable_key == "content_quality" and grader.locale == "ja-JP" for grader in graders)
    assert any(simulator.stable_key == "assessment_direct" and simulator.locale == "ja-JP" for simulator in simulators)
    check.close()
