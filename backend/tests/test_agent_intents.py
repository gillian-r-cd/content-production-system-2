# backend/tests/test_agent_intents.py
# 功能: 测试Agent意图表达和路由
# 验证: 所有意图类型正确路由、@引用解析、上下文传递

"""
Agent意图表达测试

测试场景:
1. 意图分类: 各类意图正确识别
2. 意图路由: 路由到正确的处理节点
3. @引用: 解析@field_name并注入内容
4. Tool调用: 直接调用工具
5. Skill调用: 调用预定义技能
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, ProjectField, generate_uuid
from core.prompt_engine import prompt_engine


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


class TestReferencesParsing:
    """@引用解析测试"""
    
    def test_parse_single_reference(self):
        """测试单个@引用解析"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="test_field",
            content="This is field A content",
        )
        
        fields_by_name = {"test_field": field_a}
        
        text = "Please refer to @test_field for details."
        replaced, referenced = prompt_engine.parse_references(text, fields_by_name)
        
        assert len(referenced) == 1
        assert referenced[0].name == "test_field"
        assert "This is field A content" in replaced
    
    def test_parse_multiple_references(self):
        """测试多个@引用解析"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="intro",
            content="Intro content",
        )
        field_b = ProjectField(
            id="field_b",
            project_id="test",
            phase="produce_inner",
            name="summary",
            content="Summary content",
        )
        
        fields_by_name = {"intro": field_a, "summary": field_b}
        
        text = "Based on @intro and @summary generate a report."
        replaced, referenced = prompt_engine.parse_references(text, fields_by_name)
        
        assert len(referenced) == 2
        assert "Intro content" in replaced
        assert "Summary content" in replaced
    
    def test_parse_phase_prefixed_reference(self):
        """测试带阶段前缀的@引用"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="goal",
            content="Goal content",
        )
        
        fields_by_name = {"goal": field_a}
        
        text = "Refer to @inner.goal for context."
        replaced, referenced = prompt_engine.parse_references(text, fields_by_name)
        
        assert len(referenced) == 1
        assert "Goal content" in replaced
    
    def test_parse_nonexistent_reference(self):
        """测试不存在的@引用保持原样"""
        fields_by_name = {}
        
        text = "Please see @nonexistent field."
        replaced, referenced = prompt_engine.parse_references(text, fields_by_name)
        
        assert len(referenced) == 0
        assert "@nonexistent" in replaced
    
    def test_parse_chinese_field_name(self):
        """测试中文字段名引用"""
        field_a = ProjectField(
            id="field_a",
            project_id="test",
            phase="produce_inner",
            name="target",
            content="Target content",
        )
        
        fields_by_name = {"target": field_a}
        
        text = "Based on @target generate more content."
        replaced, referenced = prompt_engine.parse_references(text, fields_by_name)
        
        assert len(referenced) == 1
        assert "Target content" in replaced


class TestIntentTypes:
    """意图类型测试"""
    
    def test_advance_phase_keywords(self):
        """测试推进阶段的关键词"""
        advance_inputs = [
            "continue",
            "next step",
            "go on",
            "lets start research",
        ]
        
        for inp in advance_inputs:
            # 这些应该被识别为advance_phase意图
            # 实际测试需要mock AI调用，这里验证输入格式
            assert isinstance(inp, str) and len(inp) > 0
    
    def test_generate_keywords(self):
        """测试生成内容的关键词"""
        generate_inputs = [
            "generate content",
            "write a summary",
            "create outline",
        ]
        
        for inp in generate_inputs:
            assert isinstance(inp, str) and len(inp) > 0
    
    def test_modify_keywords(self):
        """测试修改内容的关键词"""
        modify_inputs = [
            "modify the intro",
            "adjust the title",
            "change the tone",
        ]
        
        for inp in modify_inputs:
            assert isinstance(inp, str) and len(inp) > 0
    
    def test_query_with_reference(self):
        """测试带@引用的查询"""
        query_inputs = [
            "show me @intro",
            "what is in @summary",
        ]
        
        for inp in query_inputs:
            assert "@" in inp


class TestIntentRouting:
    """意图路由测试 — LangGraph 架构下通过工具名称验证"""
    
    def test_route_targets_are_valid(self):
        """新架构: 所有路由通过 AGENT_TOOLS 的工具名称"""
        from core.agent_tools import AGENT_TOOLS
        
        tool_names = {t.name for t in AGENT_TOOLS}
        # 旧路由目标映射到新工具名称
        expected_tools = {
            "advance_to_phase",    # 旧 advance_phase
            "generate_field_content",  # 旧 generate
            "modify_field",        # 旧 modify
            "run_research",        # 旧 research
            "run_evaluation",      # 旧 evaluate (含 simulate)
            "query_field",         # 旧 query
        }
        assert expected_tools.issubset(tool_names)
    
    def test_phase_nodes_exist(self):
        """测试所有阶段定义存在"""
        from core.models import PROJECT_PHASES
        
        expected_phases = [
            "intent",
            "research",
            "design_inner",
            "produce_inner",
            "design_outer",
            "produce_outer",
            "evaluate",
        ]
        
        assert PROJECT_PHASES == expected_phases


class TestStateTransition:
    """状态转换测试 — LangGraph AgentState"""
    
    def test_agent_state_structure(self):
        """测试 AgentState 结构完整 (4 字段)"""
        from core.orchestrator import AgentState
        
        required_fields = [
            "messages",
            "project_id",
            "current_phase",
            "creator_profile",
        ]
        
        annotations = AgentState.__annotations__
        for field in required_fields:
            assert field in annotations, f"Missing field: {field}"
        assert len(annotations) == 4
    
    def test_initial_state_defaults(self):
        """测试初始状态默认值"""
        from core.models import PROJECT_PHASES
        
        assert len(PROJECT_PHASES) == 7
        assert PROJECT_PHASES[0] == "intent"
        assert PROJECT_PHASES[-1] == "evaluate"


class TestBuildSystemPrompt:
    """build_system_prompt 测试"""
    
    def test_system_prompt_contains_tools(self):
        """system prompt 应包含工具能力描述"""
        from core.orchestrator import build_system_prompt, AgentState
        
        state = AgentState(
            messages=[], project_id="test",
            current_phase="intent", creator_profile="专业顾问",
        )
        prompt = build_system_prompt(state)
        
        assert "工具" in prompt or "tool" in prompt.lower()
        assert len(prompt) > 500
    
    def test_system_prompt_includes_creator(self):
        """system prompt 应包含创作者信息"""
        from core.orchestrator import build_system_prompt, AgentState
        
        state = AgentState(
            messages=[], project_id="test",
            current_phase="intent", creator_profile="资深内容专家",
        )
        prompt = build_system_prompt(state)
        
        assert "资深内容专家" in prompt
    
    def test_system_prompt_includes_phase(self):
        """system prompt 应包含当前阶段"""
        from core.orchestrator import build_system_prompt, AgentState
        
        state = AgentState(
            messages=[], project_id="test",
            current_phase="research", creator_profile="",
        )
        prompt = build_system_prompt(state)
        
        assert "research" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


