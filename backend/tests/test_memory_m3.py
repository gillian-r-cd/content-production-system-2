# backend/tests/test_memory_m3.py
# 功能: M3 里程碑验证测试 — Memory CRUD API + 全局记忆 + 合并/筛选逻辑
# 主要测试:
#   1. Memory CRUD API（M3-1: 增删改查）
#   2. 全局记忆（M3-5: project_id=NULL / _global）
#   3. 记忆去重、合并阈值、筛选阈值单元逻辑（M3-3 / M3-4）
#   4. load_memory_context 包含全局记忆（M3-5 + M2 联动）
# 运行: cd backend && .\venv\Scripts\python -m pytest tests/test_memory_m3.py -v

"""
M3 里程碑验证测试

测试策略：
- API 层使用 httpx 直接请求本地 FastAPI 服务（需要 backend 已启动）
- 单元层直接导入 memory_service 函数
- 每个测试负责清理自己创建的数据
- 不 mock LLM（合并/筛选的 LLM 调用仅在超阈值时触发，测试不触发）
"""

import sys
import os
import asyncio

# 确保 backend 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest

BASE_URL = "http://localhost:8000"
TIMEOUT = 30.0


# ============== Fixtures ==============

@pytest.fixture(scope="module")
def client():
    """httpx 同步客户端（禁用代理，使用宽裕超时）"""
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, proxy=None) as c:
        yield c


@pytest.fixture(scope="module")
def project_id(client):
    """获取一个已有的项目 ID"""
    resp = client.get("/api/projects/")
    assert resp.status_code == 200, f"GET /api/projects/ failed: {resp.text}"
    projects = resp.json()
    assert len(projects) > 0, "No projects found — please create at least one project first"
    return projects[0]["id"]


# ============== M3-1: Memory CRUD API ==============

class TestMemoryCRUD:
    """验证 /api/memories/ 端点的增删改查"""

    def test_create_and_list(self, client, project_id):
        """创建一条项目记忆，列表应包含它"""
        # 创建
        resp = client.post(f"/api/memories/{project_id}", json={
            "content": "M3测试：用户偏好极简风格",
            "source_mode": "manual",
            "source_phase": "",
            "related_blocks": ["场景库"],
        })
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        mem = resp.json()
        mem_id = mem["id"]
        assert mem["project_id"] == project_id
        assert mem["content"] == "M3测试：用户偏好极简风格"
        assert mem["source_mode"] == "manual"
        assert mem["related_blocks"] == ["场景库"]
        assert mem["created_at"]  # 不为空
        assert mem["updated_at"]  # 不为空

        try:
            # 列表
            resp2 = client.get(f"/api/memories/{project_id}")
            assert resp2.status_code == 200
            items = resp2.json()
            ids = [m["id"] for m in items]
            assert mem_id in ids, f"Created memory not found in list: {ids}"
            print(f"✅ Create + List OK — id={mem_id}")
        finally:
            # 清理
            client.delete(f"/api/memories/{project_id}/{mem_id}")

    def test_get_single(self, client, project_id):
        """获取单条记忆"""
        # 先创建
        resp = client.post(f"/api/memories/{project_id}", json={
            "content": "M3测试：获取单条",
        })
        mem_id = resp.json()["id"]

        try:
            resp2 = client.get(f"/api/memories/{project_id}/{mem_id}")
            assert resp2.status_code == 200
            detail = resp2.json()
            assert detail["id"] == mem_id
            assert detail["content"] == "M3测试：获取单条"
            print(f"✅ Get single OK — id={mem_id}")
        finally:
            client.delete(f"/api/memories/{project_id}/{mem_id}")

    def test_update(self, client, project_id):
        """更新记忆内容"""
        resp = client.post(f"/api/memories/{project_id}", json={
            "content": "M3测试：原始内容",
            "related_blocks": ["A"],
        })
        mem_id = resp.json()["id"]

        try:
            resp2 = client.put(f"/api/memories/{project_id}/{mem_id}", json={
                "content": "M3测试：已更新内容",
                "related_blocks": ["A", "B"],
            })
            assert resp2.status_code == 200
            updated = resp2.json()
            assert updated["content"] == "M3测试：已更新内容"
            assert updated["related_blocks"] == ["A", "B"]
            print(f"✅ Update OK — id={mem_id}")
        finally:
            client.delete(f"/api/memories/{project_id}/{mem_id}")

    def test_delete(self, client, project_id):
        """删除记忆"""
        resp = client.post(f"/api/memories/{project_id}", json={
            "content": "M3测试：即将删除",
        })
        mem_id = resp.json()["id"]

        resp2 = client.delete(f"/api/memories/{project_id}/{mem_id}")
        assert resp2.status_code == 200
        assert resp2.json()["message"] == "Memory deleted"

        # 确认已删除
        resp3 = client.get(f"/api/memories/{project_id}/{mem_id}")
        assert resp3.status_code == 404
        print(f"✅ Delete OK — id={mem_id}")

    def test_create_empty_content_rejected(self, client, project_id):
        """空内容应被拒绝"""
        resp = client.post(f"/api/memories/{project_id}", json={
            "content": "   ",  # 全空格
        })
        assert resp.status_code == 400
        print("✅ Empty content rejected (400)")

    def test_get_nonexistent_returns_404(self, client, project_id):
        """查询不存在的记忆应返回 404"""
        resp = client.get(f"/api/memories/{project_id}/nonexistent-id-12345")
        assert resp.status_code == 404
        print("✅ Nonexistent memory returns 404")


