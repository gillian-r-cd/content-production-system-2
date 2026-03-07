from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import ContentBlock, FieldTemplate, PhaseTemplate, Project
from scripts.migrate_t2_phase_proposal_guidance import migrate_t2_phase_proposal_guidance


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_migrate_t2_phase_proposal_guidance_idempotent():
    db = _make_session()
    try:
        project = Project(name="t2 migration project")
        db.add(project)
        db.flush()

        block = ContentBlock(
            project_id=project.id,
            name="legacy phase block",
            block_type="phase",
            guidance_input="legacy in",
            guidance_output="legacy out",
        )
        db.add(block)

        template = FieldTemplate(
            name="field template",
            fields=[{"name": "f1", "block_type": "proposal", "guidance_output": "x"}],
            root_nodes=[
                {
                    "template_node_id": "n1",
                    "name": "legacy group",
                    "block_type": "phase",
                    "guidance_input": "x",
                    "children": [],
                }
            ],
        )
        db.add(template)

        phase_template = PhaseTemplate(
            name="phase template",
            phases=[
                {
                    "name": "legacy phase",
                    "block_type": "phase",
                    "guidance_input": "x",
                    "default_fields": [
                        {"name": "df", "block_type": "proposal", "guidance_output": "x"}
                    ],
                }
            ],
        )
        db.add(phase_template)
        db.commit()

        first = migrate_t2_phase_proposal_guidance(db, dry_run=False)
        assert first["content_blocks_changed"] == 1
        assert first["field_templates_changed"] == 1
        assert first["phase_templates_changed"] == 1

        migrated_block = db.query(ContentBlock).filter(ContentBlock.id == block.id).first()
        assert migrated_block is not None
        assert migrated_block.block_type == "group"
        assert migrated_block.guidance_input == ""
        assert migrated_block.guidance_output == ""

        migrated_template = db.query(FieldTemplate).filter(FieldTemplate.id == template.id).first()
        assert migrated_template is not None
        assert migrated_template.root_nodes[0]["block_type"] == "group"
        assert "guidance_input" not in migrated_template.root_nodes[0]
        assert migrated_template.fields[0]["block_type"] == "field"
        assert "guidance_output" not in migrated_template.fields[0]

        migrated_phase_template = db.query(PhaseTemplate).filter(PhaseTemplate.id == phase_template.id).first()
        assert migrated_phase_template is not None
        assert migrated_phase_template.phases[0]["block_type"] == "group"
        assert migrated_phase_template.phases[0]["default_fields"][0]["block_type"] == "field"
        assert "guidance_input" not in migrated_phase_template.phases[0]

        second = migrate_t2_phase_proposal_guidance(db, dry_run=False)
        assert second["content_blocks_changed"] == 0
        assert second["field_templates_changed"] == 0
        assert second["phase_templates_changed"] == 0
    finally:
        db.close()
