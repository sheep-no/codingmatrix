"""AJP11：模板上传端点的同步解析不应阻塞事件循环。

`CustomTemplateParser.parse_template_file` 会读取并解析整个 .pptx（上限 20MB），
直接在 async 端点内执行会让事件循环在解析期间冻结。修复后应通过
`asyncio.to_thread` 在线程池中执行。
"""

import threading

import pytest

import app.api.v1.aiGeneratorPptx as pptx_api
from app.utils.pptx import custom_template


class _FakeUpload:
    filename = "t.pptx"

    def __init__(self):
        self._done = False

    async def read(self, size: int = -1) -> bytes:
        if self._done:
            return b""
        self._done = True
        return b"fake-pptx-bytes"


@pytest.mark.asyncio
async def test_upload_custom_template_parses_off_event_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(pptx_api, "BASE_DIR", tmp_path)
    seen = {}

    class _FakeParser:
        def parse_template_file(self, path: str):
            seen["thread"] = threading.current_thread()
            raise RuntimeError("template-offloaded")

    # 端点在函数内导入，patch 包模块属性即可生效
    monkeypatch.setattr(custom_template, "CustomTemplateParser", _FakeParser)

    result = await pptx_api.upload_custom_template(
        file=_FakeUpload(), name="t", token={"sub": "u1"}
    )

    assert result["config"] is None
    assert "template-offloaded" in result["message"]
    assert seen["thread"] is not threading.main_thread()
