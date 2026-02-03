# backend/tests/test_field_dependencies.py
# 功能: 测试字段依赖关系的各种场景
# 验证: 串行依赖、并行依赖、复杂链、循环检测、上下文注入

"""
字段依赖关系完整测试

测试场景:
1. 串行依赖: A → B → C (依次执行)
2. 并行依赖: A → (B, C) (B、C可并行)
3. 复杂依赖: A → B, A → C, B+C → D (D等待B和C)
4. 循环检测: A → B → A (应检测出循环)
5. 上下文注入: 依赖字段的内容正确注入到后续字段
6. 依赖满足检查: can_generate正确判断
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, ProjectField, generate_uuid
from core.tools.field_generator import resolve_field_order
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


class TestSerialDependency:
    """串行依赖测试: A → B → C"""
    
    def test_serial_order_resolution(self, db_session):
        """测试串行依赖解析顺序"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        # 创建字段: A → B → C
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": [field_b.id], "dependency_type": "all"},
        )
        
        db_session.add_all([field_a, field_b, field_c])
        db_session.commit()
        
        # 解析顺序
        order = resolve_field_order([field_a, field_b, field_c])
        
        # 应该是 [[A], [B], [C]]
        assert len(order) == 3
        assert order[0][0].name == "Field A"
        assert order[1][0].name == "Field B"
        assert order[2][0].name == "Field C"
    
    def test_serial_can_generate(self, db_session):
        """测试串行依赖的生成检查"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        # A没有依赖，可以直接生成
        assert field_a.can_generate(set()) == True
        
        # B依赖A，A未完成时不能生成
        assert field_b.can_generate(set()) == False
        
        # A完成后B可以生成
        assert field_b.can_generate({"field_a"}) == True


class TestParallelDependency:
    """并行依赖测试: A → (B, C)"""
    
    def test_parallel_order_resolution(self, db_session):
        """测试并行依赖解析顺序"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        # A → (B, C) B和C都只依赖A
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        
        db_session.add_all([field_a, field_b, field_c])
        db_session.commit()
        
        # 解析顺序
        order = resolve_field_order([field_a, field_b, field_c])
        
        # 应该是 [[A], [B, C]]
        assert len(order) == 2
        assert order[0][0].name == "Field A"
        assert len(order[1]) == 2
        assert set(f.name for f in order[1]) == {"Field B", "Field C"}
    
    def test_parallel_both_can_generate(self, db_session):
        """测试并行依赖：A完成后B和C都可以生成"""
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id="field_c",
            project_id="test",
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        # A未完成
        assert field_b.can_generate(set()) == False
        assert field_c.can_generate(set()) == False
        
        # A完成后
        completed = {"field_a"}
        assert field_b.can_generate(completed) == True
        assert field_c.can_generate(completed) == True


class TestComplexDependency:
    """复杂依赖测试: A → B, A → C, (B, C) → D"""
    
    def test_complex_order_resolution(self, db_session):
        """测试复杂依赖解析顺序"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_d = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field D",
            dependencies={"depends_on": [field_b.id, field_c.id], "dependency_type": "all"},
        )
        
        db_session.add_all([field_a, field_b, field_c, field_d])
        db_session.commit()
        
        # 解析顺序: [[A], [B, C], [D]]
        order = resolve_field_order([field_a, field_b, field_c, field_d])
        
        assert len(order) == 3
        assert order[0][0].name == "Field A"
        assert len(order[1]) == 2
        assert set(f.name for f in order[1]) == {"Field B", "Field C"}
        assert order[2][0].name == "Field D"
    
    def test_complex_d_needs_both_b_and_c(self, db_session):
        """测试D需要B和C都完成（all类型）"""
        field_d = ProjectField(
            id="field_d",
            project_id="test",
            phase="produce_inner",
            name="Field D",
            dependencies={"depends_on": ["field_b", "field_c"], "dependency_type": "all"},
        )
        
        # 只有B完成
        assert field_d.can_generate({"field_b"}) == False
        # 只有C完成
        assert field_d.can_generate({"field_c"}) == False
        # B和C都完成
        assert field_d.can_generate({"field_b", "field_c"}) == True
    
    def test_any_dependency_type(self, db_session):
        """测试any依赖类型：B或C任一完成即可"""
        field_d = ProjectField(
            id="field_d",
            project_id="test",
            phase="produce_inner",
            name="Field D",
            dependencies={"depends_on": ["field_b", "field_c"], "dependency_type": "any"},
        )
        
        # 只有B完成 - 可以
        assert field_d.can_generate({"field_b"}) == True
        # 只有C完成 - 可以
        assert field_d.can_generate({"field_c"}) == True
        # 都没完成 - 不可以
        assert field_d.can_generate(set()) == False


class TestCycleDetection:
    """循环依赖检测测试"""
    
    def test_direct_cycle_detection(self, db_session):
        """测试直接循环: A → B → A"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": ["field_b"], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        # 应该抛出循环依赖错误
        with pytest.raises(ValueError, match="循环依赖"):
            resolve_field_order([field_a, field_b])
    
    def test_indirect_cycle_detection(self, db_session):
        """测试间接循环: A → B → C → A"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": ["field_c"], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id="field_c",
            project_id="test",
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": ["field_b"], "dependency_type": "all"},
        )
        
        with pytest.raises(ValueError, match="循环依赖"):
            resolve_field_order([field_a, field_b, field_c])
    
    def test_no_cycle_passes(self, db_session):
        """测试无循环的依赖应该正常解析"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        # 不应该抛出异常
        order = resolve_field_order([field_a, field_b])
        assert len(order) == 2


