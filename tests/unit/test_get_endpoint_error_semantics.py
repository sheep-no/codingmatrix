"""GET 端点不得因「资源不存在 / 结果为空 / 可选依赖缺失」返回 500。

运行时冒烟（对全部非 Agent GET 端点做占位参数探测）发现两处 500：

- `GET /api/v1/aicloud/history`：空结果返回 `None`，而 `response_model`
  是单个 `SessionResponse`，FastAPI 序列化报
  `model_attributes_type ... input: None` 后抛 500。前端 `getHistory`
  本就按数组消费（`sessions.find`），响应也应为列表。
- `GET /api/v1/pptx/templates/{id}/preview/{page}`：未知模板让
  `TemplateManager.select_template` 的 `KeyError` 冒泡成 500；同一个
  未解析的 id 还会传给 `_paths`，使别名（`business` → `business_report`）
  命中错误目录而误报「样张暂不可用」。
- `GET /api/v2/Controller/admin/docker/containers`：Docker SDK 属可选依赖
  （未列入 requirements.txt），缺失时被泛化的 `except Exception` 转成 500
  `INTERNAL_ERROR`。依赖不可用应报 503。
"""

import sys

import pytest
from fastapi import HTTPException

from app.api.v1 import aiGeneratorPptx, aicloud
from app.api.v2 import guardian_router
from app.schema.aicloud import SessionResponse


class _EmptyScalars:
    def scalars(self):
        return self

    def all(self):
        return []


class _EmptyDB:
    """空库：execute 返回空结果集。"""

    async def execute(self, *args, **kwargs):
        return _EmptyScalars()


@pytest.mark.asyncio
async def test_aicloud_history_returns_empty_list(monkeypatch):
    """空结果必须是 []，而不是无法序列化的 None。"""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(aicloud, "check_aicloud_permission", _noop)

    result = await aicloud.get_history(days=1, limit=10, offset=0, db=_EmptyDB(), user_id=1)

    assert result == []


def test_aicloud_history_response_model_is_list():
    """response_model 必须是列表，返回单个对象或 None 都不满足它。"""
    from typing import get_origin

    route = next(r for r in aicloud.router.routes if getattr(r, "path", None) == "/aicloud/history")

    assert get_origin(route.response_model) is list
    assert route.response_model.__args__ == (SessionResponse,)


@pytest.mark.asyncio
async def test_template_preview_unknown_id_returns_404():
    """未知模板是请求侧问题，返回 404 而非 500。"""
    with pytest.raises(HTTPException) as exc:
        await aiGeneratorPptx.get_template_sample("probe-nonexistent", 1)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_template_preview_resolves_alias_before_locating_sample(monkeypatch, tmp_path):
    """别名须在定位样张目录前解析，否则 ensure 与 _paths 命中不同目录。"""
    from app.services import ppt_template_samples

    captured = {}

    async def fake_ensure(template_id):
        captured["ensure"] = template_id
        return {}

    def fake_paths(template_id):
        captured["paths"] = template_id
        return {"png_dir": tmp_path}

    monkeypatch.setattr(ppt_template_samples, "ensure_template_sample", fake_ensure)
    monkeypatch.setattr(ppt_template_samples, "_paths", fake_paths)
    (tmp_path / "slide-1.png").write_bytes(b"\x89PNG\r\n")

    response = await aiGeneratorPptx.get_template_sample("business", 1)

    assert captured == {"ensure": "business_report", "paths": "business_report"}
    assert str(response.path) == str(tmp_path / "slide-1.png")


@pytest.mark.asyncio
async def test_docker_containers_missing_sdk_returns_503(monkeypatch):
    """可选依赖缺失是服务不可用（503），而不是内部错误（500）。"""
    # sys.modules 中置 None 会让 `import docker` 抛 ImportError
    monkeypatch.setitem(sys.modules, "docker", None)

    with pytest.raises(HTTPException) as exc:
        await guardian_router.list_docker_containers(token={"sub": "1"})

    assert exc.value.status_code == 503
