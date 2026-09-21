"""AJP11：PPT 上传端点的同步解析不应阻塞事件循环。

`parse_document`（文件上传）与 `parse_template_file`（模板上传）都是 CPU/IO
密集的同步调用，直接在 async 端点内执行会让整个事件循环在大文件解析期间
冻结。修复后应通过 `asyncio.to_thread` 在线程池中执行。
"""

import threading

import pytest
from fastapi import HTTPException

import app.api.v1.aiGeneratorPptx as pptx_api
from app.utils.aicloud import knowledge_processor
from app.utils.pptx import custom_template


class _FakeUpload:
    """最小化的 UploadFile 替身：单次返回一小段内容后结束。"""

    def __init__(self, filename: str, payload: bytes = b"hello world"):
        self.filename = filename
        self._payload = payload
        self._done = False

    async def read(self, size: int = -1) -> bytes:
        if self._done:
            return b""
        self._done = True
        return self._payload


@pytest.mark.asyncio
async def test_generate_from_file_parses_off_event_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_parse(path: str) -> str:
        seen["thread"] = threading.current_thread()
        raise HTTPException(status_code=418, detail="parse-offloaded")

    # 端点在函数内导入，patch 包模块属性即可生效
    monkeypatch.setattr(knowledge_processor, "parse_document", fake_parse)

    with pytest.raises(HTTPException) as exc:
        await pptx_api.generate_ppt_from_file(
            file=_FakeUpload("demo.md"), token={"sub": "u1"}
        )

    assert exc.value.status_code == 418
    assert seen["thread"] is not threading.main_thread()


@pytest.mark.asyncio
async def test_upload_custom_template_parses_off_event_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    class _FakeParser:
        def parse_template_file(self, path: str):
            seen["thread"] = threading.current_thread()
            raise RuntimeError("template-offloaded")

    monkeypatch.setattr(custom_template, "CustomTemplateParser", _FakeParser)

    result = await pptx_api.upload_custom_template(
        file=_FakeUpload("t.pptx"), name="t", token={"sub": "u1"}
    )

    assert result["config"] is None
    assert "template-offloaded" in result["message"]
    assert seen["thread"] is not threading.main_thread()
