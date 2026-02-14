# backend/tests/test_langgraph_migration.py
"""
LangGraph 迁移集成测试

验证：
1. LLM 统一客户端（llm.py）
2. Agent 工具注册（agent_tools.py）
3. LangGraph 编排器（orchestrator.py）
4. 流式 API 端点（api/agent.py）
5. 编辑引擎（edit_engine.py）
6. 摘要服务（digest_service.py）
7. 全链路导入完整性
"""
import pytest
import asyncio
import json

# ============== Test 1: LLM 统一客户端 ==============

class TestLLMClient:
    """验证 llm.py 替代 ai_client.py"""
    
    def test_llm_singleton_exists(self):
        """主 LLM 实例应该存在且配置正确"""
        from core.llm import llm
        assert llm is not None
        assert hasattr(llm, 'ainvoke')
        assert hasattr(llm, 'astream')
        assert hasattr(llm, 'bind_tools')
    
    def test_llm_mini_exists(self):
        """轻量 LLM 实例应该存在"""
        from core.llm import llm_mini
        assert llm_mini is not None
    
    def test_get_chat_model(self):
        """get_chat_model 应该返回新的实例"""
        from core.llm import get_chat_model
        m1 = get_chat_model(temperature=0.5)
        m2 = get_chat_model(temperature=0.9)
        assert m1 is not m2
        assert hasattr(m1, 'ainvoke')
    
    def test_llm_supports_tool_binding(self):
        """LLM 应该支持工具绑定"""
        from core.llm import llm
        from langchain_core.tools import tool
        
        @tool
        def dummy_tool(x: str) -> str:
            """A dummy tool."""
            return x
        
        bound = llm.bind_tools([dummy_tool])
        assert bound is not None
    
    def test_llm_supports_structured_output(self):
        """LLM 应该支持结构化输出"""
        from core.llm import llm
        from pydantic import BaseModel
        
        class TestOutput(BaseModel):
            name: str
            score: int
        
        structured = llm.with_structured_output(TestOutput)
        assert structured is not None


# ============== Test 2: Agent 工具注册 ==============

class TestAgentTools:
    """验证 agent_tools.py 的 12 个工具"""
    
    def test_agent_tools_count(self):
        """应该有 12 个工具"""
        from core.agent_tools import AGENT_TOOLS
        assert len(AGENT_TOOLS) == 12, f"Expected 12, got {len(AGENT_TOOLS)}: {[t.name for t in AGENT_TOOLS]}"
    
    def test_agent_tools_names(self):
        """所有工具名称应该正确"""
        from core.agent_tools import AGENT_TOOLS
        names = {t.name for t in AGENT_TOOLS}
        expected = {
            "modify_field", "generate_field_content", "query_field",
            "read_field", "update_field", "manage_architecture",
            "advance_to_phase", "run_research", "manage_persona",
            "run_evaluation", "generate_outline", "manage_skill",
        }
        assert names == expected, f"Missing: {expected - names}, Extra: {names - expected}"
    
    def test_produce_tools_subset(self):
        """PRODUCE_TOOLS 应该是 AGENT_TOOLS 名称的子集"""
        from core.agent_tools import AGENT_TOOLS, PRODUCE_TOOLS
        all_names = {t.name for t in AGENT_TOOLS}
        assert PRODUCE_TOOLS.issubset(all_names), f"Not subset: {PRODUCE_TOOLS - all_names}"
    
    def test_each_tool_has_docstring(self):
        """每个工具都应该有详细的 docstring"""
        from core.agent_tools import AGENT_TOOLS
        for tool in AGENT_TOOLS:
            assert tool.description, f"Tool {tool.name} has no description"
            # 文档至少 50 字（我们的 docstring 都很详细）
            assert len(tool.description) >= 50, (
                f"Tool {tool.name} description too short ({len(tool.description)} chars)"
            )
    
    def test_tools_are_langchain_tools(self):
        """每个工具都应该是 LangChain Tool"""
        from core.agent_tools import AGENT_TOOLS
        from langchain_core.tools import BaseTool
        for tool in AGENT_TOOLS:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"


# ============== Test 3: LangGraph 编排器 ==============

