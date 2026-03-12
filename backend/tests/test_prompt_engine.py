# backend/tests/test_prompt_engine.py
# 功能: 测试提示词引擎
# 主要函数: test_*

"""
提示词引擎测试

重构说明（2026-02）:
- GoldenContext 现在只包含 creator_profile
- intent 和 consumer_personas 应通过字段依赖传递
"""

import pytest
from core.prompt_engine import (
    PromptEngine,
    GoldenContext,
    PromptContext,
)
from core.localization import DEFAULT_LOCALE
from core.models import (
    Project,
    CreatorProfile,
    ProjectField,
    ContentBlock,
    Channel,
)


class TestGoldenContext:
    """测试Golden Context - 只包含创作者特质"""
    
    def test_empty_context(self):
        gc = GoldenContext()
        assert gc.is_empty()
        assert gc.to_prompt() == ""
    
    def test_with_creator_profile(self):
        """GoldenContext 只包含创作者特质"""
        gc = GoldenContext(
            creator_profile="专业严谨型: 适合B2B、技术类、专业培训内容",
        )
        
        prompt = gc.to_prompt()
        assert "创作者特质" in prompt
        assert "专业严谨型" in prompt
        assert not gc.is_empty()


class TestPromptContext:
    """测试完整提示词上下文"""
    
    def test_system_prompt_generation(self):
        ctx = PromptContext(
            golden_context=GoldenContext(
                creator_profile="测试特质",
            ),
            phase_context="这是当前任务描述",
            field_context="## 项目意图\n测试意图\n\n## 目标用户\n测试用户",
        )
        
        system_prompt = ctx.to_system_prompt()
        
        assert "创作者特质" in system_prompt
        assert "当前任务" in system_prompt
        assert "参考内容" in system_prompt
        # 字段依赖内容通过 field_context 传递
        assert "项目意图" in system_prompt

    def test_system_prompt_generation_uses_japanese_runtime_headers(self):
        ctx = PromptContext(
            golden_context=GoldenContext(
                creator_profile="日本語の特性",
                locale="ja-JP",
            ),
            phase_context="これは現在のタスクです",
            field_context="## 参考情報\n既存内容",
            channel_context="メールマガジン",
        )

        system_prompt = ctx.to_system_prompt()

        assert "クリエイタープロファイル" in system_prompt
        assert "現在のタスク" in system_prompt
        assert "参考情報" in system_prompt
        assert "対象チャネル" in system_prompt
        assert "当前任务" not in system_prompt
        assert "目标渠道" not in system_prompt
    
    def test_field_context_for_dependencies(self):
        """测试通过 field_context 传递依赖内容"""
        # 模拟意图分析和消费者调研的依赖传递
        field_context = """## 意图分析
这是意图分析的结果...

## 消费者调研
这是消费者调研的结果..."""
        
        ctx = PromptContext(
            golden_context=GoldenContext(creator_profile="专业型"),
            phase_context="内涵设计任务",
            field_context=field_context,
        )
        
        system_prompt = ctx.to_system_prompt()
        
        assert "意图分析" in system_prompt
        assert "消费者调研" in system_prompt


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

    def test_parse_references_by_stable_id(self, engine):
        text = "Please refer to @id:block-123 for design"
        field = ContentBlock(
            id="block-123",
            project_id="p1",
            name="intent_analysis",
            block_type="field",
            content="Stable id content",
        )

        replaced, refs = engine.parse_references(text, {"intent_analysis": field})

        assert len(refs) == 1
        assert refs[0].id == "block-123"
        assert "Stable id content" in replaced
        assert "id:block-123" in replaced

    def test_parse_references_uses_japanese_runtime_labels(self, engine):
        text = "参照 @id:block-123"
        field = ContentBlock(
            id="block-123",
            project_id="p1",
            name="概要",
            block_type="field",
            content="参照本文",
        )

        replaced, refs = engine.parse_references(
            text,
            {"概要": field},
            locale="ja-JP",
        )

        assert len(refs) == 1
        assert "[参照対象]" in replaced
        assert "参照本文" in replaced
        assert "引用 [" not in replaced

    def test_build_reference_lookup_skips_ambiguous_names(self, engine):
        block_a = ContentBlock(
            id="block-a",
            project_id="p1",
            name="duplicate",
            block_type="field",
            content="A",
        )
        block_b = ContentBlock(
            id="block-b",
            project_id="p1",
            name="duplicate",
            block_type="field",
            content="B",
        )

        lookup = engine.build_reference_lookup([block_a, block_b])

        assert "duplicate" not in lookup
        assert lookup["id:block-a"].id == "block-a"
        assert lookup["id:block-b"].id == "block-b"

    def test_parse_references_keeps_ambiguous_name_unresolved(self, engine):
        text = "Please refer to @duplicate and @id:block-b"
        block_a = ContentBlock(
            id="block-a",
            project_id="p1",
            name="duplicate",
            block_type="field",
            content="A",
        )
        block_b = ContentBlock(
            id="block-b",
            project_id="p1",
            name="duplicate",
            block_type="field",
            content="B",
        )

        replaced, refs = engine.parse_references(
            text,
            engine.build_reference_lookup([block_a, block_b]),
        )

        assert "@duplicate" in replaced
        assert "B" in replaced
        assert len(refs) == 1
        assert refs[0].id == "block-b"
    
    def test_phase_prompts_exist(self, engine):
        """验证所有阶段都有提示词"""
        phases = [
            "intent", "research", 
            "design_inner", "produce_inner",
            "design_outer", "produce_outer",
            "evaluate"
        ]
        
        for phase in phases:
            assert phase in engine.PHASE_PROMPTS
            assert len(engine.PHASE_PROMPTS[phase]) > 50

    def test_get_phase_prompt_uses_japanese_builtin_prompt(self, engine):
        prompt = engine._get_phase_prompt("intent", locale="ja-JP")

        assert "あなたはコンテンツ戦略コンサルタントです" in prompt
        assert "3 つの質問" in prompt

    def test_build_golden_context_defaults_locale(self, engine):
        project = Project(name="默认项目")

        gc = engine.build_golden_context(project=project)

        assert gc.locale == DEFAULT_LOCALE

    def test_build_golden_context_keeps_project_locale(self, engine):
        project = Project(name="日本語项目", locale="ja-JP")

        gc = engine.build_golden_context(project=project)

        assert gc.locale == "ja-JP"

    def test_build_golden_context_formats_creator_profile_with_project_locale(self, engine):
        profile = CreatorProfile(
            name="知的で簡潔",
            locale="zh-CN",
            traits={"tone": "落ち着いたビジネス文体"},
        )
        project = Project(name="日本語项目", locale="ja-JP")

        gc = engine.build_golden_context(project=project, creator_profile=profile)

        assert "## クリエイタープロファイル" in gc.creator_profile
        assert "名前: 知的で簡潔" in gc.creator_profile
        assert "トーン: 落ち着いたビジネス文体" in gc.creator_profile
        assert "创作者特质" not in gc.creator_profile
    
    def test_build_golden_context(self, engine):
        """测试构建Golden Context - 只包含创作者特质"""
        profile = CreatorProfile(
            name="测试特质",
            traits={"tone": "专业"}
        )
        
        project = Project(
            name="测试项目",
            # golden_context 已废弃，不再使用
        )
        
        gc = engine.build_golden_context(
            project=project,
            creator_profile=profile,
        )
        
        # GoldenContext 只包含 creator_profile
        assert "测试特质" in gc.creator_profile
        assert not gc.is_empty()
    
    def test_get_field_generation_prompt(self, engine):
        """测试字段生成提示词"""
        field = ContentBlock(
            id="f1",
            project_id="p1",
            name="测试字段",
            block_type="field",
            ai_prompt="请生成一段测试内容",
            pre_questions=[
                {"id": "q1", "question": "问题1", "required": True},
                {"id": "q2", "question": "问题2", "required": False},
            ],
            pre_answers={"q1": "答案1", "q2": "答案2"},
        )
        
        # 依赖内容通过 field_context 传递
        context = PromptContext(
            golden_context=GoldenContext(creator_profile="专业型"),
            phase_context="内涵生产任务",
            field_context="## 意图分析\n测试意图内容",
        )
        
        prompt = engine.get_field_generation_prompt(field, context)
        
        assert "测试字段" in prompt  # 字段名称应出现
        assert "请生成一段测试内容" in prompt  # AI提示词应出现
        assert "用户补充信息" in prompt
        assert "答案1" in prompt

    def test_get_field_generation_prompt_uses_japanese_markdown_and_pre_answers_headers(self, engine):
        field = ContentBlock(
            id="f-ja",
            project_id="p1",
            name="概要",
            block_type="field",
            ai_prompt="日本語で要約してください",
            pre_questions=[
                {"id": "q1", "question": "強調したい点は？", "required": True},
            ],
            pre_answers={"q1": "導入効果"},
        )

        context = PromptContext(
            golden_context=GoldenContext(creator_profile="簡潔で論理的", locale="ja-JP"),
            phase_context="内包制作タスク",
        )

        prompt = engine.get_field_generation_prompt(field, context)

        assert "# 出力形式（必須）" in prompt
        assert "# ユーザー補足情報" in prompt
        assert "強調したい点は？: 導入効果" in prompt
        assert "输出格式（必须遵守）" not in prompt
        assert "用户补充信息" not in prompt

    def test_get_field_generation_prompt_keeps_legacy_text_key_answers(self, engine):
        field = ContentBlock(
            id="f2",
            project_id="p1",
            name="兼容字段",
            block_type="field",
            ai_prompt="请生成兼容测试内容",
            pre_questions=[
                {"id": "legacy-q1", "question": "问题1", "required": False},
            ],
            pre_answers={"问题1": "旧格式答案"},
        )
        context = PromptContext(
            golden_context=GoldenContext(creator_profile="专业型"),
            phase_context="兼容任务",
        )

        prompt = engine.get_field_generation_prompt(field, context)

        assert "问题1" in prompt
        assert "旧格式答案" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
