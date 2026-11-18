"""API 路由别名与兜底行为。"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_unknown_api_path_returns_json_404():
    """未知 API 路径返回 JSON 404，不落到 SPA。"""
    response = client.get("/api/v1/definitely-missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "NOT_FOUND"


def test_workflow_stream_alias_is_registered():
    """客户端使用的 /workflow/stream 与 /orchestrate/stream 指向同一实现。"""
    registered = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", ())
    }
    for path in (
        "/api/v1/agent/workflow/stream",
        "/api/v1/agent/orchestrate/stream",
    ):
        assert (path, "POST") in registered


def test_api_root_without_slash_is_not_spa():
    """/api 本身不能返回前端首页。"""
    response = client.get("/api")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