class TestOrchestrator:
    """验证 orchestrator.py 的 Agent Graph"""
    
    def test_graph_builder_exists(self):
        """graph builder 应该存在（编译后的图通过 get_agent_graph() 异步获取）"""
        from core.orchestrator import _graph_builder
        assert _graph_builder is not None

    def test_graph_builder_nodes(self):
        """graph builder 应该包含 agent 和 tools 节点"""
        from core.orchestrator import _graph_builder
        # StateGraph 未编译时通过 .nodes 属性查看
        nodes = set(_graph_builder.nodes.keys())
        assert "agent" in nodes, f"Missing 'agent' node. Got: {nodes}"
        assert "tools" in nodes, f"Missing 'tools' node. Got: {nodes}"

    def test_agent_state_fields(self):
        """AgentState 应该有 7 个字段（原 4 个 + mode/mode_prompt/memory_context）"""
        from core.orchestrator import AgentState
        fields = list(AgentState.__annotations__.keys())
        assert len(fields) == 7, f"Expected 7 fields, got {len(fields)}: {fields}"
        assert "messages" in fields
        assert "project_id" in fields
        assert "current_phase" in fields
        assert "creator_profile" in fields
        assert "mode" in fields
        assert "mode_prompt" in fields
        assert "memory_context" in fields

    def test_build_system_prompt(self):
        """build_system_prompt 应该返回非空字符串"""
        from core.orchestrator import build_system_prompt, AgentState
        state = AgentState(
            messages=[],
            project_id="test-id",
            current_phase="intent",
            creator_profile="",
            mode="assistant",
            mode_prompt="",
            memory_context="",
        )
        prompt = build_system_prompt(state)
        assert isinstance(prompt, str)
        assert len(prompt) > 500, f"System prompt too short: {len(prompt)} chars"
        # 应该包含关键片段
        assert "工具" in prompt or "tool" in prompt.lower()

    def test_build_system_prompt_with_mode(self):
        """build_system_prompt 使用 mode_prompt 时应替换身份段"""
        from core.orchestrator import build_system_prompt, AgentState
        custom_identity = "你是一个严格的审稿人。"
        state = AgentState(
            messages=[],
            project_id="test-id",
            current_phase="intent",
            creator_profile="",
            mode="critic",
            mode_prompt=custom_identity,
            memory_context="",
        )
        prompt = build_system_prompt(state)
        assert custom_identity in prompt, "mode_prompt should replace identity section"
        assert "智能内容生产 Agent" not in prompt, "Default identity should be replaced"

    def test_dead_code_removed(self):
        """P3-1: ContentProductionAgent 等向后兼容代码已删除"""
        import importlib
        mod = importlib.import_module("core.orchestrator")
        assert not hasattr(mod, "ContentProductionAgent"), "ContentProductionAgent should be removed"
        assert not hasattr(mod, "content_agent"), "content_agent should be removed"
        assert not hasattr(mod, "ContentProductionState"), "ContentProductionState alias should be removed"
        assert not hasattr(mod, "normalize_intent"), "normalize_intent should be removed"
        assert not hasattr(mod, "normalize_consumer_personas"), "normalize_consumer_personas should be removed"


# ============== Test 4: API 端点 ==============

