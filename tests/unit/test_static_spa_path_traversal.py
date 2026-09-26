"""SPA 静态兜底路由的路径穿越回归。

`GET /{full_path:path}` 原先直接 `os.path.join(DIST_PATH, full_path)` 后交给
`FileResponse`。URL 中的 `%2f` 在 httpx/浏览器侧不视为分隔符，Starlette 解码后
`full_path` 变成 `../..`，`join` 结果逃逸出 `src/dist`，可未认证读取任意文件。
本文件锁定修复：静态命中必须 resolve 后仍落在 dist 目录内，否则回落到 index.html。
"""

import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.responses import FileResponse

from app import main


def _prepare_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('APPJS')", encoding="utf-8")
    return dist


@pytest.mark.asyncio
async def test_legit_asset_is_served(tmp_path, monkeypatch):
    dist = _prepare_dist(tmp_path)
    monkeypatch.setattr(main, "DIST_PATH", str(dist))

    response = await main.serve_vue_routes("app.js")

    assert isinstance(response, FileResponse)
    assert Path(response.path) == dist / "app.js"


@pytest.mark.asyncio
async def test_traversal_falls_back_to_index(tmp_path, monkeypatch):
    dist = _prepare_dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-TRAVERSAL-MARKER", encoding="utf-8")
    monkeypatch.setattr(main, "DIST_PATH", str(dist))

    response = await main.serve_vue_routes("../secret.txt")

    assert isinstance(response, FileResponse)
    assert Path(response.path) == dist / "index.html"


@pytest.mark.asyncio
async def test_sibling_prefix_dir_is_not_treated_as_inside(tmp_path, monkeypatch):
    """`dist_evil` 与 `dist` 共享前缀，`startswith` 校验会放行；resolve 后必须拒绝。"""
    dist = _prepare_dist(tmp_path)
    sibling = tmp_path / "dist_evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("SECRET-TRAVERSAL-MARKER", encoding="utf-8")
    monkeypatch.setattr(main, "DIST_PATH", str(dist))

    response = await main.serve_vue_routes("../dist_evil/secret.txt")

    assert Path(response.path) == dist / "index.html"


@pytest.mark.asyncio
async def test_api_paths_are_not_served_by_spa(tmp_path, monkeypatch):
    dist = _prepare_dist(tmp_path)
    monkeypatch.setattr(main, "DIST_PATH", str(dist))

    with pytest.raises(HTTPException) as error:
        await main.serve_vue_routes("api/v1/does-not-exist")

    assert error.value.status_code == 404


def test_encoded_traversal_request_does_not_leak(tmp_path, monkeypatch):
    """端到端复现：`..%2f` 编码使客户端不清洗 `..`，解码后必须被 dist 边界拦截。"""
    dist = _prepare_dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-TRAVERSAL-MARKER", encoding="utf-8")
    monkeypatch.setattr(main, "DIST_PATH", str(dist))

    encoded = os.path.relpath(secret, dist).replace(os.sep, "%2f")
    client = TestClient(main.app)

    response = client.get("/" + encoded)

    assert response.status_code == 200
    assert "SECRET-TRAVERSAL-MARKER" not in response.text
    assert "id=app" in response.text
