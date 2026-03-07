from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import ContentBlock, FieldTemplate, Project, ProjectField, ProjectStructureDraft
from scripts.migrate_pre_question_schema import migrate_pre_question_schema


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_migrate_pre_question_schema_normalizes_runtime_templates_and_drafts():
    session = make_session()
    try:
        project = Project(
            id="project-1",
            name="Migration Project",
            current_phase="intent",
            phase_order=["intent"],
            phase_status={"intent": "pending"},
        )
        session.add(project)
        session.flush()

        block = ContentBlock(
            id="block-1",
            project_id=project.id,
            name="内容块",
            block_type="field",
            pre_questions=["问题A"],
            pre_answers={"问题A": "答案A"},
        )
        field = ProjectField(
            id="field-1",
            project_id=project.id,
            phase="intent",
            name="旧字段",
            pre_questions=["问题B"],
            pre_answers={"问题B": "答案B"},
        )
        template = FieldTemplate(
            id="template-1",
            name="模板",
            fields=[{"name": "字段模板", "pre_questions": ["问题C"]}],
            root_nodes=[{
                "template_node_id": "node-1",
                "name": "模板块",
                "block_type": "field",
                "pre_questions": ["问题D"],
                "pre_answers": {"问题D": "答案D"},
                "children": [],
            }],
        )
        draft = ProjectStructureDraft(
            id="draft-1",
            project_id=project.id,
            draft_type="auto_split",
            name="自动拆分",
            status="draft",
            last_validated_at=datetime.now(),
            draft_payload={
                "chunks": [{"chunk_id": "chunk-1", "title": "片段一", "content": "内容", "order_index": 0}],
                "plans": [{
                    "plan_id": "plan-1",
                    "name": "方案一",
                    "target_chunk_ids": ["chunk-1"],
                    "root_nodes": [{
                        "template_node_id": "draft-node-1",
                        "name": "草稿块",
                        "block_type": "field",
                        "pre_questions": ["问题E"],
                        "pre_answers": {"问题E": "答案E"},
                        "children": [],
                    }],
                }],
                "shared_root_nodes": [],
                "aggregate_root_nodes": [],
                "ui_state": {},
            },
        )
        session.add_all([block, field, template, draft])
        session.commit()

        stats = migrate_pre_question_schema(session, dry_run=False)

        session.refresh(block)
        session.refresh(field)
        session.refresh(template)
        session.refresh(draft)

        assert stats["content_blocks_changed"] == 1
        assert stats["project_fields_changed"] == 1
        assert stats["field_templates_changed"] == 1
        assert stats["drafts_changed"] == 1

        assert block.pre_questions[0]["question"] == "问题A"
        assert block.pre_questions[0]["required"] is False
        assert block.pre_answers == {block.pre_questions[0]["id"]: "答案A"}

        assert field.pre_questions[0]["question"] == "问题B"
        assert field.pre_answers == {field.pre_questions[0]["id"]: "答案B"}

        assert template.fields[0]["pre_questions"][0]["question"] == "问题C"
        assert template.root_nodes[0]["pre_questions"][0]["question"] == "问题D"
        assert template.root_nodes[0]["pre_answers"] == {
            template.root_nodes[0]["pre_questions"][0]["id"]: "答案D",
        }

        migrated_question = draft.draft_payload["plans"][0]["root_nodes"][0]["pre_questions"][0]
        assert migrated_question["question"] == "问题E"
        assert migrated_question["required"] is False
        assert draft.draft_payload["plans"][0]["root_nodes"][0]["pre_answers"] == {
            migrated_question["id"]: "答案E",
        }
    finally:
        session.close()
