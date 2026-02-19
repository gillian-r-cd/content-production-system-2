from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, EvalRun, EvalTask, EvalTrial, EvalTaskV2, EvalTrialResultV2, generate_uuid
from scripts.migrate_legacy_eval_to_v2 import migrate_legacy_eval_to_v2


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_migrate_legacy_eval_to_v2_idempotent():
    db = _make_session()
    try:
        project = Project(id=generate_uuid(), name="legacy project")
        db.add(project)
        db.flush()

        run = EvalRun(id=generate_uuid(), project_id=project.id, name="旧运行")
        db.add(run)
        db.flush()

        task = EvalTask(
            id=generate_uuid(),
            eval_run_id=run.id,
            name="旧任务",
            simulator_type="consumer",
            interaction_mode="dialogue",
            target_block_ids=[],
            order_index=0,
        )
        db.add(task)
        db.flush()

        tr1 = EvalTrial(
            id=generate_uuid(),
            eval_run_id=run.id,
            eval_task_id=task.id,
            role="consumer",
            interaction_mode="dialogue",
            nodes=[{"role": "user", "content": "Q1"}],
            result={"scores": {"需求匹配度": 7}},
            grader_outputs=[{"grader_name": "g1"}],
            llm_calls=[{"step": "s1"}],
            overall_score=7.0,
            status="completed",
        )
        tr2 = EvalTrial(
            id=generate_uuid(),
            eval_run_id=run.id,
            eval_task_id=task.id,
            role="consumer",
            interaction_mode="dialogue",
            nodes=[{"role": "user", "content": "Q2"}],
            result={"scores": {"需求匹配度": 8}},
            grader_outputs=[{"grader_name": "g1"}],
            llm_calls=[{"step": "s2"}],
            overall_score=8.0,
            status="completed",
        )
        db.add(tr1)
        db.add(tr2)
        db.commit()

        first = migrate_legacy_eval_to_v2(db, dry_run=False)
        assert first["tasks_created"] == 1
        assert first["configs_created"] == 1
        assert first["results_created"] == 2

        v2_tasks = db.query(EvalTaskV2).all()
        v2_results = db.query(EvalTrialResultV2).all()
        assert len(v2_tasks) == 1
        assert len(v2_results) == 2
        assert v2_tasks[0].latest_batch_id.startswith("legacy-")
        assert isinstance(v2_tasks[0].latest_overall, float)

        second = migrate_legacy_eval_to_v2(db, dry_run=False)
        assert second["tasks_created"] == 0
        assert second["results_created"] == 0
        assert second["results_skipped_existing"] >= 2

        assert db.query(EvalTaskV2).count() == 1
        assert db.query(EvalTrialResultV2).count() == 2
    finally:
        db.close()


