# backend/tests/test_api_e2e.py
# 功能: 端到端API测试
# 测试完整的项目创建和字段加载流程

"""
端到端API测试
运行: python -m pytest tests/test_api_e2e.py -v
"""

import pytest
import time
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """测试客户端"""
    return TestClient(app)


class TestProjectAPI:
    """项目API测试"""

    def test_cors_allows_loopback_frontend_port_3001(self, client):
        response = client.options(
            "/api/projects/",
            headers={
                "Origin": "http://127.0.0.1:3001",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"

    def test_list_projects(self, client):
        """测试获取项目列表"""
        response = client.get("/api/projects/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_projects_returns_all_projects_by_default(self, client):
        prefix = f"list-default-{time.time_ns()}"
        for idx in range(101):
            response = client.post(
                "/api/projects/",
                json={"name": f"{prefix}-{idx}"}
            )
            assert response.status_code == 200

        response = client.get("/api/projects/")
        assert response.status_code == 200

        matching = [item for item in response.json() if item["name"].startswith(prefix)]
        assert len(matching) == 101

    def test_list_projects_orders_latest_first(self, client):
        prefix = f"list-order-{time.time_ns()}"
        older = client.post("/api/projects/", json={"name": f"{prefix}-older"})
        assert older.status_code == 200
        time.sleep(0.01)
        newer = client.post("/api/projects/", json={"name": f"{prefix}-newer"})
        assert newer.status_code == 200

        response = client.get("/api/projects/")
        assert response.status_code == 200
        names = [
            item["name"]
            for item in response.json()
            if item["name"].startswith(prefix)
        ]
        assert names[:2] == [f"{prefix}-newer", f"{prefix}-older"]

    def test_batch_delete_projects_relinks_remaining_version_chain(self, client):
        prefix = f"batch-delete-chain-{time.time_ns()}"
        root_response = client.post("/api/projects/", json={"name": f"{prefix}-root"})
        assert root_response.status_code == 200
        root = root_response.json()

        middle_response = client.post(
            f"/api/projects/{root['id']}/versions",
            json={"version_note": "middle"},
        )
        assert middle_response.status_code == 200
        middle = middle_response.json()

        leaf_response = client.post(
            f"/api/projects/{middle['id']}/versions",
            json={"version_note": "leaf"},
        )
        assert leaf_response.status_code == 200
        leaf = leaf_response.json()

        response = client.post(
            "/api/projects/batch-delete",
            json={"project_ids": [root["id"], middle["id"]]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_count"] == 2
        assert set(payload["deleted_ids"]) == {root["id"], middle["id"]}

        remaining_leaf = client.get(f"/api/projects/{leaf['id']}")
        assert remaining_leaf.status_code == 200
        assert remaining_leaf.json()["parent_version_id"] is None

        assert client.get(f"/api/projects/{root['id']}").status_code == 404
        assert client.get(f"/api/projects/{middle['id']}").status_code == 404

    def test_batch_delete_projects_is_atomic_when_any_project_is_missing(self, client):
        prefix = f"batch-delete-atomic-{time.time_ns()}"
        first = client.post("/api/projects/", json={"name": f"{prefix}-first"})
        second = client.post("/api/projects/", json={"name": f"{prefix}-second"})
        assert first.status_code == 200
        assert second.status_code == 200

        response = client.post(
            "/api/projects/batch-delete",
            json={"project_ids": [first.json()["id"], "missing-project-id", second.json()["id"]]},
        )
        assert response.status_code == 404

        listed = client.get("/api/projects/")
        assert listed.status_code == 200
        remaining_ids = {item["id"] for item in listed.json()}
        assert first.json()["id"] in remaining_ids
        assert second.json()["id"] in remaining_ids

    def test_create_project(self, client):
        """测试创建项目"""
        response = client.post(
            "/api/projects/",
            json={"name": "E2E测试项目"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "E2E测试项目"
        assert data["locale"] == "zh-CN"
        assert data["version"] == 1
        assert data["current_phase"] == "intent"
        assert "id" in data
        return data["id"]

    def test_create_project_with_locale(self, client):
        response = client.post(
            "/api/projects/",
            json={"name": "JP项目", "locale": "ja-JP"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "JP项目"
        assert data["locale"] == "ja-JP"

    def test_duplicate_project_preserves_locale(self, client):
        create_response = client.post(
            "/api/projects/",
            json={"name": "复制源项目", "locale": "ja-JP"}
        )
        assert create_response.status_code == 200
        project_id = create_response.json()["id"]

        duplicate_response = client.post(f"/api/projects/{project_id}/duplicate")
        assert duplicate_response.status_code == 200
        duplicated = duplicate_response.json()
        assert duplicated["locale"] == "ja-JP"
        assert duplicated["name"] == "复制源项目（コピー）"
        assert duplicated["version_note"] == "プロジェクトを複製して作成"

    def test_create_new_version_preserves_locale(self, client):
        create_response = client.post(
            "/api/projects/",
            json={"name": "版本源项目", "locale": "ja-JP"}
        )
        assert create_response.status_code == 200
        project = create_response.json()

        version_response = client.post(
            f"/api/projects/{project['id']}/versions",
            json={"version_note": "locale keep"}
        )
        assert version_response.status_code == 200
        new_version = version_response.json()
        assert new_version["locale"] == "ja-JP"
        assert new_version["version"] == project["version"] + 1

    def test_export_import_project_preserves_locale(self, client):
        create_response = client.post(
            "/api/projects/",
            json={"name": "导入导出项目", "locale": "ja-JP"}
        )
        assert create_response.status_code == 200
        project = create_response.json()

        export_response = client.get(f"/api/projects/{project['id']}/export")
        assert export_response.status_code == 200
        payload = export_response.json()
        assert payload["project"]["locale"] == "ja-JP"

        import_response = client.post("/api/projects/import", json={"data": payload})
        assert import_response.status_code == 200
        imported = import_response.json()
        assert imported["locale"] == "ja-JP"

    def test_import_project_localizes_default_version_note_for_ja_locale(self, client):
        create_response = client.post(
            "/api/projects/",
            json={"name": "日本語インポート", "locale": "ja-JP"}
        )
        assert create_response.status_code == 200
        project = create_response.json()

        export_response = client.get(f"/api/projects/{project['id']}/export")
        assert export_response.status_code == 200
        payload = export_response.json()
        payload["project"].pop("version_note", None)

        import_response = client.post("/api/projects/import", json={"data": payload})
        assert import_response.status_code == 200
        imported = import_response.json()
        assert imported["locale"] == "ja-JP"
        assert imported["version_note"] == "エクスポートファイルからインポート"
        assert imported["message"] == f"プロジェクト「{imported['name']}」をインポートしました"

    def test_apply_template_prefers_project_locale_variant(self, client):
        project_response = client.post(
            "/api/projects/",
            json={"name": "模板语言项目", "locale": "ja-JP"}
        )
        assert project_response.status_code == 200
        project = project_response.json()

        zh_template_response = client.post(
            "/api/settings/field-templates",
            json={
                "name": "中文模板",
                "stable_key": "template.locale.demo",
                "locale": "zh-CN",
                "root_nodes": [
                    {
                        "template_node_id": "intro-node",
                        "name": "中文摘要",
                        "block_type": "field",
                        "ai_prompt": "请生成中文摘要",
                        "children": [],
                    }
                ],
            },
        )
        assert zh_template_response.status_code == 200
        zh_template = zh_template_response.json()

        ja_template_response = client.post(
            "/api/settings/field-templates",
            json={
                "name": "日本語テンプレート",
                "stable_key": "template.locale.demo",
                "locale": "ja-JP",
                "root_nodes": [
                    {
                        "template_node_id": "intro-node",
                        "name": "日本語概要",
                        "block_type": "field",
                        "ai_prompt": "日本語の概要を生成してください",
                        "children": [],
                    }
                ],
            },
        )
        assert ja_template_response.status_code == 200

        apply_response = client.post(
            f"/api/blocks/project/{project['id']}/apply-template",
            params={"template_id": zh_template["id"]},
        )
        assert apply_response.status_code == 200

        tree_response = client.get(f"/api/blocks/project/{project['id']}")
        assert tree_response.status_code == 200
        tree = tree_response.json()
        block_names = [block["name"] for block in tree.get("blocks", [])]
        assert "日本語概要" in block_names
        assert "中文摘要" not in block_names

    def test_apply_phase_template_prefers_project_locale_variant(self, client):
        project_response = client.post(
            "/api/projects/",
            json={"name": "流程模板语言项目", "locale": "ja-JP"}
        )
        assert project_response.status_code == 200
        project = project_response.json()

        zh_template_response = client.post(
            "/api/phase-templates/",
            json={
                "name": "中文流程模板",
                "stable_key": "phase.template.locale.demo",
                "locale": "zh-CN",
                "root_nodes": [
                    {
                        "template_node_id": "group-node",
                        "name": "中文分组",
                        "block_type": "group",
                        "children": [
                            {
                                "template_node_id": "field-node",
                                "name": "中文流程摘要",
                                "block_type": "field",
                                "ai_prompt": "请生成中文流程摘要",
                                "children": [],
                            }
                        ],
                    }
                ],
            },
        )
        assert zh_template_response.status_code == 200
        zh_template = zh_template_response.json()

        ja_template_response = client.post(
            "/api/phase-templates/",
            json={
                "name": "日本語フローテンプレート",
                "stable_key": "phase.template.locale.demo",
                "locale": "ja-JP",
                "root_nodes": [
                    {
                        "template_node_id": "group-node",
                        "name": "日本語グループ",
                        "block_type": "group",
                        "children": [
                            {
                                "template_node_id": "field-node",
                                "name": "日本語フロー概要",
                                "block_type": "field",
                                "ai_prompt": "日本語のフロー概要を生成してください",
                                "children": [],
                            }
                        ],
                    }
                ],
            },
        )
        assert ja_template_response.status_code == 200
        assert ja_template_response.json()["locale"] == "ja-JP"

        apply_response = client.post(
            f"/api/blocks/project/{project['id']}/apply-template",
            params={"template_id": zh_template["id"]},
        )
        assert apply_response.status_code == 200
        assert apply_response.json()["message"] == "テンプレート「日本語フローテンプレート」を適用しました"

        tree_response = client.get(f"/api/blocks/project/{project['id']}")
        assert tree_response.status_code == 200
        tree = tree_response.json()
        def collect_names(blocks):
            names = []
            for block in blocks:
                names.append(block["name"])
                names.extend(collect_names(block.get("children", [])))
            return names

        block_names = collect_names(tree.get("blocks", []))
        assert "日本語フロー概要" in block_names
        assert "中文流程摘要" not in block_names

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


