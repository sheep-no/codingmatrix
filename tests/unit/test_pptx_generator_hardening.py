"""AJP6/AJP10/AJP11：PPT 大纲 JSON 提取、产物目录锚定、上传解析的健壮性。

- AJP6：原先用贪婪正则 `\\{[\\s\\S]*\\}` 提取无围栏的 JSON，遇到多段
  JSON 会拼成一个无法解析的字符串，最终静默回退模板大纲。改为从首个
  `{` / `[` 起用 `raw_decode` 解析第一个完整 JSON 值。
- AJP10：产物/上传/模板目录原先用相对路径，随进程 CWD 漂移；改为锚定
  仓库根目录，并与定时清理服务的默认目录保持一致。
- AJP11：`parse_document` 是同步 CPU/IO 解析，直接在 async 端点内调用会
  阻塞事件循环，改为 `asyncio.to_thread` 放入工作线程。
"""

import json
import threading
from pathlib import Path

import pytest

from app.api.v1 import aiGeneratorPptx
from app.core.config import BASE_DIR
from app.services import generated_asset_retention


def test_extract_json_prefers_fenced_block():
    content = '说明文字\n```json\n{"slides": [1, 2]}\n```\n结束语'
    assert json.loads(aiGeneratorPptx._extract_json_payload(content)) == {"slides": [1, 2]}


def test_extract_json_returns_first_value_without_crossing_blocks():
    content = '前言 {"a": {"b": 1}} 中间 {"c": 2} 结尾'
    payload = aiGeneratorPptx._extract_json_payload(content)
    assert payload == '{"a": {"b": 1}}'
    assert json.loads(payload) == {"a": {"b": 1}}


def test_extract_json_handles_array_payload():
    content = "结果如下 [1, 2, 3] 完毕"
    assert json.loads(aiGeneratorPptx._extract_json_payload(content)) == [1, 2, 3]


def test_extract_json_without_json_raises():
    with pytest.raises(ValueError):
        aiGeneratorPptx._extract_json_payload("没有任何 JSON 内容")


@pytest.mark.asyncio
async def test_parse_uploaded_document_runs_off_main_thread(monkeypatch):
    import app.utils.aicloud.knowledge_processor as knowledge_processor

    seen = {}

    def fake_parse(path):
        seen["thread"] = threading.current_thread()
        return "解析文本"

    monkeypatch.setattr(knowledge_processor, "parse_document", fake_parse)

    text = await aiGeneratorPptx._parse_uploaded_document(Path("/tmp/example.pdf"))

    assert text == "解析文本"
    assert seen["thread"] is not threading.main_thread()


def test_ppt_output_dir_is_anchored_and_matches_cleanup_default():
    assert aiGeneratorPptx.PPT_OUTPUT_DIR == BASE_DIR / "pptx_output"
    assert generated_asset_retention.DEFAULT_PPT_OUTPUT_DIR == aiGeneratorPptx.PPT_OUTPUT_DIR
