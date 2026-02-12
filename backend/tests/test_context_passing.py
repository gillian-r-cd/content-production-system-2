# backend/tests/test_context_passing.py
# 功能: 测试上下文传递的完整性
# 验证: 依赖内容注入、pre-answers、系统提示词、字段AI提示词

"""
上下文传递完整性测试

测试场景:
1. 依赖内容注入: 依赖字段的content正确注入到提示词
2. Pre-answers注入: 用户回答的预问题注入到提示词
3. 系统提示词: 各阶段系统提示词正确应用
4. 字段AI提示词: 字段特定的AI指导词正确应用
5. 渠道上下文: 外延生产时渠道信息正确注入
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import (
    Project, 
    ProjectField, 
    Channel,
    CreatorProfile,
    generate_uuid,
)
from core.prompt_engine import prompt_engine, GoldenContext, PromptContext


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


class TestDependencyContentInjection:
    """依赖内容注入测试"""
    
    def test_single_dependency_content_injection(self, db_session):
        """测试单个依赖字段内容注入"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        # 创建依赖字段
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Introduction",
            content="Welcome to the AI course. This course covers...",
            status="completed",
        )
        db_session.add(field_a)
        db_session.commit()
        
        # 构建上下文
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            dependent_fields=[field_a],
        )
        
        system_prompt = context.to_system_prompt()
        
        # 验证依赖内容被注入
        assert "Introduction" in system_prompt
        assert "Welcome to the AI course" in system_prompt
    
    def test_multiple_dependencies_ordered_injection(self, db_session):
        """测试多个依赖字段按顺序注入"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        fields = [
            ProjectField(
                id=generate_uuid(),
                project_id=project.id,
                phase="produce_inner",
                name="Chapter 1",
                content="Content of chapter 1",
                status="completed",
            ),
            ProjectField(
                id=generate_uuid(),
                project_id=project.id,
                phase="produce_inner",
                name="Chapter 2",
                content="Content of chapter 2",
                status="completed",
            ),
        ]
        for f in fields:
            db_session.add(f)
        db_session.commit()
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            dependent_fields=fields,
        )
        
        system_prompt = context.to_system_prompt()
        
        assert "Chapter 1" in system_prompt
        assert "Chapter 2" in system_prompt
        assert "Content of chapter 1" in system_prompt
        assert "Content of chapter 2" in system_prompt
    
    def test_dependency_context_structure(self, db_session):
        """测试依赖上下文结构正确"""
        field = ProjectField(
            id="test_id",
            project_id="test",
            phase="produce_inner",
            name="Test Field",
            content="Test content here",
        )
        
        fields_by_id = {"test_id": field}
        
        dependent_field = ProjectField(
            id="dependent_id",
            project_id="test",
            phase="produce_inner",
            name="Dependent Field",
            dependencies={"depends_on": ["test_id"], "dependency_type": "all"},
        )
        
        context = dependent_field.get_dependency_context(fields_by_id)
        
        # 验证格式
        assert "## Test Field" in context
        assert "Test content here" in context


class TestPreAnswersInjection:
    """Pre-answers注入测试"""
    
    def test_pre_answers_in_prompt(self, db_session):
        """测试预问题回答注入到提示词"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Course Goal",
            pre_questions=["Target audience?", "Main objective?"],
            pre_answers={
                "Target audience?": "Software developers",
                "Main objective?": "Learn AI basics",
            },
        )
        db_session.add(field)
        db_session.commit()
        
        context = PromptContext(
            golden_context=GoldenContext(),
            phase_context="Generate content",
        )
        
        full_prompt = prompt_engine.get_field_generation_prompt(field, context)
        
        # 验证预回答被注入
        assert "Target audience?" in full_prompt
        assert "Software developers" in full_prompt
        assert "Main objective?" in full_prompt
        assert "Learn AI basics" in full_prompt
    
    def test_empty_pre_answers_not_injected(self, db_session):
        """测试空预回答不注入"""
        field = ProjectField(
            id=generate_uuid(),
            project_id="test",
            phase="produce_inner",
            name="Test Field",
            pre_answers={},
        )
        
        context = PromptContext(
            golden_context=GoldenContext(),
        )
        
        full_prompt = prompt_engine.get_field_generation_prompt(field, context)
        
        # 空预回答不应该有"用户补充信息"部分
        assert "用户补充信息" not in full_prompt


