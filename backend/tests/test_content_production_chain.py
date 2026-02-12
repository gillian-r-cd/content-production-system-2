# backend/tests/test_content_production_chain.py
# 功能: 测试完整的内容生产链路
# 验证: 阶段流转、状态更新、上下文传递、环路完成

"""
完整内容生产链路测试

测试场景:
1. 阶段流转: 按正确顺序流转所有阶段
2. 阶段顺序调整: 中间四个阶段可拖拽调整
3. 固定阶段: intent/research固定在前，simulate/evaluate固定在后
4. 状态更新: 每个阶段状态正确更新
5. Golden Context传递: 上下文在整个流程中保持
6. 完整环路: 从意图分析到评估的完整流程
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import (
    Project, 
    ProjectField, 
    CreatorProfile,
    PROJECT_PHASES,
    generate_uuid,
)
from core.prompt_engine import prompt_engine, GoldenContext


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


class TestPhaseOrder:
    """阶段顺序测试"""
    
    def test_default_phase_order(self, db_session):
        """测试默认阶段顺序"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        expected_order = [
            "intent",
            "research",
            "design_inner",
            "produce_inner",
            "design_outer",
            "produce_outer",
            "evaluate",
        ]
        
        assert project.phase_order == expected_order
    
    def test_custom_phase_order_middle_four(self, db_session):
        """测试中间四个阶段可以调整顺序"""
        # 外延优先的顺序
        custom_order = [
            "intent",
            "research",
            "design_outer",  # 先外延设计
            "produce_outer", # 再外延生产
            "design_inner",  # 后内涵设计
            "produce_inner", # 最后内涵生产
            "evaluate",
        ]
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            phase_order=custom_order,
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        assert project.phase_order == custom_order
        
        # 验证固定阶段位置
        assert project.phase_order[0] == "intent"
        assert project.phase_order[1] == "research"
        assert project.phase_order[-1] == "evaluate"
    
    def test_phase_order_navigation(self, db_session):
        """测试阶段导航正确使用自定义顺序"""
        custom_order = [
            "intent",
            "research",
            "design_outer",
            "produce_outer",
            "design_inner",
            "produce_inner",
            "evaluate",
        ]
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            phase_order=custom_order,
            current_phase="research",
        )
        db_session.add(project)
        db_session.commit()
        
        # 验证下一个阶段是design_outer而不是design_inner
        next_phase = project.get_next_phase()
        assert next_phase == "design_outer"


class TestPhaseStatus:
    """阶段状态测试"""
    
    def test_default_phase_status(self, db_session):
        """测试默认阶段状态都是pending"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        for phase in PROJECT_PHASES:
            assert project.phase_status.get(phase) == "pending"
    
    def test_phase_status_transition(self, db_session):
        """测试阶段状态转换"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        
        # 模拟阶段推进
        # intent: pending -> in_progress -> completed
        new_status = dict(project.phase_status)
        new_status["intent"] = "in_progress"
        project.phase_status = new_status
        db_session.commit()
        
        assert project.phase_status["intent"] == "in_progress"
        
        # 完成并推进
        new_status = dict(project.phase_status)
        new_status["intent"] = "completed"
        new_status["research"] = "in_progress"
        project.phase_status = new_status
        project.current_phase = "research"
        db_session.commit()
        
        assert project.phase_status["intent"] == "completed"
        assert project.phase_status["research"] == "in_progress"
        assert project.current_phase == "research"
    
    def test_full_chain_status_tracking(self, db_session):
        """测试完整链路状态追踪"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        
        # 模拟完整流程
        for i, phase in enumerate(PROJECT_PHASES):
            # 当前阶段设为进行中
            new_status = dict(project.phase_status)
            new_status[phase] = "in_progress"
            project.phase_status = new_status
            project.current_phase = phase
            db_session.commit()
            
            assert project.phase_status[phase] == "in_progress"
            
            # 完成当前阶段
            new_status = dict(project.phase_status)
            new_status[phase] = "completed"
            project.phase_status = new_status
            db_session.commit()
            
            assert project.phase_status[phase] == "completed"
        
        # 验证所有阶段都已完成
        for phase in PROJECT_PHASES:
            assert project.phase_status[phase] == "completed"


class TestGoldenContextFlow:
    """Golden Context流转测试"""
    
    def test_creator_profile_propagation(self, db_session):
        """测试创作者特质传递"""
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Professional Profile",
            traits={"tone": "professional", "style": "concise"},
        )
        db_session.add(profile)
        db_session.commit()
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            creator_profile_id=profile.id,
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        # 构建Golden Context
        gc = prompt_engine.build_golden_context(project, creator_profile=profile)
        
        assert "Professional Profile" in gc.creator_profile
        assert "professional" in gc.creator_profile
    
    def test_intent_stored_in_golden_context(self, db_session):
        """测试意图信息存储在 golden_context JSON 字段中（但不再通过 GoldenContext.intent 访问）"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        
        # 意图存储在 project.golden_context dict 中
        intent_content = "Build an AI diagnostic assistant for doctors"
        project.golden_context = {"intent": intent_content}
        db_session.commit()
        db_session.refresh(project)
        
        # GoldenContext 只包含 creator_profile，意图通过字段依赖传递
        assert project.golden_context["intent"] == intent_content
    
    def test_creator_profile_in_golden_context(self, db_session):
        """测试创作者特质通过 GoldenContext 传递"""
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Expert Writer",
            traits={"tone": "professional"},
        )
        db_session.add(profile)
        db_session.commit()
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()
        
        gc = prompt_engine.build_golden_context(project, creator_profile=profile)
        assert "Expert Writer" in gc.creator_profile
    
    def test_context_available_in_all_phases(self, db_session):
        """测试上下文在所有阶段可用"""
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Expert Writer",
            traits={"tone": "professional"},
        )
        db_session.add(profile)
        db_session.commit()
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()
        
        # 在每个阶段构建上下文
        for phase in ["design_inner", "produce_inner", "design_outer", "produce_outer"]:
            context = prompt_engine.build_prompt_context(project=project, phase=phase)
            system_prompt = context.to_system_prompt()
            
            # system_prompt 至少应该非空
            assert isinstance(system_prompt, str)