# ============== M3-5: 全局记忆 ==============

class TestGlobalMemory:
    """验证 project_id=NULL 的全局记忆功能"""

    def test_create_global_memory(self, client):
        """通过 _global 创建全局记忆，project_id 应为 null"""
        resp = client.post("/api/memories/_global", json={
            "content": "M3测试：全局偏好 - 简洁风格",
            "source_mode": "manual",
        })
        assert resp.status_code == 200, f"Create global failed: {resp.text}"
        mem = resp.json()
        assert mem["project_id"] is None, f"Global memory should have null project_id, got: {mem['project_id']}"
        global_id = mem["id"]

        try:
            # _global 列表应包含它
            resp2 = client.get("/api/memories/_global")
            assert resp2.status_code == 200
            items = resp2.json()
            ids = [m["id"] for m in items]
            assert global_id in ids
            print(f"✅ Global memory created and listed — id={global_id}")
        finally:
            client.delete(f"/api/memories/_global/{global_id}")

    def test_include_global_flag(self, client, project_id):
        """include_global=true 时项目列表应同时包含全局记忆"""
        # 创建一条全局记忆
        resp_g = client.post("/api/memories/_global", json={
            "content": "M3测试全局：通用规则ABC",
        })
        global_id = resp_g.json()["id"]

        # 创建一条项目记忆
        resp_p = client.post(f"/api/memories/{project_id}", json={
            "content": "M3测试项目：特定需求XYZ",
        })
        proj_mem_id = resp_p.json()["id"]

        try:
            # 不含全局
            resp1 = client.get(f"/api/memories/{project_id}")
            items1 = resp1.json()
            ids1 = [m["id"] for m in items1]
            assert proj_mem_id in ids1
            assert global_id not in ids1, "全局记忆不应出现在不带 include_global 的列表中"

            # 含全局
            resp2 = client.get(f"/api/memories/{project_id}", params={"include_global": "true"})
            items2 = resp2.json()
            ids2 = [m["id"] for m in items2]
            assert proj_mem_id in ids2
            assert global_id in ids2, "include_global=true 时应包含全局记忆"

            print(f"✅ include_global flag OK — project:{len(items1)}, project+global:{len(items2)}")
        finally:
            client.delete(f"/api/memories/{project_id}/{proj_mem_id}")
            client.delete(f"/api/memories/_global/{global_id}")

    def test_global_memory_in_load_context(self):
        """load_memory_context 应同时加载项目记忆和全局记忆"""
        from core.memory_service import load_memory_context
        from core.database import get_db
        from core.models.memory_item import MemoryItem
        from core.models import generate_uuid

        test_pid = "test-global-ctx-001"

        db = next(get_db())
        try:
            # 清理
            db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
            db.commit()

            # 创建项目记忆
            mem_proj = MemoryItem(
                id=generate_uuid(),
                project_id=test_pid,
                content="项目级别记忆：使用幽默语气",
                source_mode="assistant",
                source_phase="intent",
                related_blocks=[],
            )
            # 创建全局记忆
            mem_global = MemoryItem(
                id=generate_uuid(),
                project_id=None,  # 全局
                content="全局记忆：每段开头用问句",
                source_mode="manual",
                source_phase="",
                related_blocks=[],
            )
            db.add_all([mem_proj, mem_global])
            db.commit()

            global_id = mem_global.id
        finally:
            db.close()

        try:
            ctx = load_memory_context(test_pid)
            assert "项目级别记忆：使用幽默语气" in ctx, f"Project memory missing from context: {ctx}"
            assert "全局记忆：每段开头用问句" in ctx, f"Global memory missing from context: {ctx}"
            assert "[全局]" in ctx, f"Global prefix missing from context: {ctx}"
            print(f"✅ load_memory_context includes global memories:\n{ctx}")
        finally:
            # 清理
            db = next(get_db())
            try:
                db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
                db.query(MemoryItem).filter(MemoryItem.id == global_id).delete()
                db.commit()
            finally:
                db.close()


