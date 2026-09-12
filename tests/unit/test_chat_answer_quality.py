import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

from app.api.v1 import Aicode
from app.api.v1.Aicode import (
    ai_decide_search,
    build_bounded_search_query,
    parse_search_decision,
    _build_context,
)
from app.db.add_history import save_history_to_db
from app.api.v1.auth import _history_payload
from app.models.history import History
from app.utils.aicloud.knowledge_processor import parse_document
from app.schema.codeRequest import CodeRequest
from pydantic import ValidationError


def test_parse_search_decision_reads_json():
    assert parse_search_decision('{"search": true}') is True
    assert parse_search_decision('{"search": false}') is False
    assert parse_search_decision("not json") is None


def _passthrough_planner():
    async def plan(prompt, attachment_names=None, sources=None, failed_queries=None, api_key_token=None):
        query = build_bounded_search_query(prompt, attachment_names)
        if sources:
            follow = Aicode.build_followup_search_query(query, sources)
            if not follow:
                return {"action": "stop", "queries": [], "urls": []}
            return {"action": "search", "queries": [follow], "urls": []}
        return {"action": "search", "queries": [query], "urls": []}
    return plan


def _install_search_stubs(monkeypatch, plan=None):
    monkeypatch.setattr(Aicode, "plan_search_actions", plan or _passthrough_planner())

    async def no_pages(*_args, **_kwargs):
        return []

    monkeypatch.setattr(Aicode, "fetch_source_pages", no_pages)


def test_parse_search_plan_reads_search_fetch_stop():
    search = Aicode.parse_search_plan('{"action":"search","queries":["华为 2024年 营收"]}')
    assert search["action"] == "search"
    assert search["queries"] == ["华为 2024年 营收"]
    fetch = Aicode.parse_search_plan('{"action":"fetch","urls":["https://example.test/a"]}')
    assert fetch["action"] == "fetch"
    assert fetch["urls"] == ["https://example.test/a"]
    assert Aicode.parse_search_plan('{"action":"stop"}')["action"] == "stop"
    assert Aicode.parse_search_plan("not json") is None


def test_parse_search_plan_expands_relative_years():
    plan = Aicode.parse_search_plan('{"action":"search","queries":["今年就业数据"]}')
    year = str(datetime.now().year)
    assert year in plan["queries"][0]
    assert "今年" not in plan["queries"][0]


@pytest.mark.asyncio
async def test_plan_search_actions_uses_model_queries(monkeypatch):
    async def fake_llm(**_kwargs):
        return {"choices": [{"message": {"content": '{"action":"search","queries":["华为 营收 2024"]}'}}]}

    monkeypatch.setattr(Aicode, "call_llm", fake_llm)
    plan = await Aicode.plan_search_actions("华为的近三年营收")
    assert plan["action"] == "search"
    assert plan["queries"] == ["华为 营收 2024"]


