"""AJP4：PPT 生成应消费素材正文，而非只拼文件名。

`material_file_ids` 对应的 `File.parsed_content` 一直存在，旧链路却只把
filename 拼进 prompt（与 `ppt_state_service._load_materials` 不一致），
「素材上传绑定」名不符实。`_read_material_text` 负责取正文：优先缓存、
未命中解析回填、失败降级为空。
"""

import pytest

import app.api.v1.aiGeneratorPptx as pptx_api
from app.utils.aicloud import knowledge_processor


class _FakeFile:
    def __init__(self, filename="report.pdf", path="/tmp/report.pdf", cached=None, valid=False):
        self.filename = filename
        self.file_path = path
        self.parsed_content = cached
        self._valid = valid
        self.cache_updates = []

    def is_parse_cache_valid(self, ttl_seconds=3600):
        return self._valid

    def update_parse_cache(self, content, ttl_seconds=3600):
        self.cache_updates.append(content)


async def test_uses_cached_content_not_filename(monkeypatch):
    record = _FakeFile(cached="缓存里的素材正文", valid=True)

    async def _boom(*args, **kwargs):
        raise AssertionError("缓存命中时不应重新解析")

    monkeypatch.setattr(pptx_api.asyncio, "to_thread", _boom)

    text = await pptx_api._read_material_text(record)

    assert text == "缓存里的素材正文"


async def test_parses_and_backfills_on_cache_miss(monkeypatch):
    record = _FakeFile(cached=None, valid=False)

    monkeypatch.setattr(knowledge_processor, "parse_document", lambda path: "  解析出的正文  ")

    text = await pptx_api._read_material_text(record)

    assert text == "解析出的正文"
    assert record.cache_updates == ["解析出的正文"]


async def test_parse_failure_degrades_to_empty(monkeypatch):
    record = _FakeFile(cached=None, valid=False)

    def _fail(path):
        raise RuntimeError("坏文件")

    monkeypatch.setattr(knowledge_processor, "parse_document", _fail)

    assert await pptx_api._read_material_text(record) == ""
    assert record.cache_updates == []


async def test_content_is_truncated_to_limit(monkeypatch):
    record = _FakeFile(cached="x" * 100, valid=True)

    text = await pptx_api._read_material_text(record, limit=10)

    assert text == "x" * 10


class _FakeResult:
    def __init__(self, record):
        self._record = record

    def scalar_one_or_none(self):
        return self._record


class _FakeSession:
    def __init__(self, records_by_id):
        self._records_by_id = records_by_id

    async def execute(self, _stmt):
        # select(File).where(File.id == <file_id>) 的绑定值从编译后的参数里取
        file_id = next(
            (value for value in _stmt.compile().params.values() if isinstance(value, int)),
            None,
        )
        return _FakeResult(self._records_by_id.get(file_id))


async def test_material_context_embeds_content_not_just_filename(monkeypatch):
    record = _FakeFile(filename="年度报告.pdf", cached="营收同比增长 18%", valid=True)
    db = _FakeSession({7: record})

    context = await pptx_api._build_material_context(db, "42", [7])

    assert "年度报告.pdf" in context
    assert "营收同比增长 18%" in context
    assert context.strip().startswith("[参考素材]")


async def test_material_context_skips_other_session(monkeypatch):
    record = _FakeFile(filename="别的会话.pdf", cached="正文", valid=True)
    record.conversation_id = 2
    db = _FakeSession({7: record})

    assert await pptx_api._build_material_context(db, "42", [7], session_id="1") == ""


async def test_material_context_matches_session_across_types(monkeypatch):
    # File.conversation_id 是 Integer，请求里的 session_id 是 str
    record = _FakeFile(filename="本会话.pdf", cached="正文", valid=True)
    record.conversation_id = 7
    db = _FakeSession({7: record})

    context = await pptx_api._build_material_context(db, "42", [7], session_id="7")

    assert "正文" in context


async def test_material_context_empty_when_no_record(monkeypatch):
    db = _FakeSession({})

    assert await pptx_api._build_material_context(db, "42", [7]) == ""