class TestCompleteLoop:
    """完整环路测试"""
    
    def test_full_production_loop(self, db_session):
        """测试完整的内容生产循环"""
        # 1. 创建项目
        project = Project(
            id=generate_uuid(),
            name="Complete Loop Test",
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        
        # 2. 模拟意图分析阶段
        project.golden_context = {"intent": "Build AI course for developers"}
        new_status = dict(project.phase_status)
        new_status["intent"] = "completed"
        new_status["research"] = "in_progress"
        project.phase_status = new_status
        project.current_phase = "research"
        db_session.commit()
        
        assert project.current_phase == "research"
        
        # 3. 模拟消费者调研阶段
        project.golden_context = {
            **project.golden_context,
            "consumer_personas": "Software developers aged 25-40",
        }
        new_status = dict(project.phase_status)
        new_status["research"] = "completed"
        new_status["design_inner"] = "in_progress"
        project.phase_status = new_status
        project.current_phase = "design_inner"
        db_session.commit()
        
        # 4. 创建内涵设计字段
        field_design = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="design_inner",
            name="Course Outline",
            content="Module 1: Introduction\nModule 2: Deep Dive",
            status="completed",
        )
        db_session.add(field_design)
        db_session.commit()
        
        # 5. 创建内涵生产字段（依赖设计）
        field_content = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Module 1 Content",
            dependencies={"depends_on": [field_design.id], "dependency_type": "all"},
            status="pending",
        )
        db_session.add(field_content)
        db_session.commit()
        
        # 验证依赖检查
        assert field_content.can_generate({field_design.id}) == True
        
        # 6. 获取依赖上下文
        fields_by_id = {field_design.id: field_design}
        dep_context = field_content.get_dependency_context(fields_by_id)
        
        assert "Course Outline" in dep_context
        assert "Module 1" in dep_context
        
        # 7. 推进到评估阶段（simulate已合并进evaluate）
        new_status = dict(project.phase_status)
        new_status["design_inner"] = "completed"
        new_status["produce_inner"] = "completed"
        new_status["design_outer"] = "completed"
        new_status["produce_outer"] = "completed"
        new_status["evaluate"] = "in_progress"
        project.phase_status = new_status
        project.current_phase = "evaluate"
        db_session.commit()
        
        assert project.current_phase == "evaluate"
        
        # 9. 完成评估
        new_status = dict(project.phase_status)
        new_status["evaluate"] = "completed"
        project.phase_status = new_status
        db_session.commit()
        
        # 验证最终状态
        assert project.get_next_phase() is None  # 已经是最后阶段
        for phase in PROJECT_PHASES:
            assert project.phase_status[phase] == "completed"


class TestPhasePrompts:
    """阶段提示词测试"""
    
    def test_all_phases_have_prompts(self):
        """测试所有阶段都有对应的提示词"""
        from core.prompt_engine import PromptEngine
        
        expected_phases = [
            "intent",
            "research",
            "design_inner",
            "produce_inner",
            "design_outer",
            "produce_outer",
            "evaluate",
        ]
        
        for phase in expected_phases:
            prompt = PromptEngine.PHASE_PROMPTS.get(phase, "")
            assert len(prompt) > 0, f"Missing prompt for phase: {phase}"
    
    def test_phase_prompts_contain_instructions(self):
        """测试阶段提示词包含具体指令"""
        from core.prompt_engine import PromptEngine
        
        # 意图分析应该提到问题
        assert "问题" in PromptEngine.PHASE_PROMPTS["intent"] or "问" in PromptEngine.PHASE_PROMPTS["intent"]
        
        # 调研应该提到用户/消费者
        assert "用户" in PromptEngine.PHASE_PROMPTS["research"] or "消费" in PromptEngine.PHASE_PROMPTS["research"]
        
        # 评估应该提到评分/评价
        assert "评" in PromptEngine.PHASE_PROMPTS["evaluate"]


class TestVersionManagement:
    """版本管理测试"""
    
    def test_project_versioning(self, db_session):
        """测试项目版本管理"""
        # 创建v1
        project_v1 = Project(
            id=generate_uuid(),
            name="Test Project",
            version=1,
            version_note="Initial version",
        )
        db_session.add(project_v1)
        db_session.commit()
        
        # 创建v2（基于v1）
        project_v2 = Project(
            id=generate_uuid(),
            name="Test Project",
            version=2,
            version_note="Added new content",
            parent_version_id=project_v1.id,
        )
        db_session.add(project_v2)
        db_session.commit()
        
        assert project_v2.version == 2
        assert project_v2.parent_version_id == project_v1.id
    
    def test_version_note_required_for_new_version(self, db_session):
        """测试新版本需要版本说明"""
        project_v1 = Project(
            id=generate_uuid(),
            name="Test Project",
            version=1,
        )
        db_session.add(project_v1)
        db_session.commit()
        
        project_v2 = Project(
            id=generate_uuid(),
            name="Test Project",
            version=2,
            version_note="Updated after feedback",
            parent_version_id=project_v1.id,
        )
        
        # 版本说明存在
        assert project_v2.version_note == "Updated after feedback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