@pytest.mark.asyncio
async def test_plan_search_actions_fail_open_to_bounded_query(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(Aicode, "call_llm", boom)
    plan = await Aicode.plan_search_actions("今年的就业数据")
    assert plan["action"] == "search"
    assert str(datetime.now().year) in plan["queries"][0]
    assert "就业数据" in plan["queries"][0]


@pytest.mark.asyncio
async def test_ai_decide_search_uses_model_and_skips_greetings(monkeypatch):
    prompts = []

    async def fake_llm(**kwargs):
        prompts.append(kwargs["prompt"])
        return {"choices": [{"message": {"content": '{"search": true}'}}]}

    monkeypatch.setattr(Aicode, "call_llm", fake_llm)
    assert await ai_decide_search("你好") is False
    assert prompts == []
    assert await ai_decide_search("前几年的就业数据") is True
    assert "前几年的就业数据" in prompts[0]
    assert str(datetime.now().year) in prompts[0]


@pytest.mark.asyncio
async def test_ai_decide_search_fail_open_when_model_errors(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(Aicode, "call_llm", boom)
    assert await ai_decide_search("今年的就业数据") is True


@pytest.mark.asyncio
async def test_auto_mode_searches_general_questions_and_skips_code(monkeypatch):
    called = []

    class Search:
        async def search_with_sources(self, **kwargs):
            called.append(kwargs["query"])
            return "result", [{"title": "T", "url": "https://example.test", "snippet": "S"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)

    async def decide(prompt, api_key_token=None):
        return "快排" not in prompt

    monkeypatch.setattr(Aicode, "ai_decide_search", decide)
    events = []
    _, _, did_search, _, _ = await _build_context(
        1, "北京有哪些值得去的博物馆", _Db(), None, None, 3, search_mode="auto", on_stage=events.append
    )
    assert did_search is True
    assert called == ["北京有哪些值得去的博物馆"]

    events = []
    _, _, did_search, _, _ = await _build_context(
        1, "写一个 Python 快排函数", _Db(), None, None, 3, search_mode="auto", on_stage=events.append
    )
    assert did_search is False
    assert called == ["北京有哪些值得去的博物馆"]
    assert any(event.get("reason") == "auto_not_needed" for event in events)


@pytest.mark.asyncio
async def test_employment_query_injects_time_and_expands_year(monkeypatch):
    called = []

    class Search:
        async def search_with_sources(self, **kwargs):
            called.append(kwargs["query"])
            return "result", [{"title": "就业", "url": "https://example.test/jobs", "snippet": "数据"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)
    monkeypatch.setattr(Aicode, "ai_decide_search", AsyncMock(return_value=True))
    context, _, did_search, _, _ = await _build_context(
        1, "今年的就业数据", _Db(), None, None, 3, search_mode="auto"
    )
    year = str(datetime.now().year)
    assert did_search is True
    assert "当前时间" in context
    assert year in context
    assert called
    assert year in called[0]
    assert "就业数据" in called[0]


def test_attachment_search_query_is_bounded_and_uses_name_entity_only():
    query = build_bounded_search_query(
        "核查附件最新版本并给出变化说明", ["Qwen3_Release_Notes.pdf"]
    )
    assert len(query) <= 400
    assert query.startswith("Qwen3 Release Notes ")
    assert "核查附件最新版本并给出变化说明" in query
    assert "完整正文" not in query


def test_empty_attachment_names_do_not_expand_query():
    assert build_bounded_search_query("最新版本", []) == "最新版本"


def test_attachment_entities_leave_room_for_question():
    prompt = "核查最新版本并说明升级影响"
    query = build_bounded_search_query(prompt, ["topic" * 30 + ".pdf"] * 10)
    assert len(query) <= 400
    assert query.endswith(prompt)


def test_followup_prefers_topic_details_over_generic_first_result():
    sources = [
        {"title": "Welcome to Python.org", "snippet": "Python community mission"},
        {"title": "Download Python", "snippet": "Python release installer packages"},
    ]
    query = Aicode.build_followup_search_query("Python latest stable release official release notes", sources)
    assert "Download Python" in query
    assert "release installer" in query
    assert "community mission" not in query


class _Result:
    def scalar_one_or_none(self):
        return None


class _Db:
    async def execute(self, *_args, **_kwargs):
        return _Result()


@pytest.mark.asyncio
async def test_search_mode_explicit_value_overrides_legacy_boolean(monkeypatch):
    called = []

    class Search:
        async def search_with_sources(self, **kwargs):
            called.append(kwargs["query"])
            return "result", [{"title": "T", "url": "https://example.test", "snippet": "S"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)
    _, _, did_search, _, _ = await _build_context(1, "静态问题", _Db(), None, False, 3, search_mode="on")
    assert did_search is True
    assert called

    _, _, did_search, _, _ = await _build_context(1, "联网搜索最新版本", _Db(), None, True, 3, search_mode="off")
    assert did_search is False
    assert len(called) == 1


@pytest.mark.asyncio
async def test_stage_callback_reports_real_order_and_search_fallback(monkeypatch):
    events = []

    class Search:
        async def search_with_sources(self, **kwargs):
            assert "report" in kwargs["query"]
            assert "Acme" in kwargs["query"]
            assert "uuid-path" not in kwargs["query"]
            assert "private paragraph" not in kwargs["query"]
            return "搜索暂时不可用", []

    async def parse_file(*_args, **_kwargs):
        return "正文\n公司：Acme\nprivate paragraph", {"filename": "report.txt", "type": "parsed"}

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)
    monkeypatch.setattr(Aicode, "get_or_parse_file", parse_file)
    context, sources, _, _, warnings = await _build_context(
        1, "联网搜索报告", _Db(), None, None, 3, files_to_parse=["uuid-path"], on_stage=events.append
    )
    assert context.find("正文") >= 0
    assert sources[0] == {"kind": "file", "title": "report.txt"}
    assert events[0]["status"] == "started"
    assert any(event["status"] == "failed" and event["stage"] == "searching" for event in events)
    assert warnings


@pytest.mark.asyncio
async def test_off_mode_reports_skipped_without_search(monkeypatch):
    events = []
    search = SimpleNamespace(search_with_sources=lambda **_: pytest.fail("must not search"))
    monkeypatch.setattr(Aicode, "FreeWebSearch", lambda: search)
    await _build_context(1, "普通问题", _Db(), None, None, 3, search_mode="off", on_stage=events.append)
    assert {event["status"] for event in events} == {"skipped"}


@pytest.mark.asyncio
async def test_history_save_persists_display_metadata():
    class Db:
        def __init__(self):
            self.record = None

        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(scalar=lambda: 0)

        def add(self, record):
            self.record = record

        async def commit(self):
            return None

        async def refresh(self, _record):
            return None

    db = Db()
    await save_history_to_db(db, 1, None, "p", "r", metadata={"sources": [{"title": "T"}]})
    assert '"sources"' in db.record.metadata_json


def test_document_parser_reads_supported_text_and_history_exposes_metadata(tmp_path):
    document = tmp_path / "notes.txt"
    document.write_text("标题\n公司 Acme", encoding="utf-8")
    assert "Acme" in parse_document(str(document))

    record = History(
        id=1,
        conversation_id=2,
        prompt="p",
        response="r",
        metadata_json='{"sources":[{"title":"T"}]}',
    )
    assert _history_payload(record)["metadata"]["sources"][0]["title"] == "T"


@pytest.mark.asyncio
async def test_document_body_is_cached_and_parser_is_skipped_on_cache_hit(monkeypatch, tmp_path):
    document = tmp_path / "report.txt"
    document.write_text("company report body", encoding="utf-8")
    record = SimpleNamespace(filename="report.txt", parsed_content=None, parsed_at=None)
    record.is_parse_cache_valid = Mock(return_value=False)
    record.update_parse_cache = Mock()
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(Aicode, "verify_file_access", AsyncMock(return_value=str(document)))
    body, _ = await Aicode.get_or_parse_file(str(document), 1, None, db)
    assert body == "company report body"
    record.update_parse_cache.assert_called_once_with(body, ttl_seconds=3600)
    record.is_parse_cache_valid.return_value = True
    record.parsed_content = body
    record.parsed_at = SimpleNamespace(isoformat=lambda: "2026-09-08")
    monkeypatch.setattr(Aicode, "parse_document", Mock(side_effect=AssertionError("cache must bypass parser")))
    assert (await Aicode.get_or_parse_file(str(document), 1, None, db))[0] == body


@pytest.mark.asyncio
async def test_attachment_failure_is_a_visible_warning(monkeypatch):
    monkeypatch.setattr(Aicode, "get_or_parse_file", AsyncMock(side_effect=Aicode.HTTPException(422, "附件无正文")))
    events = []
    context, sources, _, _, warnings = await _build_context(
        1, "总结附件", _Db(), None, None, 3, search_mode="off", files_to_parse=["report.pdf"], on_stage=events.append
    )
    assert sources == []
    assert warnings == [{"stage": "parsing", "error": "附件无正文"}]
    assert "附件无正文" in context
    assert events[1]["status"] == "failed"


@pytest.mark.asyncio
async def test_stream_emits_real_stage_before_work_and_cancels_context(monkeypatch):
    released = asyncio.Event()
    cancelled = asyncio.Event()

    async def context(**kwargs):
        try:
            await kwargs["on_stage"]({"stage": "parsing", "status": "started"})
            await released.wait()
            return "", [], False, True, []
        finally:
            cancelled.set()

    monkeypatch.setattr(Aicode, "_build_context", context)
    stream = Aicode.stream_response("1", "q", "model", None, _Db(), None)
    event = json.loads(await asyncio.wait_for(anext(stream), timeout=1))
    assert event == {"stage": "parsing", "status": "started"}
    assert not released.is_set()
    await stream.aclose()
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(("depth", "expected_calls"), [("shallow", 1), ("multi", 2)])
async def test_search_depth_drives_result_based_rounds(monkeypatch, depth, expected_calls):
    calls, events = [], []
    first = {"title": "Acme Nova 版本", "url": "https://example.test/one", "snippet": "新增 VectorIndex 引擎"}
    second = {"title": "VectorIndex 说明", "url": "https://example.test/two", "snippet": "技术说明"}

    class Search:
        async def search_with_sources(self, **kwargs):
            calls.append(kwargs["query"])
            assert events[-1]["status"] == "started"
            if len(calls) == 1:
                return "首轮资料", [first]
            return "第二轮资料", [first, second]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)
    context, sources, _, _, warnings = await _build_context(
        1, "最新产品资料", _Db(), None, None, 3,
        search_mode="on", search_depth=depth, on_stage=events.append,
    )
    assert len(calls) == expected_calls
    assert warnings == []
    assert "首轮资料" in context
    if depth == "multi":
        assert calls[1] != calls[0]
        assert "最新产品资料" in calls[1]
        assert "VectorIndex" in calls[1]
        assert len(calls[1]) <= 400
        assert "第二轮资料" in context
        assert [s["url"] for s in sources] == [first["url"], second["url"]]
        assert [e["round"] for e in events if e["status"] == "started"] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_round", [1, 2])
async def test_multi_round_failure_keeps_existing_results(monkeypatch, failed_round):
    calls = []
    class Search:
        async def search_with_sources(self, **kwargs):
            calls.append(kwargs["query"])
            if len(calls) == failed_round:
                raise OSError("search unavailable")
            return "有效首轮", [{"title": "Nova 引擎", "snippet": "更新细节", "url": "https://example.test/one"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch)
    context, sources, _, _, warnings = await _build_context(
        1, "q", _Db(), None, None, 3, search_mode="on", search_depth="multi"
    )
    assert len(calls) == failed_round
    assert warnings[0]["round"] == failed_round
    assert len(sources) == failed_round - 1
    if failed_round == 2:
        assert "有效首轮" in context


@pytest.mark.asyncio
async def test_multi_depth_respects_disabled_search(monkeypatch):
    search = Mock(side_effect=AssertionError("disabled search"))
    monkeypatch.setattr(Aicode, "FreeWebSearch", search)
    await _build_context(1, "最新资料", _Db(), None, None, 3, search_mode="off", search_depth="multi")
    search.assert_not_called()


def test_search_depth_contract_and_followup_query_bounds():
    assert CodeRequest(prompt="q").search_depth == "shallow"
    with pytest.raises(ValidationError):
        CodeRequest(prompt="q", search_depth="unlimited")
    query = Aicode.build_followup_search_query("q" * 400, [{"title": "t" * 500, "snippet": "s" * 1000}])
    assert len(query) <= 400
    assert "t" in query and "s" in query
    assert Aicode.build_followup_search_query("q", [{"title": "", "snippet": ""}]) is None


@pytest.mark.asyncio
async def test_build_context_uses_planned_search_queries(monkeypatch):
    called = []

    class Search:
        async def search_with_sources(self, **kwargs):
            called.append(kwargs["query"])
            return "result", [{"title": "华为2024年报", "url": "https://example.test/hw", "snippet": "营收"}]

    async def plan(prompt, **_kwargs):
        return {"action": "search", "queries": ["华为 营收 2024", "华为 营收 2025"], "urls": []}

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    _install_search_stubs(monkeypatch, plan=plan)
    _, _, did_search, _, _ = await _build_context(
        1, "华为的近三年营收", _Db(), None, None, 3, search_mode="on"
    )
    assert did_search is True
    assert called == ["华为 营收 2024", "华为 营收 2025"]


@pytest.mark.asyncio
async def test_build_context_fetches_search_hit_pages(monkeypatch):
    class Search:
        async def search_with_sources(self, **kwargs):
            return "摘要", [{"title": "年报", "url": "https://example.test/report", "snippet": "营收"}]

    async def pages(urls, seen=None, limit=2):
        return [{"url": urls[0], "text": "2024年营业收入 6000 亿元"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    monkeypatch.setattr(Aicode, "plan_search_actions", _passthrough_planner())
    monkeypatch.setattr(Aicode, "fetch_source_pages", pages)
    context, sources, _, _, _ = await _build_context(
        1, "华为的近三年营收", _Db(), None, None, 3, search_mode="on"
    )
    assert "2024年营业收入 6000 亿元" in context
    assert sources[0]["url"] == "https://example.test/report"


@pytest.mark.asyncio
async def test_multi_round_can_fetch_known_source(monkeypatch):
    calls = []

    class Search:
        async def search_with_sources(self, **kwargs):
            calls.append(kwargs["query"])
            return "摘要", [{"title": "年报", "url": "https://example.test/report", "snippet": "营收"}]

    plans = iter([
        {"action": "search", "queries": ["华为 年报"], "urls": []},
        {"action": "fetch", "urls": ["https://example.test/report"]},
    ])

    async def plan(prompt, **_kwargs):
        return next(plans)

    async def pages(urls, seen=None, limit=2):
        return [{"url": "https://example.test/report", "text": "正文营收数字"}]

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    monkeypatch.setattr(Aicode, "plan_search_actions", plan)
    monkeypatch.setattr(Aicode, "fetch_source_pages", pages)
    context, _, _, _, _ = await _build_context(
        1, "华为营收", _Db(), None, None, 3, search_mode="on", search_depth="multi"
    )
    assert calls == ["华为 年报"]
    assert "正文营收数字" in context


@pytest.mark.asyncio
async def test_empty_first_search_retries_with_new_queries(monkeypatch):
    calls = []
    seen_failed = []
    plans = iter([
        {"action": "search", "queries": ["2025中国就业数据"], "urls": []},
        {"action": "search", "queries": ["2025年国民经济和社会发展统计公报"], "urls": []},
    ])

    async def plan(prompt, failed_queries=None, **_kwargs):
        seen_failed.append(list(failed_queries or []))
        return next(plans)

    class Search:
        async def search_with_sources(self, **kwargs):
            calls.append(kwargs["query"])
            if "统计公报" in kwargs["query"]:
                return "公报", [{"title": "统计公报", "url": "https://www.stats.gov.cn/bulletin", "snippet": "就业"}]
            return "搜索暂时不可用", []

    monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
    monkeypatch.setattr(Aicode, "plan_search_actions", plan)

    async def no_pages(*_args, **_kwargs):
        return []

    monkeypatch.setattr(Aicode, "fetch_source_pages", no_pages)
    context, sources, _, _, warnings = await _build_context(
        1, "2025中国就业数据", _Db(), None, None, 3, search_mode="on"
    )
    assert calls == ["2025中国就业数据", "2025年国民经济和社会发展统计公报"]
    assert seen_failed[1] == ["2025中国就业数据"]
    assert sources[0]["url"].endswith("/bulletin")
    assert "公报" in context
    assert warnings == []
