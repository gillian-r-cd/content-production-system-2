# backend/tests/test_agent_autonomy.py
# 功能: 测试Agent自主权设置的有效性
# 验证: 设置为需要确认时,推进阶段应该等待; 设置为自动时应该直接推进

"""
Agent自主权测试
验证autonomy设置是否正确影响阶段推进逻辑
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base
from core.models import Project, generate_uuid


# 内存数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


class TestAgentAutonomy:
    """Agent自主权测试"""

    def test_default_autonomy_all_phases_need_confirm(self, db_session):
        """默认情况下所有阶段都需要确认"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            # 使用默认autonomy设置
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        # 验证默认设置: 所有阶段需要确认
        for phase in project.phase_order:
            assert project.needs_human_confirm(phase) == True, f"Phase {phase} should need confirm by default"

    def test_autonomy_set_auto_for_specific_phase(self, db_session):
        """设置特定阶段为自动（不需要确认）"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            agent_autonomy={
                "intent": False,  # 不需要确认
                "research": True,  # 需要确认
                "design_inner": False,
                "produce_inner": True,
                "design_outer": False,
                "produce_outer": True,
                "simulate": False,
                "evaluate": True,
            },
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        # 验证各阶段设置
        assert project.needs_human_confirm("intent") == False
        assert project.needs_human_confirm("research") == True
        assert project.needs_human_confirm("design_inner") == False
        assert project.needs_human_confirm("produce_inner") == True

    def test_autonomy_missing_phase_defaults_to_confirm(self, db_session):
        """未设置的阶段默认需要确认"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            agent_autonomy={
                "intent": False,
                # 其他阶段未设置
            },
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        # intent明确设置为False
        assert project.needs_human_confirm("intent") == False
        # research未设置，应该默认True
        assert project.needs_human_confirm("research") == True

    def test_phase_order_respected(self, db_session):
        """验证阶段顺序被正确处理"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            phase_order=[
                "intent",
                "research",
                "design_outer",  # 改变顺序
                "produce_outer",
                "design_inner",
                "produce_inner",
                "simulate",
                "evaluate",
            ],
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)

        # 验证phase_order被保存
        assert project.phase_order[2] == "design_outer"
        assert project.phase_order[4] == "design_inner"

        # 验证get_next_phase使用自定义顺序
        project.current_phase = "research"
        assert project.get_next_phase() == "design_outer"

    def test_update_autonomy_after_creation(self, db_session):
        """项目创建后可以更新自主权设置"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()

        # 初始：需要确认
        assert project.needs_human_confirm("intent") == True

        # 更新设置
        project.agent_autonomy = {"intent": False, "research": False}
        db_session.commit()
        db_session.refresh(project)

        # 更新后：不需要确认
        assert project.needs_human_confirm("intent") == False
        assert project.needs_human_confirm("research") == False


class TestPhaseAdvancement:
    """阶段推进测试"""

    def test_advance_phase_updates_status(self, db_session):
        """推进阶段应该更新状态"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="intent",
            phase_status={
                "intent": "in_progress",
                "research": "pending",
            },
        )
        db_session.add(project)
        db_session.commit()

        # 模拟推进 - 需要替换整个dict来触发SQLAlchemy更新
        new_status = dict(project.phase_status)
        new_status["intent"] = "completed"
        new_status["research"] = "in_progress"
        project.phase_status = new_status
        project.current_phase = "research"
        db_session.commit()
        db_session.refresh(project)

        assert project.current_phase == "research"
        assert project.phase_status["intent"] == "completed"
        assert project.phase_status["research"] == "in_progress"

    def test_get_next_phase_at_end(self, db_session):
        """最后一个阶段时get_next_phase返回None"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="evaluate",
        )
        db_session.add(project)
        db_session.commit()

        assert project.get_next_phase() is None