class TestAgentAPI:
    """验证 api/agent.py 的端点"""
    
    def test_router_has_stream_endpoint(self):
        """应该有 /stream 端点"""
        from api.agent import router
        paths = [r.path for r in router.routes]
        assert "/stream" in paths, f"Missing /stream. Got: {paths}"
    
    def test_router_has_all_endpoints(self):
        """应该有所有必要端点"""
        from api.agent import router
        paths = set(r.path for r in router.routes)
        expected = {"/stream", "/chat", "/history/{project_id}", 
                    "/message/{message_id}", "/retry/{message_id}",
                    "/tool", "/advance"}
        assert expected.issubset(paths), f"Missing: {expected - paths}"
    
    def test_sse_event_format(self):
        """sse_event 应该返回正确格式"""
        from api.agent import sse_event
        result = sse_event({"type": "token", "content": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        payload = json.loads(result[6:-2])
        assert payload["type"] == "token"
        assert payload["content"] == "hello"
    
    def test_get_agent_graph_is_async(self):
        """get_agent_graph 应该是异步函数（返回编译后的图 + AsyncSqliteSaver）"""
        import asyncio
        from core.orchestrator import get_agent_graph
        assert asyncio.iscoroutinefunction(get_agent_graph), "get_agent_graph should be async"


# ============== Test 5: 编辑引擎 ==============

class TestEditEngine:
    """验证 edit_engine.py"""
    
    def test_apply_edits_replace(self):
        """replace 操作应该正确工作"""
        from core.edit_engine import apply_edits
        original = "Hello world, this is a test."
        edits = [{"type": "replace", "anchor": "Hello world", "new_text": "Hi there"}]
        result, changes = apply_edits(original, edits)
        assert result == "Hi there, this is a test."
        assert len(changes) == 1
        assert changes[0]["status"] == "applied"
    
    def test_apply_edits_insert_after(self):
        """insert_after 操作应该正确工作"""
        from core.edit_engine import apply_edits
        original = "Line 1.\nLine 2."
        edits = [{"type": "insert_after", "anchor": "Line 1.", "new_text": "Inserted."}]
        result, changes = apply_edits(original, edits)
        assert "Inserted." in result
        assert result.index("Inserted.") > result.index("Line 1.")
    
    def test_apply_edits_delete(self):
        """delete 操作应该正确工作"""
        from core.edit_engine import apply_edits
        original = "Keep this. Remove this. Keep that."
        edits = [{"type": "delete", "anchor": " Remove this."}]
        result, changes = apply_edits(original, edits)
        assert result == "Keep this. Keep that."
    
    def test_apply_edits_anchor_not_found(self):
        """找不到 anchor 应该标记为 failed"""
        from core.edit_engine import apply_edits
        original = "Hello world."
        edits = [{"type": "replace", "anchor": "nonexistent", "new_text": "X"}]
        result, changes = apply_edits(original, edits)
        assert result == original  # 不应修改
        assert changes[0]["status"] == "failed"
        assert changes[0]["reason"] == "anchor_not_found"
    
    def test_apply_edits_anchor_not_unique(self):
        """anchor 不唯一应该标记为 failed"""
        from core.edit_engine import apply_edits
        original = "word word word"
        edits = [{"type": "replace", "anchor": "word", "new_text": "X"}]
        result, changes = apply_edits(original, edits)
        assert changes[0]["status"] == "failed"
        assert changes[0]["reason"] == "anchor_not_unique"
    
    def test_apply_edits_partial_accept(self):
        """部分接受应该只应用指定的编辑"""
        from core.edit_engine import apply_edits
        original = "A B C"
        edits = [
            {"id": "e0", "type": "replace", "anchor": "A", "new_text": "X"},
            {"id": "e1", "type": "replace", "anchor": "C", "new_text": "Z"},
        ]
        result, changes = apply_edits(original, edits, accepted_ids={"e0"})
        assert result == "X B C"  # 只有 e0 被应用
        assert any(c["status"] == "rejected" for c in changes)
    
    def test_generate_revision_markdown(self):
        """修订 markdown 应该包含 del/ins 标签"""
        from core.edit_engine import generate_revision_markdown
        old = "Line 1\nLine 2\nLine 3\n"
        new = "Line 1\nLine 2 modified\nLine 3\n"
        result = generate_revision_markdown(old, new)
        assert "<del>" in result
        assert "<ins>" in result
        assert "Line 1" in result  # 未改的行应保留


# ============== Test 6: 摘要服务 ==============

class TestDigestService:
    """验证 digest_service.py"""
    
    def test_build_field_index_empty_project(self):
        """空项目应该返回空字符串"""
        from core.digest_service import build_field_index
        result = build_field_index("nonexistent-project-id")
        assert result == ""
    
    def test_trigger_digest_update_doesnt_crash(self):
        """trigger_digest_update 不应崩溃（即使实体不存在）"""
        from core.digest_service import trigger_digest_update
        # 这个函数是非阻塞的，不应抛出异常
        trigger_digest_update("fake-id", "field", "Some content")


# ============== Test 7: 全链路导入完整性 ==============

class TestImportIntegrity:
    """验证删除 ai_client 后所有模块仍能正常导入"""
    
    def test_no_ai_client_imports(self):
        """不应该有任何文件仍导入 ai_client"""
        import os
        import ast
        
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        violations = []
        
        for root, dirs, files in os.walk(backend_dir):
            # 跳过 venv 和测试目录
            dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', '.git')]
            for f in files:
                if not f.endswith('.py'):
                    continue
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            if node.module and 'ai_client' in node.module:
                                violations.append(f"{filepath}: from {node.module} import ...")
                except SyntaxError:
                    pass
        
        assert len(violations) == 0, f"Files still importing ai_client:\n" + "\n".join(violations)
    
    def test_ai_client_file_deleted(self):
        """ai_client.py 应该已被删除"""
        import os
        ai_client_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "ai_client.py"
        )
        assert not os.path.exists(ai_client_path), "ai_client.py should be deleted"
    
    def test_full_app_loads(self):
        """完整的 FastAPI 应用应该能加载"""
        from main import app
        assert app is not None
        assert len(app.routes) > 50  # 应该有很多路由
    
    def test_all_tool_modules_importable(self):
        """所有工具模块应该可以正常导入"""
        from core.tools.field_generator import generate_field
        from core.tools.deep_research import deep_research
        from core.tools.persona_manager import manage_persona
        from core.tools.skill_manager import manage_skill
        from core.tools.outline_generator import generate_outline
        from core.tools.simulator import run_dialogue_simulation
        from core.tools.eval_engine import run_task_trial
        assert all([
            generate_field, deep_research, manage_persona,
            manage_skill, generate_outline,
            run_dialogue_simulation, run_task_trial,
        ])
