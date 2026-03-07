from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, ProjectStructureDraft
from scripts.migrate_t16_auto_split_draft_payload import migrate_t16_auto_split_draft_payload


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_migrate_t16_auto_split_draft_payload_normalizes_and_validates():
    db = _make_session()
    try:
        project = Project(name="t16 migration project")
        db.add(project)
        db.flush()

        draft = ProjectStructureDraft(
            project_id=project.id,
            draft_type="auto_split",
            name="auto split draft",
            draft_payload={
                "chunks": [
                    {
                        "chunk_id": "c1",
                        "title": "chunk 1",
                        "content": "demo",
                        "order_index": 0,
                    }
                ],
                "plans": [
                    {
                        "plan_id": "p1",
                        "name": "plan 1",
                        "target_chunk_ids": ["c1"],
                        "root_nodes": [
                            {
                                "template_node_id": "n1",
                                "name": "legacy phase node",
                                "block_type": "phase",
                                "guidance_input": "legacy",
                                "children": [
                                    {
                                        "template_node_id": "n2",
                                        "name": "legacy proposal node",
                                        "block_type": "proposal",
                                        "guidance_output": "legacy",
                                        "children": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "shared_root_nodes": [],
                "aggregate_root_nodes": [],
                "ui_state": {},
            },
        )
        db.add(draft)
        db.commit()

        stats = migrate_t16_auto_split_draft_payload(db, dry_run=False)
        assert stats["drafts_total"] == 1
        assert stats["drafts_changed"] == 1
        assert stats["validate_passed"] == 1
        assert stats["validate_failed"] == 0

        migrated = db.query(ProjectStructureDraft).filter(ProjectStructureDraft.id == draft.id).first()
        assert migrated is not None
        node = migrated.draft_payload["plans"][0]["root_nodes"][0]
        child = node["children"][0]
        assert node["block_type"] == "group"
        assert child["block_type"] == "field"
        assert "guidance_input" not in node
        assert "guidance_output" not in child
        assert migrated.status == "validated"
        assert migrated.last_validated_at is not None
    finally:
        db.close()
