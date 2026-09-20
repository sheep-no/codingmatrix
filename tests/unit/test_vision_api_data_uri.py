"""VA1：视觉 API 对畸形 data URI 应返回 400，而非 500。

原先 `image_url.split(",", 1)` 与 `base64.b64decode` 的异常会落入
通用 except 变成 500，客户端无法区分「输入错误」与「服务故障」。
"""

import base64

import pytest
from fastapi import HTTPException

import app.api.v1.vision_api as vision_api


@pytest.mark.asyncio
async def test_data_uri_without_comma_returns_400():
    with pytest.raises(HTTPException) as exc:
        await vision_api.api_analyze_image(
            file=None, image_url="data:image/png;base64", token={"sub": "u"}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_data_uri_invalid_base64_returns_400():
    with pytest.raises(HTTPException) as exc:
        await vision_api.api_analyze_image(
            file=None, image_url="data:image/png;base64,@@@@", token={"sub": "u"}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_data_uri_oversized_returns_400(monkeypatch):
    monkeypatch.setattr(vision_api, "MAX_IMAGE_SIZE", 8)
    payload = base64.b64encode(b"x" * 9).decode()

    with pytest.raises(HTTPException) as exc:
        await vision_api.api_analyze_image(
            file=None, image_url=f"data:image/png;base64,{payload}", token={"sub": "u"}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_valid_data_uri_reaches_analyzer(monkeypatch):
    async def fake_analyze(path, prompt=None, model=None):
        return {"description": "d", "objects": [], "text": "", "model_used": "m"}

    monkeypatch.setattr(vision_api, "analyze_image", fake_analyze)
    payload = base64.b64encode(b"abc").decode()

    response = await vision_api.api_analyze_image(
        file=None, image_url=f"data:image/png;base64,{payload}", token={"sub": "u"}
    )
    assert response.description == "d"
