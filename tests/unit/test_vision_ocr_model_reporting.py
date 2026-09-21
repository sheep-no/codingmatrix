"""VA2：`/vision/ocr` 应上报实际使用的 OCR 模型，而非硬编码名称。

原先固定返回 "deepseek-ai/DeepSeek-OCR"，与配置中的 OCR 默认模型脱节：
统一模型配置改换 OCR 模型后，接口仍谎报旧模型名。
"""

import pytest

import app.api.v1.vision_api as vision_api


class _FakeUpload:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


@pytest.mark.asyncio
async def test_ocr_reports_configured_model(monkeypatch):
    async def fake_extract(image_path):
        return "识别文本"

    monkeypatch.setattr(vision_api, "extract_text_from_image", fake_extract)
    monkeypatch.setattr(vision_api, "OCR_MODEL", "custom/ocr-model")

    response = await vision_api.api_ocr(
        file=_FakeUpload("sample.png", b"fake-image-bytes"),
        token={"sub": "u"},
    )

    assert response.text == "识别文本"
    assert response.model_used == "custom/ocr-model"
