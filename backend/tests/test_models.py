# backend/tests/test_models.py
# 功能: 测试数据模型的CRUD操作
# 主要函数: test_*

"""
数据模型测试
验证所有模型的增删改查操作
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import (
    CreatorProfile,
    Project,
    FieldTemplate,
    ProjectField,
    Channel,
    Simulator,
    SimulationRecord,
    GenerationLog,
)


@pytest.fixture
def db_session():
    """创建测试用的内存数据库"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


class TestCreatorProfile:
    """测试创作者特质模型"""
    
    def test_create(self, db_session):
        profile = CreatorProfile(
            name="测试特质",
            description="测试描述",
            traits={"tone": "专业"}
        )
        db_session.add(profile)
        db_session.commit()
        
        assert profile.id is not None
        assert profile.name == "测试特质"
        assert profile.traits["tone"] == "专业"
    
    def test_to_prompt_context(self, db_session):
        profile = CreatorProfile(
            name="专业型",
            traits={"tone": "严谨", "taboos": ["夸大", "虚假"]}
        )
        context = profile.to_prompt_context()
        
        assert "专业型" in context
        assert "严谨" in context
        assert "夸大" in context


class TestProject:
    """测试项目模型"""
    
    def test_create_with_creator(self, db_session):
        profile = CreatorProfile(name="测试特质")
        db_session.add(profile)
        db_session.commit()
        
        project = Project(
            name="测试项目",
            creator_profile_id=profile.id
        )
        db_session.add(project)
        db_session.commit()
        
        assert project.id is not None
        assert project.version == 1
        assert project.current_phase == "intent"
        assert len(project.phase_order) == 7
    
    def test_phase_navigation(self, db_session):
        project = Project(name="测试项目")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        assert project.get_phase_index("intent") == 0
        assert project.get_next_phase() == "research"
        
        project.current_phase = "evaluate"
        assert project.get_next_phase() is None
    


class TestFieldTemplate:
    """测试字段模板模型"""
    
    def test_create(self, db_session):
        template = FieldTemplate(
            name="测试模板",
            category="课程",
            fields=[
                {"name": "目标", "type": "text", "depends_on": []},
                {"name": "大纲", "type": "structured", "depends_on": ["目标"]},
            ]
        )
        db_session.add(template)
        db_session.commit()
        
        assert template.id is not None
        assert template.get_field_names() == ["目标", "大纲"]
        assert template.get_field_by_name("目标")["type"] == "text"
    
    def test_validate_dependencies(self, db_session):
        template = FieldTemplate(
            name="测试模板",
            fields=[
                {"name": "A", "depends_on": ["不存在的字段"]},
            ]
        )
        
        errors = template.validate_dependencies()
        assert len(errors) > 0
        assert "不存在" in errors[0]


class TestProjectField:
    """测试项目字段模型"""
    
    def test_create(self, db_session):
        project = Project(name="测试项目")
        db_session.add(project)
        db_session.commit()
        
        field = ProjectField(
            project_id=project.id,
            phase="inner",
            name="测试字段",
            content="测试内容"
        )
        db_session.add(field)
        db_session.commit()
        
        assert field.id is not None
        assert field.status == "pending"
    
    def test_dependency_check(self, db_session):
        field = ProjectField(
            project_id="test",
            phase="inner",
            name="字段B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"}
        )
        
        assert field.can_generate(set()) is False
        assert field.can_generate({"field_a"}) is True
        
        # 测试 any 类型
        field.dependencies["dependency_type"] = "any"
        field.dependencies["depends_on"] = ["field_a", "field_b"]
        
        assert field.can_generate({"field_a"}) is True
        assert field.can_generate(set()) is False


class TestSimulator:
    """测试模拟器模型"""
    
    def test_create(self, db_session):
        simulator = Simulator(
            name="对话模拟器",
            interaction_type="dialogue"
        )
        db_session.add(simulator)
        db_session.commit()
        
        assert simulator.id is not None
    
    def test_default_template(self):
        template = Simulator.get_default_template("dialogue")
        assert "{persona}" in template
        assert "对话" in template


class TestGenerationLog:
    """测试生成日志模型"""
    
    def test_cost_calculation(self):
        # GPT-4o: $2.50/1M input, $10/1M output
        cost = GenerationLog.calculate_cost("gpt-4o", 1000, 500)
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
        assert abs(cost - expected) < 0.0001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