class TestContextInjection:
    """上下文注入测试"""
    
    def test_get_dependency_context(self, db_session):
        """测试从依赖字段获取上下文"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            content="这是字段A的内容",
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        fields_by_id = {"field_a": field_a}
        
        context = field_b.get_dependency_context(fields_by_id)
        
        assert "Field A" in context
        assert "这是字段A的内容" in context
    
    def test_multiple_dependency_context(self, db_session):
        """测试多个依赖字段的上下文合并"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            content="内容A",
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            content="内容B",
        )
        field_c = ProjectField(
            id="field_c",
            project_id="test",
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": ["field_a", "field_b"], "dependency_type": "all"},
        )
        
        fields_by_id = {"field_a": field_a, "field_b": field_b}
        
        context = field_c.get_dependency_context(fields_by_id)
        
        assert "Field A" in context
        assert "内容A" in context
        assert "Field B" in context
        assert "内容B" in context
    
    def test_empty_content_not_included(self, db_session):
        """测试空内容的依赖字段不包含在上下文中"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="Field A",
            content="",  # 空内容
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": ["field_a"], "dependency_type": "all"},
        )
        
        fields_by_id = {"field_a": field_a}
        
        context = field_b.get_dependency_context(fields_by_id)
        
        # 空内容不应该出现在上下文中
        assert context == ""
    
    def test_context_built_with_dependencies(self, db_session):
        """测试完整的上下文构建包含依赖"""
        project = Project(id=generate_uuid(), name="Test Project")
        project.golden_context = {"intent": "Test Intent"}
        
        field_a = ProjectField(
            id="field_a",
            project_id=project.id,
            phase="produce_inner",
            name="Field A",
            content="Field A Content",
        )
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            dependent_fields=[field_a],
        )
        
        system_prompt = context.to_system_prompt()
        
        assert "Field A" in system_prompt
        assert "Field A Content" in system_prompt


class TestCrossPhaseContext:
    """跨阶段上下文传递测试"""
    
    def test_golden_context_includes_intent(self, db_session):
        """测试Golden Context包含意图分析结果"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            golden_context={"intent": "为医生提供AI诊断辅助系统"}
        )
        
        gc = prompt_engine.build_golden_context(project)
        
        assert "AI诊断辅助" in gc.intent
    
    def test_golden_context_includes_research(self, db_session):
        """测试Golden Context包含消费者调研结果"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            golden_context={
                "intent": "Test Intent",
                "consumer_personas": "目标用户：35-50岁医生"
            }
        )
        
        gc = prompt_engine.build_golden_context(project)
        
        assert "医生" in gc.consumer_personas
    
    def test_context_propagation_to_all_phases(self, db_session):
        """测试上下文传递到所有阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            golden_context={
                "creator_profile": "专业医疗顾问",
                "intent": "AI诊断系统",
                "consumer_personas": "临床医生"
            }
        )
        
        for phase in ["design_inner", "produce_inner", "design_outer", "produce_outer"]:
            context = prompt_engine.build_prompt_context(
                project=project,
                phase=phase,
            )
            
            system_prompt = context.to_system_prompt()
            
            # 所有阶段都应该包含核心上下文
            assert "AI诊断系统" in system_prompt or "intent" in context.golden_context.intent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

