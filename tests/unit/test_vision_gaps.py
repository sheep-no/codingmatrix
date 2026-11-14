"""vision 图片读取、结构解析与安全判定边界补测。"""

import json

import pytest

from app.utils import vision
from app.utils.vision import (
    _call_vision_model,
    _extract_json_object,
    check_image_safety,
    extract_text_from_image,
    generate_code_from_image,
    image_to_base64,
)


def test_missing_image_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        image_to_base64(str(tmp_path / "missing.png"))


def test_oversized_image_raises(tmp_path, monkeypatch):
    path = tmp_path / "big.png"
    path.write_bytes(b"x" * 16)
    monkeypatch.setattr(vision, "MAX_IMAGE_SIZE", 8)

    with pytest.raises(ValueError, match="过大"):
        image_to_base64(str(path))


def test_unsupported_format_raises(tmp_path):
    path = tmp_path / "image.txt"
    path.write_bytes(b"x")

    with pytest.raises(ValueError, match="格式"):
        image_to_base64(str(path))


def test_jpg_uses_jpeg_mime(tmp_path):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"abc")

    assert image_to_base64(str(path)).startswith("data:image/jpeg;base64,")


def test_uppercase_extension_is_normalized(tmp_path):
    path = tmp_path / "image.PNG"
    path.write_bytes(b"abc")

    assert image_to_base64(str(path)).startswith("data:image/png;base64,")


async def test_call_vision_model_uses_default_caller(monkeypatch):
    import app.utils

    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(app.utils, "call_llm", fake_call_llm)

    result = await _call_vision_model("data:image/png;base64,abc", "prompt", "m", 60.0)

    assert result == "ok"
    assert captured["timeout"] == 60.0


async def test_call_vision_model_rejects_non_dict_result():
    async def fake(**kwargs):
        return ["not", "a", "dict"]

    with pytest.raises(ValueError, match="list"):
        await _call_vision_model("img", "p", "m", 60.0, llm_caller=fake)


async def test_call_vision_model_rejects_empty_choices():
    async def fake(**kwargs):
        return {"choices": []}

    with pytest.raises(ValueError):
        await _call_vision_model("img", "p", "m", 60.0, llm_caller=fake)


async def test_call_vision_model_rejects_missing_message():
    async def fake(**kwargs):
        return {"choices": [{"text": "x"}]}

    with pytest.raises(ValueError):
        await _call_vision_model("img", "p", "m", 60.0, llm_caller=fake)


async def test_call_vision_model_handles_non_dict_choice():
    async def fake(**kwargs):
        return {"choices": ["bad"]}

    with pytest.raises(ValueError):
        await _call_vision_model("img", "p", "m", 60.0, llm_caller=fake)


async def test_extract_text_delegates_to_analyze_image(monkeypatch, tmp_path):
    captured = {}

    async def fake_analyze(image_path, prompt, model):
        captured.update(image=image_path, prompt=prompt, model=model)
        return {"text": "识别文字"}

    monkeypatch.setattr(vision, "analyze_image", fake_analyze)

    text = await extract_text_from_image(str(tmp_path / "a.png"))

    assert text == "识别文字"
    assert captured["model"] == vision.OCR_MODEL


async def test_generate_code_from_image(monkeypatch, tmp_path):
    calls = []

    async def fake_analyze(image_path, prompt, model):
        calls.append(("vision", model))
        return {"description": "登录界面"}

    async def fake_call_llm(**kwargs):
        calls.append(("code", kwargs["model"]))
        return "<div>login</div>"

    import app.utils

    monkeypatch.setattr(vision, "analyze_image", fake_analyze)
    monkeypatch.setattr(app.utils, "call_llm", fake_call_llm)

    result = await generate_code_from_image(str(tmp_path / "ui.png"), requirement="暗色主题")

    assert result["description"] == "登录界面"
    assert result["raw_description"] == "<div>login</div>"
    assert calls[0][0] == "vision"
    assert calls[1] == ("code", vision.DEFAULT_CODE_MODEL)


def test_extract_json_object_skips_arrays_and_bad_braces():
    assert _extract_json_object("no json") is None
    assert _extract_json_object('[{}, {"a": 1}]') == {}
    assert _extract_json_object('noise {"a": 1}') == {"a": 1}
    assert _extract_json_object('prefix {"x": 1} suffix') == {"x": 1}


def test_extract_json_object_handles_invalid_first_brace():
    assert _extract_json_object('{bad} then {"ok": true}') == {"ok": True}


async def test_check_image_safety_adds_review_flag_when_unsafe_without_flags(monkeypatch, tmp_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return json.dumps({"safe": False, "reason": "可疑"})

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)
    path = tmp_path / "a.png"
    path.write_bytes(b"x")

    result = await check_image_safety(str(path))

    assert result["flags"] == ["需要人工审核"]
    assert result["reason"] == "可疑"


async def test_check_image_safety_ignores_non_bool_safe(monkeypatch, tmp_path):
    async def fake_vision(image_base64, prompt, model, timeout):
        return '{"safe": "yes", "reason": "x"}'

    monkeypatch.setattr(vision, "_call_vision_model", fake_vision)
    path = tmp_path / "a.png"
    path.write_bytes(b"x")

    result = await check_image_safety(str(path))

    assert result["safe"] is True
    assert result["reason"] == '{"safe": "yes", "reason": "x"}'


def test_keyword_safety_ignores_negated_mentions():
    safe, flags = vision._keyword_safety_check("这张图不含暴力，也没有色情内容")
    assert safe is True
    assert flags == []


def test_keyword_safety_flags_positive_mention():
    safe, flags = vision._keyword_safety_check("画面包含 violence")
    assert safe is False
    assert flags == ["violence"]