class TestFieldAIPromptInjection:
    """字段AI提示词注入测试"""
    
    def test_custom_ai_prompt_injection(self, db_session):
        """测试自定义AI提示词注入"""
        field = ProjectField(
            id=generate_uuid(),
            project_id="test",
            phase="produce_inner",
            name="Marketing Copy",
            ai_prompt="Write persuasive marketing copy. Use active voice. Keep sentences short.",
        )
        
        context = PromptContext(
            golden_context=GoldenContext(),
            phase_context="Produce content",
        )
        
        full_prompt = prompt_engine.get_field_generation_prompt(field, context)
        
        # 验证AI提示词被注入
        assert "persuasive marketing copy" in full_prompt
        assert "active voice" in full_prompt
    
    def test_ai_prompt_combined_with_dependencies(self, db_session):
        """测试AI提示词与依赖上下文组合"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        
        dep_field = ProjectField(
            id="dep_id",
            project_id=project.id,
            phase="produce_inner",
            name="Brand Guidelines",
            content="Brand voice: friendly and professional",
        )
        
        target_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Social Media Post",
            ai_prompt="Create engaging social media content",
            dependencies={"depends_on": ["dep_id"], "dependency_type": "all"},
        )
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            dependent_fields=[dep_field],
        )
        
        full_prompt = prompt_engine.get_field_generation_prompt(target_field, context)
        
        # 验证依赖和AI指令都被注入
        assert "friendly and professional" in context.field_context
        assert "engaging social media content" in full_prompt


class TestChannelContextInjection:
    """渠道上下文注入测试"""
    
    def test_channel_context_in_outer_production(self, db_session):
        """测试外延生产时渠道信息注入"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        channel = Channel(
            id=generate_uuid(),
            name="Xiaohongshu",
            description="Young female users, lifestyle content",
            platform="social",
            constraints={"max_length": 1000, "format": "image_text", "style": "lifestyle"},
        )
        db_session.add(channel)
        db_session.commit()
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_outer",
            channel=channel,
        )
        
        system_prompt = context.to_system_prompt()
        
        # 验证渠道信息注入
        assert "Xiaohongshu" in system_prompt or "目标渠道" in system_prompt


class TestSystemPromptInjection:
    """系统提示词注入测试"""
    
    def test_phase_system_prompt_injection(self, db_session):
        """测试阶段系统提示词注入"""
        project = Project(id=generate_uuid(), name="Test Project")
        
        for phase in ["intent", "research", "design_inner", "produce_inner"]:
            context = prompt_engine.build_prompt_context(
                project=project,
                phase=phase,
            )
            
            # 验证阶段提示词不为空
            assert context.phase_context != "" or phase in ["simulate", "evaluate"]
    
    def test_custom_prompt_override(self, db_session):
        """测试自定义提示词覆盖"""
        project = Project(id=generate_uuid(), name="Test Project")
        
        custom_prompt = "This is a custom instruction that should appear in the final prompt."
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            custom_prompt=custom_prompt,
        )
        
        system_prompt = context.to_system_prompt()
        
        assert custom_prompt in system_prompt


class TestGoldenContextCompleteness:
    """Golden Context完整性测试"""
    
    def test_creator_profile_fields(self, db_session):
        """测试创作者特质字段完整"""
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Professional Writer",
            description="Expert in technical writing",
            traits={
                "tone": "professional",
                "style": "concise",
                "taboos": ["slang", "jargon"],
            },
        )
        db_session.add(profile)
        db_session.commit()
        
        context = profile.to_prompt_context()
        
        assert "Professional Writer" in context
        assert "professional" in context
        assert "concise" in context
    
    def test_golden_context_with_creator(self, db_session):
        """测试Golden Context包含创作者特质"""
        gc = GoldenContext(
            creator_profile="Expert Writer with 10 years experience",
        )
        
        prompt = gc.to_prompt()
        
        # 验证创作者特质存在
        assert "创作者特质" in prompt
        assert "Expert Writer" in prompt
    
    def test_empty_golden_context(self, db_session):
        """测试空Golden Context正确处理"""
        gc = GoldenContext()
        
        prompt = gc.to_prompt()
        
        # 空GoldenContext应该返回空字符串
        assert prompt == ""
        assert gc.is_empty()


class TestPromptContextStructure:
    """PromptContext结构测试"""
    
    def test_prompt_context_sections_separated(self):
        """测试提示词各部分有分隔"""
        gc = GoldenContext(
            creator_profile="Test Profile",
        )
        
        ctx = PromptContext(
            golden_context=gc,
            phase_context="Phase specific content",
            field_context="Field content",
            custom_context="Custom content",
        )
        
        system_prompt = ctx.to_system_prompt()
        
        # 验证分隔符存在
        assert "---" in system_prompt
    
    def test_prompt_context_order(self):
        """测试提示词各部分顺序正确"""
        gc = GoldenContext(
            creator_profile="CREATOR_MARKER",
        )
        
        ctx = PromptContext(
            golden_context=gc,
            phase_context="PHASE_MARKER",
            field_context="FIELD_MARKER",
        )
        
        system_prompt = ctx.to_system_prompt()
        
        # Golden Context应该在前
        creator_pos = system_prompt.find("CREATOR_MARKER")
        phase_pos = system_prompt.find("PHASE_MARKER")
        field_pos = system_prompt.find("FIELD_MARKER")
        
        # 验证顺序
        assert creator_pos < phase_pos
        assert phase_pos < field_pos


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

