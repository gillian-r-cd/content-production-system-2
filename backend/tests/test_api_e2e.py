# backend/tests/test_api_e2e.py
# 功能: 端到端API测试
# 测试完整的项目创建和字段加载流程

"""
端到端API测试
运行: python -m pytest tests/test_api_e2e.py -v
"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """测试客户端"""
    return TestClient(app)


class TestProjectAPI:
    """项目API测试"""

    def test_list_projects(self, client):
        """测试获取项目列表"""
        response = client.get("/api/projects/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_project(self, client):
        """测试创建项目"""
        response = client.post(
            "/api/projects/",
            json={"name": "E2E测试项目"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "E2E测试项目"
        assert data["version"] == 1
        assert data["current_phase"] == "intent"
        assert "id" in data
        return data["id"]

    def test_create_project_validation_error(self, client):
        """测试创建项目时的验证错误"""
        # 空body
        response = client.post("/api/projects/", json={})
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
        # detail应该是一个数组
        assert isinstance(error["detail"], list)
        # 检查错误消息格式
        if len(error["detail"]) > 0:
            assert "msg" in error["detail"][0]

    def test_get_project(self, client):
        """测试获取项目详情"""
        # 先创建一个项目
        create_response = client.post(
            "/api/projects/",
            json={"name": "测试获取详情"}
        )
        project_id = create_response.json()["id"]
        
        # 获取项目详情
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "测试获取详情"


class TestFieldAPI:
    """字段API测试"""

    def test_list_fields_empty(self, client):
        """测试获取空字段列表"""
        # 先创建一个项目
        create_response = client.post(
            "/api/projects/",
            json={"name": "测试字段"}
        )
        project_id = create_response.json()["id"]
        
        # 获取字段列表（应该是空的）
        response = client.get(f"/api/fields/project/{project_id}")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_fields_nonexistent_project(self, client):
        """测试获取不存在项目的字段（应返回空列表）"""
        response = client.get("/api/fields/project/nonexistent-id-12345")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_field(self, client):
        """测试创建字段"""
        # 先创建一个项目
        create_response = client.post(
            "/api/projects/",
            json={"name": "测试创建字段"}
        )
        project_id = create_response.json()["id"]
        
        # 创建字段
        response = client.post(
            "/api/fields/",
            json={
                "project_id": project_id,
                "phase": "intent",
                "name": "核心意图",
                "ai_prompt": "分析项目的核心意图"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "核心意图"
        assert data["phase"] == "intent"
        assert data["status"] == "pending"


class TestHealthCheck:
    """健康检查测试"""

    def test_health(self, client):
        """测试健康检查接口"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

