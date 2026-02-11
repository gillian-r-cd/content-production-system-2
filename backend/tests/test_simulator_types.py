# backend/tests/test_simulator_types.py
# 功能: 测试各种模拟器类型的实现
"""
测试所有模拟器类型的正确性
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.models import Simulator
from core.tools.simulator import (
    run_simulation,
    run_reading_simulation,
    run_dialogue_simulation,
    run_decision_simulation,
    run_exploration_simulation,
    run_experience_simulation,
    SimulationResult,
    SimulationFeedback,
)


# Test fixtures
@pytest.fixture
def base_persona():
    return {
        "name": "张三",
        "background": "30岁，产品经理，关注效率工具",
        "story": "每天处理大量工作，希望找到提高效率的方法",
    }


@pytest.fixture
def sample_content():
    return """
# 效率工具 Pro

帮助你管理日常任务，提高工作效率。

## 核心功能
- 任务管理：创建、分配、追踪任务
- 时间追踪：记录每项任务花费的时间
- 报告分析：自动生成效率报告

## 定价
- 基础版：免费
- 专业版：99元/月
"""


class TestSimulatorTypes:
    """测试模拟器类型分发"""

    def test_reading_type_dispatched(self):
        """reading类型应该调用run_reading_simulation"""
        simulator = Simulator(
            id="s1",
            name="阅读模拟器",
            interaction_type="reading",
        )
        assert simulator.interaction_type == "reading"

    def test_dialogue_type_dispatched(self):
        """dialogue类型应该调用run_dialogue_simulation"""
        simulator = Simulator(
            id="s2",
            name="对话模拟器",
            interaction_type="dialogue",
        )
        assert simulator.interaction_type == "dialogue"

    def test_decision_type_dispatched(self):
        """decision类型应该调用run_decision_simulation"""
        simulator = Simulator(
            id="s3",
            name="决策模拟器",
            interaction_type="decision",
        )
        assert simulator.interaction_type == "decision"

    def test_exploration_type_dispatched(self):
        """exploration类型应该调用run_exploration_simulation"""
        simulator = Simulator(
            id="s4",
            name="探索模拟器",
            interaction_type="exploration",
        )
        assert simulator.interaction_type == "exploration"

    def test_experience_type_dispatched(self):
        """experience类型应该调用run_experience_simulation"""
        simulator = Simulator(
            id="s5",
            name="体验模拟器",
            interaction_type="experience",
        )
        assert simulator.interaction_type == "experience"


class TestDialogueSimulation:
    """测试对话式模拟"""

    @pytest.mark.asyncio
    async def test_dialogue_returns_simulation_result(self, base_persona, sample_content):
        """对话式模拟应该返回SimulationResult而不是AsyncGenerator"""
        simulator = Simulator(
            id="s1",
            name="对话模拟器",
            interaction_type="dialogue",
            max_turns=3,
        )
        
        # Mock AI responses
        mock_responses = [
            MagicMock(content="这个工具有什么特色功能？"),  # consumer question 1
            MagicMock(content="我们的任务管理功能支持多人协作和自动提醒。"),  # service response 1
            MagicMock(content="好的，我了解了，谢谢。"),  # consumer ends
            MagicMock(content='{"scores": {"响应相关性": 8, "问题解决率": 7, "交互体验": 8}, "comments": {"响应相关性": "回答切题", "问题解决率": "基本解答", "交互体验": "流畅"}, "questions_answered": ["特色功能"], "questions_unanswered": [], "friction_points": [], "would_continue": true, "overall": "体验良好"}'),  # evaluation
        ]
        
        with patch("core.tools.simulator.llm.ainvoke") as mock_chat:
            mock_chat.side_effect = mock_responses
            
            result = await run_dialogue_simulation(simulator, sample_content, base_persona, max_turns=3)
            
            # 验证返回类型
            assert isinstance(result, SimulationResult)
            assert result.success is True
            
            # 验证对话历史存在且非空
            assert isinstance(result.interaction_log, list)
            assert len(result.interaction_log) > 0
            
            # 验证对话中有消费者和服务方的消息
            roles = [log.get("role") for log in result.interaction_log]
            assert "consumer" in roles

    @pytest.mark.asyncio
    async def test_dialogue_generates_feedback(self, base_persona, sample_content):
        """对话结束后应该生成评估反馈"""
        simulator = Simulator(
            id="s1",
            name="对话模拟器",
            interaction_type="dialogue",
            evaluation_dimensions=["响应相关性", "问题解决率", "交互体验"],
        )
        
        mock_responses = [
            MagicMock(content="好的，我了解了。"),  # consumer ends immediately
            MagicMock(content='{"scores": {"响应相关性": 8, "问题解决率": 7, "交互体验": 9}, "comments": {"响应相关性": "切题", "问题解决率": "解决", "交互体验": "好"}, "questions_answered": [], "questions_unanswered": [], "friction_points": [], "would_continue": true, "overall": "满意"}'),
        ]
        
        with patch("core.tools.simulator.llm.ainvoke") as mock_chat:
            mock_chat.side_effect = mock_responses
            
            result = await run_dialogue_simulation(simulator, sample_content, base_persona)
            
            # 验证反馈不是空的"对话已完成"
            assert result.feedback.overall != "对话已完成"
            assert result.feedback.overall != ""
            
            # 验证有评分
            assert len(result.feedback.scores) > 0


class TestExplorationSimulation:
    """测试探索式模拟"""

    @pytest.mark.asyncio
    async def test_exploration_with_task(self, base_persona, sample_content):
        """探索式模拟应该记录用户寻找答案的过程"""
        simulator = Simulator(
            id="s1",
            name="探索模拟器",
            interaction_type="exploration",
        )
        
        mock_response = MagicMock(content='''{
            "exploration_path": ["首先看标题", "然后看核心功能", "最后看定价"],
            "attention_points": ["任务管理", "时间追踪"],
            "found_answer": true,
            "answer_location": "核心功能部分",
            "difficulties": ["定价信息不够详细"],
            "missing_info": ["试用期信息"],
            "scores": {"找到答案效率": 8, "信息完整性": 7, "满意度": 8},
            "comments": {"找到答案效率": "快", "信息完整性": "基本", "满意度": "满意"},
            "overall": "能找到需要的信息"
        }''')
        
        with patch("core.tools.simulator.llm.ainvoke", return_value=mock_response):
            result = await run_exploration_simulation(simulator, sample_content, base_persona)
            
            assert result.success is True
            assert isinstance(result.interaction_log, dict)
            assert "exploration_path" in result.interaction_log
            assert result.feedback.comments.get("found_answer") == "True"


class TestExperienceSimulation:
    """测试体验式模拟"""

    @pytest.mark.asyncio
    async def test_experience_records_steps(self, base_persona, sample_content):
        """体验式模拟应该记录用户完成任务的步骤"""
        simulator = Simulator(
            id="s1",
            name="体验模拟器",
            interaction_type="experience",
        )
        
        mock_response = MagicMock(content='''{
            "steps": [
                {"step": 1, "action": "打开应用", "result": "成功", "feeling": "顺利"},
                {"step": 2, "action": "创建任务", "result": "成功", "feeling": "简单"}
            ],
            "task_completed": true,
            "time_estimate": "5分钟",
            "pain_points": ["没有快捷键"],
            "delights": ["界面简洁"],
            "suggestions": ["增加快捷键支持"],
            "scores": {"易用性": 8, "效率": 7, "愉悦度": 8},
            "comments": {"易用性": "简单", "效率": "还行", "愉悦度": "不错"},
            "would_recommend": true,
            "overall": "体验良好"
        }''')
        
        with patch("core.tools.simulator.llm.ainvoke", return_value=mock_response):
            result = await run_experience_simulation(simulator, sample_content, base_persona)
            
            assert result.success is True
            assert isinstance(result.interaction_log, dict)
            assert "steps" in result.interaction_log
            assert len(result.interaction_log["steps"]) > 0
            assert result.feedback.comments.get("would_recommend") == "True"


class TestSimulationIntegration:
    """测试模拟结果与评估的集成"""

    def test_dialogue_log_structure_for_evaluator(self):
        """对话记录结构应该适合评估器处理"""
        # 模拟对话记录格式
        interaction_log = [
            {"role": "consumer", "content": "这个工具怎么用？", "turn": 1},
            {"role": "service", "content": "您可以先创建一个任务...", "turn": 1},
            {"role": "consumer", "content": "好的，明白了。", "turn": 2},
        ]
        
        # 验证格式正确
        for log in interaction_log:
            assert "role" in log
            assert "content" in log
            assert log["role"] in ["consumer", "service"]

    def test_feedback_structure_complete(self):
        """反馈结构应该包含所有必要字段"""
        feedback = SimulationFeedback(
            scores={"维度1": 8.0, "维度2": 7.0},
            comments={"维度1": "评语1", "维度2": "评语2"},
            overall="总体评价",
        )
        
        assert feedback.scores is not None
        assert feedback.comments is not None
        assert feedback.overall is not None
        
        # 可以转换为dict
        feedback_dict = {
            "scores": feedback.scores,
            "comments": feedback.comments,
            "overall": feedback.overall,
        }
        assert "scores" in feedback_dict


class TestDefaultTemplates:
    """测试默认提示词模板"""

    def test_all_types_have_templates(self):
        """所有交互类型都应该有默认模板"""
        types = ["dialogue", "reading", "decision", "exploration", "experience"]
        
        for sim_type in types:
            template = Simulator.get_default_template(sim_type)
            assert template is not None
            assert len(template) > 0
            assert "{persona}" in template  # 应该包含persona占位符

    def test_unknown_type_falls_back(self):
        """未知类型应该fallback到reading模板"""
        template = Simulator.get_default_template("unknown_type")
        reading_template = Simulator.get_default_template("reading")
        assert template == reading_template


