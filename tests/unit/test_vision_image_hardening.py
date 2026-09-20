"""vision / image_generation 缺陷回归。

覆盖已建档缺陷：
- VS3 analyze_image 降级只捕获 HTTPException
- VS7 _call_vision_model 无结构防御
- VS4/VS9 check_image_safety 关键词判断脆弱（中英混合失效/否定误报）
- IG1 _save_images_from_response 同步下载阻塞事件循环 + SSRF
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.utils import image_generation as ig
from app.utils import vision
from app.utils.vision import (
    _call_vision_model,
    analyze_image,
    check_image_safety,
)


@pytest.fixture
def image_path(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("model_kwargs", [{}, {"model": None}])
async def test_analyze_image_falls_back_on_non_http_exception(monkeypatch, image_path, model_kwargs):
    calls = []

    async def fake_call(image_base64, prompt, model, timeout):
        calls.append(model)
        if len(calls) == 1:
            raise ValueError("模型返回结构异常")
        return "第二模型描述"

    monkeypatch.setattr(vision, "_call_vision_model", fake_call)

    result = await analyze_image(image_path, **model_kwargs)

    assert len(calls) == 2
    assert result["description"] == "第二模型描述"
    assert result["model_used"] == vision.VISION_MODEL_FALLBACK[1]


@pytest.mark.asyncio
async def test_analyze_image_explicit_model_failure_stays_single_model(monkeypatch, image_path):
    calls = []

    async def fake_call(image_base64, prompt, model, timeout):
        calls.append(model)
        raise ValueError("指定模型调用失败")

    monkeypatch.setattr(vision, "_call_vision_model", fake_call)

    with pytest.raises(HTTPException) as excinfo:
        await analyze_image(image_path, model=vision.VISION_MODEL)

    assert excinfo.value.status_code == 503
    assert calls == [vision.VISION_MODEL]


@pytest.mark.asyncio
async def test_analyze_image_reports_last_error_when_all_fail(monkeypatch, image_path):
    async def fake_call(image_base64, prompt, model, timeout):
        raise KeyError("choices")

    monkeypatch.setattr(vision, "_call_vision_model", fake_call)

    with pytest.raises(HTTPException) as excinfo:
        await analyze_image(image_path, model=None)

    assert excinfo.value.status_code == 503
    assert "choices" in excinfo.value.detail


@pytest.mark.asyncio
async def test_call_vision_model_rejects_malformed_response():
    async def fake_llm_caller(**kwargs):
        return {}

    with pytest.raises(ValueError):
        await _call_vision_model("data:image/png;base64,x", "p", "m", 60.0,
                                 llm_caller=fake_llm_caller)


@pytest.mark.asyncio
async def test_call_vision_model_extracts_content():
    async def fake_llm_caller(**kwargs):
        return {"choices": [{"message": {"content": "描述"}}]}

    result = await _call_vision_model("data:image/png;base64,x", "p", "m", 60.0,
                                      llm_caller=fake_llm_caller)

    assert result == "描述"


@pytest.mark.asyncio
async def test_check_image_safety_trusts_structured_json(monkeypatch, image_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return '{"safe": false, "reason": "包含暴力内容", "flags": ["暴力"]}'

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)

    result = await check_image_safety(image_path)

    assert result["safe"] is False
    assert result["flags"] == ["暴力"]
    assert result["reason"] == "包含暴力内容"


@pytest.mark.asyncio
async def test_check_image_safety_structured_safe(monkeypatch, image_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return '{"safe": true, "reason": "无不当内容", "flags": []}'

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)

    result = await check_image_safety(image_path)

    assert result["safe"] is True
    assert result["flags"] == []


@pytest.mark.asyncio
async def test_check_image_safety_detects_english_unsafe(monkeypatch, image_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return "This image contains violence and blood."

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)

    result = await check_image_safety(image_path)

    assert result["safe"] is False
    assert "violence" in result["flags"]


@pytest.mark.asyncio
async def test_check_image_safety_handles_english_negation(monkeypatch, image_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return "This image does not contain any violence."

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)

    result = await check_image_safety(image_path)

    assert result["safe"] is True


def test_keyword_safety_check_does_not_flag_negated_chinese():
    from app.utils.vision import _keyword_safety_check

    is_safe, flags = _keyword_safety_check("图片不包含暴力和色情内容")

    assert is_safe is True
    assert flags == []


def test_keyword_safety_check_flags_positive_chinese():
    from app.utils.vision import _keyword_safety_check

    is_safe, flags = _keyword_safety_check("图片包含暴力内容")

    assert is_safe is False
    assert "暴力" in flags


@pytest.mark.asyncio
async def test_download_image_bytes_rejects_internal_address():
    with pytest.raises(ValueError):
        await ig._download_image_bytes("http://127.0.0.1/internal.png")


@pytest.mark.asyncio
async def test_save_images_from_response_downloads_via_async_helper(monkeypatch, tmp_path):
    calls = []

    async def fake_download(url, timeout=60.0):
        calls.append(url)
        return b"image-bytes"

    monkeypatch.setattr(ig, "_download_image_bytes", fake_download)
    monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path)

    images, paths = await ig._save_images_from_response(
        {"data": [{"url": "https://example.com/a.png"}]}, "test", "png"
    )

    assert calls == ["https://example.com/a.png"]
    assert images == ["data:image/png;base64," + __import__("base64").b64encode(b"image-bytes").decode()]
    assert paths and paths[0].endswith(".png")
    assert (tmp_path / paths[0].split("/")[-1]).read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_text_to_image_is_awaitable_end_to_end(monkeypatch, tmp_path):
    async def fake_call_kolors(data, timeout, api_key_token=None):
        return {"data": [{"url": "https://example.com/out.png"}]}

    async def fake_download(url, timeout=60.0):
        return b"img"

    monkeypatch.setattr(ig, "_call_kolors_api", fake_call_kolors)
    monkeypatch.setattr(ig, "_download_image_bytes", fake_download)
    monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path)

    result = await ig.text_to_image("a cat")

    assert result["success"] is True
    assert len(result["images"]) == 1