# ============== M3-3 / M3-4: 合并和筛选逻辑单元测试 ==============

class TestConsolidationAndFilter:
    """验证合并和筛选的阈值逻辑（不触发 LLM，只验证低于阈值时的行为）"""

    def test_consolidate_below_threshold_noop(self):
        """记忆数 ≤ CONSOLIDATE_THRESHOLD 时不执行合并"""
        from core.memory_service import consolidate_memories, CONSOLIDATE_THRESHOLD
        from core.database import get_db
        from core.models.memory_item import MemoryItem
        from core.models import generate_uuid

        test_pid = "test-consolidate-001"

        db = next(get_db())
        try:
            db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
            db.commit()

            # 插入少于阈值的记忆
            for i in range(3):
                db.add(MemoryItem(
                    id=generate_uuid(),
                    project_id=test_pid,
                    content=f"合并测试记忆{i}",
                    source_mode="assistant",
                    source_phase="",
                    related_blocks=[],
                ))
            db.commit()
        finally:
            db.close()

        try:
            result = asyncio.run(consolidate_memories(test_pid))
            assert result == 0, f"Should be 0 (below threshold), got {result}"
            print(f"✅ consolidate below threshold = noop (CONSOLIDATE_THRESHOLD={CONSOLIDATE_THRESHOLD})")
        finally:
            db = next(get_db())
            try:
                db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
                db.commit()
            finally:
                db.close()

    def test_filter_below_threshold_returns_all(self):
        """记忆数 ≤ FILTER_THRESHOLD 时返回全部索引"""
        from core.memory_service import filter_memories_by_relevance, FILTER_THRESHOLD

        # 构造少于阈值的记忆
        lines = [(i, f"记忆{i}: 测试内容") for i in range(10)]

        result = asyncio.run(
            filter_memories_by_relevance(lines, mode="assistant", phase="intent")
        )
        assert result == list(range(10)), f"Should return all indices, got {result}"
        print(f"✅ filter below threshold returns all (FILTER_THRESHOLD={FILTER_THRESHOLD})")

    def test_save_memories_dedup_integration(self):
        """save_memories 集成去重验证"""
        from core.memory_service import save_memories
        from core.database import get_db
        from core.models.memory_item import MemoryItem

        test_pid = "test-save-dedup-001"

        # 清理
        db = next(get_db())
        try:
            db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
            db.commit()
        finally:
            db.close()

        try:
            # 第一次保存
            saved1 = asyncio.run(save_memories(
                test_pid, "assistant", "intent",
                [
                    {"content": "去重测试记忆A", "related_blocks": []},
                    {"content": "去重测试记忆B", "related_blocks": ["场景库"]},
                ]
            ))
            assert saved1 == 2, f"First save: expected 2, got {saved1}"

            # 第二次保存完全相同的内容 → 应被去重
            saved2 = asyncio.run(save_memories(
                test_pid, "critic", "content_core",
                [
                    {"content": "去重测试记忆A", "related_blocks": []},
                    {"content": "去重测试记忆B", "related_blocks": ["场景库"]},
                ]
            ))
            assert saved2 == 0, f"Second save (dedup): expected 0, got {saved2}"

            # 第三次保存不同内容 → 应保存
            saved3 = asyncio.run(save_memories(
                test_pid, "creative", "intent",
                [
                    {"content": "去重测试记忆C（全新）", "related_blocks": []},
                ]
            ))
            assert saved3 == 1, f"Third save: expected 1, got {saved3}"

            print("✅ save_memories dedup integration OK (2 → 0 → 1)")
        finally:
            db = next(get_db())
            try:
                db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
                db.commit()
            finally:
                db.close()

    def test_load_memory_context_async(self):
        """load_memory_context_async 基础验证"""
        from core.memory_service import load_memory_context_async
        from core.database import get_db
        from core.models.memory_item import MemoryItem
        from core.models import generate_uuid

        test_pid = "test-async-load-001"

        db = next(get_db())
        try:
            db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
            db.commit()
            db.add(MemoryItem(
                id=generate_uuid(),
                project_id=test_pid,
                content="异步加载测试记忆",
                source_mode="assistant",
                source_phase="intent",
                related_blocks=["模块A"],
            ))
            db.commit()
        finally:
            db.close()

        try:
            ctx = asyncio.run(load_memory_context_async(test_pid, mode="assistant", phase="intent"))
            assert "异步加载测试记忆" in ctx, f"Memory not in async context: {ctx}"
            assert "assistant" in ctx
            print(f"✅ load_memory_context_async OK:\n{ctx}")
        finally:
            db = next(get_db())
            try:
                db.query(MemoryItem).filter(MemoryItem.project_id == test_pid).delete()
                db.commit()
            finally:
                db.close()


# ============== 入口 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])



