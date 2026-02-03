# backend/tests/test_prompt_engine.py
# 功能: 测试提示词引擎
# 主要函数: test_*

"""
提示词引擎测试
"""

import pytest
from core.prompt_engine import (
    PromptEngine,
    GoldenContext,
    PromptContext,
)
from core.models import (
    Project,
    CreatorProfile,
    ProjectField,
    Channel,
)


class TestGoldenContext:
    """测试Golden Context"""
    
    def test_empty_context(self):
        gc = GoldenContext()
        assert gc.is_empty()
        assert gc.to_prompt() == ""
    
    def test_full_context(self):
        gc = GoldenContext(
            creator_profile="专业严谨型",
            intent="帮助用户学习Python编程",
            consumer_personas="25-35岁职场人士",
        )
        
        prompt = gc.to_prompt()
        assert "创作者特质" in prompt
        assert "项目意图" in prompt
        assert "目标用户画像" in prompt
        assert "Python" in prompt


class TestPromptContext:
    """测试完整提示词上下文"""
    
    def test_system_prompt_generation(self):
        ctx = PromptContext(
            golden_context=GoldenContext(
                creator_profile="测试特质",
                intent="测试意图",
            ),
            phase_context="这是当前任务描述",
            field_context="参考内容A\n参考内容B",
        )
        
        system_prompt = ctx.to_system_prompt()
        
        assert "创作者特质" in system_prompt
        assert "当前任务" in system_prompt
        assert "参考内容" in system_prompt


class TestPromptEngine:
    """测试提示词引擎"""
    
    @pytest.fixture
    def engine(self):
        return PromptEngine()
    
    def test_parse_references_simple(self, engine):
        # Use English to avoid encoding issues
        text = "Please refer to @intent_analysis for design"
        fields = {
            "intent_analysis": ProjectField(
                id="f1",
                project_id="p1",
                phase="intent",
                name="intent_analysis",
                content="This is intent analysis content"
            )
        }
        
        replaced, refs = engine.parse_references(text, fields)
        
        assert len(refs) == 1
        assert refs[0].name == "intent_analysis"
        assert "This is intent analysis content" in replaced
    
    def test_parse_references_with_phase(self, engine):
        text = "Based on @inner.course_goal generate outline"
        fields = {
            "course_goal": ProjectField(
                id="f1",
                project_id="p1",
                phase="inner",
                name="course_goal",
                content="Goal content"
            )
        }
        
        replaced, refs = engine.parse_references(text, fields)
        
        assert len(refs) == 1
        assert "Goal content" in replaced
    
    def test_parse_references_not_found(self, engine):
        text = "Please refer to @nonexistent_field"
        fields = {}
        
        replaced, refs = engine.parse_references(text, fields)
        
        assert len(refs) == 0
        assert "@nonexistent_field" in replaced  # Keep original
    
    def test_phase_prompts_exist(self, engine):
        """验证所有阶段都有提示词"""
        phases = [
            "intent", "research", 
            "design_inner", "produce_inner",
            "design_outer", "produce_outer",
            "simulate", "evaluate"
        ]
        
        for phase in phases:
            assert phase in engine.PHASE_PROMPTS
            assert len(engine.PHASE_PROMPTS[phase]) > 50
    
    def test_build_golden_context(self, engine):
        """测试构建Golden Context"""
        profile = CreatorProfile(
            name="测试特质",
            traits={"tone": "专业"}
        )
        
        project = Project(
            name="测试项目",
            golden_context={
                "intent": "测试意图内容",
                "consumer_personas": "测试用户画像",
            }
        )
        
        gc = engine.build_golden_context(
            project=project,
            creator_profile=profile,
        )
        
        assert "测试特质" in gc.creator_profile
        assert gc.intent == "测试意图内容"
        assert gc.consumer_personas == "测试用户画像"
    
    def test_get_field_generation_prompt(self, engine):
        """测试字段生成提示词"""
        field = ProjectField(
            id="f1",
            project_id="p1",
            phase="inner",
            name="测试字段",
            ai_prompt="请生成一段测试内容",
            pre_answers={"问题1": "答案1", "问题2": "答案2"},
        )
        
        context = PromptContext(
            golden_context=GoldenContext(intent="测试意图"),
            phase_context="内涵生产任务",
        )
        
        prompt = engine.get_field_generation_prompt(field, context)
        
        assert "字段生成指导" in prompt
        assert "请生成一段测试内容" in prompt
        assert "用户补充信息" in prompt
        assert "答案1" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

