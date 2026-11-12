"""Branch coverage for app/api/v1/Aicode.py."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import Aicode
from app.schema.codeRequest import CodeRequest, FileAttachment


class _Result:
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []
        self.rowcount = 3

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _Db:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.execute = AsyncMock(return_value=_Result())
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def scalars(self, _stmt):
        return _Result(rows=[1, 2])


class _Budget:
    context_length = 32768
    max_output_tokens = 4096
    input_budget_tokens = 28672
    input_tokens = 100
    truncated = False


class _Request:
    def __init__(self, disconnected=False):
        self._disconnected = disconnected

    async def is_disconnected(self):
        return self._disconnected


def _patch_fit(monkeypatch, context="ctx"):
    monkeypatch.setattr(
        Aicode, "fit_context", MagicMock(return_value=(context, _Budget()))
    )


class TestSharedChatPersistence:
    @pytest.mark.asyncio
    async def test_existing_session_reuses_it(self, monkeypatch):
        db = _Db()
        db.scalar = AsyncMock(return_value=SimpleNamespace(id=10))
        create = AsyncMock()
        append = AsyncMock()
        invalidate = AsyncMock()
        monkeypatch.setattr(Aicode, "create_session", create)
        monkeypatch.setattr(Aicode, "append_message", append)
        monkeypatch.setattr(Aicode, "invalidate_history_caches", invalidate)

        await Aicode._append_shared_chat_messages(db, 1, 5, "p", "r")

        create.assert_not_awaited()
        assert append.await_count == 2
        db.commit.assert_awaited_once()
        invalidate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_session_is_created(self, monkeypatch):
        db = _Db()
        db.scalar = AsyncMock(return_value=None)
        create = AsyncMock(return_value=SimpleNamespace(id=11))
        monkeypatch.setattr(Aicode, "create_session", create)
        monkeypatch.setattr(Aicode, "append_message", AsyncMock())
        monkeypatch.setattr(Aicode, "invalidate_history_caches", AsyncMock())

        await Aicode._append_shared_chat_messages(db, 1, 5, "p", "r")

        create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_all_removes_shared_rows(self):
        db = _Db()
        db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [1, 2]))

        deleted = await Aicode._delete_shared_chat_data(db, 1, delete_all=True)

        assert deleted == 2
        assert db.execute.await_count == 4

    @pytest.mark.asyncio
    async def test_delete_without_matching_sessions_only_updates_files(self):
        db = _Db()
        db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

        deleted = await Aicode._delete_shared_chat_data(db, 1, conversation_ids=[9])

        assert deleted == 0
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_delete_by_conversation_ids(self):
        db = _Db()
        db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [3, 4]))

        deleted = await Aicode._delete_shared_chat_data(db, 1, conversation_ids=[3, 4])

        assert deleted == 2
        assert db.execute.await_count == 4


class TestSearchHelpers:
    def test_parse_search_decision_edge_cases(self):
        assert Aicode.parse_search_decision("") is None
        assert Aicode.parse_search_decision('{"other": true}') is None
        assert Aicode.parse_search_decision("[1, 2]") is None
        assert Aicode.parse_search_decision("text {\"search\": false} tail") is False

    @pytest.mark.asyncio
    async def test_ai_decide_search_invalid_output_defaults_to_search(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(return_value={"choices": [{"message": {"content": "garbage"}}]}),
        )
        assert await Aicode.ai_decide_search("今天天气") is True

    @pytest.mark.asyncio
    async def test_ai_decide_search_handles_malformed_payload(self, monkeypatch):
        monkeypatch.setattr(Aicode, "call_llm", AsyncMock(return_value=None))
        assert await Aicode.ai_decide_search("今日新闻") is True

    def test_parse_search_plan_variants(self):
        assert Aicode.parse_search_plan("") is None
        assert Aicode.parse_search_plan("[1]") is None
        plan = Aicode.parse_search_plan('{"action":"unknown","queries":"q1"}')
        assert plan["action"] == "search"
        assert plan["queries"] == ["q1"]
        assert Aicode.parse_search_plan('{"action":"unknown"}') is None
        plan = Aicode.parse_search_plan(
            '{"action":"fetch","urls":"https://a.test/x"}'
        )
        assert plan["urls"] == ["https://a.test/x"]
        plan = Aicode.parse_search_plan(
            '{"action":"fetch","urls":["ftp://bad", "https://ok.test"]}'
        )
        assert plan["urls"] == ["https://ok.test"]
        plan = Aicode.parse_search_plan(
            '{"action":"search","queries":["", "  ", "ok"]}'
        )
        assert plan["queries"] == ["ok"]

    @pytest.mark.asyncio
    async def test_plan_search_actions_unusable_output_falls_back(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(return_value={"choices": [{"message": {"content": "nope"}}]}),
        )
        plan = await Aicode.plan_search_actions("查询")
        assert plan["action"] == "search"
        assert plan["queries"]

    @pytest.mark.asyncio
    async def test_plan_search_actions_empty_queries_falls_back(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(
                return_value={
                    "choices": [{"message": {"content": '{"action":"search","queries":[]}'}}]
                }
            ),
        )
        plan = await Aicode.plan_search_actions("查询")
        assert plan["queries"]

    @pytest.mark.asyncio
    async def test_plan_search_actions_fetch_without_url_stops_when_sources_exist(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(
                return_value={
                    "choices": [{"message": {"content": '{"action":"fetch","urls":[]}'}}]
                }
            ),
        )
        plan = await Aicode.plan_search_actions(
            "查询", sources=[{"url": "https://a.test", "title": "T", "snippet": "S"}]
        )
        assert plan == {"action": "stop", "queries": [], "urls": []}

    @pytest.mark.asyncio
    async def test_plan_search_actions_fetch_without_url_falls_back_without_sources(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(
                return_value={
                    "choices": [{"message": {"content": '{"action":"fetch","urls":[]}'}}]
                }
            ),
        )
        plan = await Aicode.plan_search_actions("查询")
        assert plan["action"] == "search"

    @pytest.mark.asyncio
    async def test_plan_search_actions_skips_sources_without_url(self, monkeypatch):
        captured = {}

        async def fake_llm(**kwargs):
            captured.update(kwargs)
            return {"choices": [{"message": {"content": '{"action":"stop"}'}}]}

        monkeypatch.setattr(Aicode, "call_llm", fake_llm)
        await Aicode.plan_search_actions(
            "查询",
            attachment_names=["my-file.pdf", ""],
            sources=[{"title": "no url"}, {"url": "https://a.test", "title": "T", "snippet": "S"}],
            failed_queries=["old"],
        )
        assert "https://a.test" in captured["prompt"]
        assert "my-file" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_fetch_source_pages_filters_and_limits(self, monkeypatch):
        fetched = []

        async def fake_fetch(url, timeout):
            fetched.append(url)
            return "body" if "good" in url else ""

        monkeypatch.setattr(Aicode, "fetch_page_text", fake_fetch)
        pages = await Aicode.fetch_source_pages(
            [
                "",
                "ftp://bad",
                "https://bad url",
                "https://good1.test",
                "https://good2.test",
                "https://good1.test",
                "https://empty.test",
            ],
            seen=set(),
            limit=1,
        )
        assert len(pages) == 1
        assert pages[0]["text"] == "body"

    @pytest.mark.asyncio
    async def test_fetch_source_pages_skips_unsafe_urls(self, monkeypatch):
        fetched = []

        async def fake_fetch(url, timeout):
            fetched.append(url)
            return "body" if "ok" in url else ""

        monkeypatch.setattr(Aicode, "fetch_page_text", fake_fetch)
        pages = await Aicode.fetch_source_pages(
            ["https://has space.test", "https://empty.test", "https://ok.test"],
            seen=None,
        )

        assert fetched == ["https://empty.test", "https://ok.test"]
        assert pages[0]["url"] == "https://ok.test"

    def test_build_followup_search_query_returns_none_without_fresh_terms(self):
        assert (
            Aicode.build_followup_search_query(
                "python release", [{"title": "python release", "snippet": "python release"}]
            )
            is None
        )


class TestStreamParsing:
    def test_extract_stream_content_parses_primary_and_fallback(self):
        ok, content = Aicode.extract_stream_content(
            json.dumps({"choices": [{"delta": {"content": "hi"}}]})
        )
        assert ok and content == "hi"

        ok, content = Aicode.extract_stream_content(
            json.dumps({"choices": [{"delta": {}}]})
        )
        assert ok and content == ""

        ok, content = Aicode.extract_stream_content(
            json.dumps({"choices": []})
        )
        assert not ok and content == ""

    def test_extract_stream_content_uses_fallback_parser(self, monkeypatch):
        monkeypatch.setattr(
            Aicode._parser,
            "parse",
            MagicMock(return_value={"choices": [{"delta": {"content": "fallback"}}]}),
        )
        ok, content = Aicode.extract_stream_content("{bad json")
        assert ok and content == "fallback"

    def test_extract_stream_content_returns_false_on_total_failure(self, monkeypatch):
        monkeypatch.setattr(
            Aicode._parser, "parse", MagicMock(side_effect=ValueError("bad"))
        )
        ok, content = Aicode.extract_stream_content("{bad json")
        assert not ok and content == ""

    def test_extract_stream_content_fallback_allows_empty_choices(self, monkeypatch):
        monkeypatch.setattr(
            Aicode._parser, "parse", MagicMock(return_value={"choices": []})
        )
        assert Aicode.extract_stream_content("{bad") == (False, "")

    def test_format_tokens_usage_defaults(self):
        assert Aicode.format_tokens_usage({}) == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        assert Aicode.format_tokens_usage({"usage": {"total_tokens": 3}})[
            "total_tokens"
        ] == 3


class TestContextBuilding:
    @pytest.mark.asyncio
    async def test_history_compression_included(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "compress_conversation_history", AsyncMock(return_value="HISTORY")
        )
        context, _, _, _, _ = await Aicode._build_context(
            1, "q", _Db(), 5, False, 3, search_mode="off"
        )
        assert "HISTORY" in context

    @pytest.mark.asyncio
    async def test_attachment_identity_field_added_to_search_terms(self, monkeypatch):
        async def parse_file(*_args, **_kwargs):
            return "公司：Acme 科技", {"filename": "report.txt"}

        monkeypatch.setattr(Aicode, "get_or_parse_file", parse_file)
        captured = {}

        async def plan(prompt, attachment_names=None, **_kwargs):
            captured["names"] = attachment_names
            return {"action": "search", "queries": ["q"], "urls": []}

        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))

        await Aicode._build_context(
            1,
            "q",
            _Db(),
            None,
            None,
            3,
            search_mode="on",
            files_to_parse=["report.txt"],
        )

        assert "Acme 科技" in captured["names"]

    @pytest.mark.asyncio
    async def test_attachment_generic_failure_is_reported(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "get_or_parse_file", AsyncMock(side_effect=RuntimeError("boom"))
        )
        events = []
        context, _, _, had_files, warnings = await Aicode._build_context(
            1,
            "q",
            _Db(),
            None,
            None,
            3,
            search_mode="off",
            files_to_parse=["x.txt"],
            on_stage=events.append,
        )
        assert had_files is True
        assert warnings[0]["stage"] == "parsing"
        assert "附件处理失败" in context

    @pytest.mark.asyncio
    async def test_stage_callback_awaitable_is_awaited(self, monkeypatch):
        events = []

        async def stage(event):
            events.append(event)

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="off", on_stage=stage
        )
        assert events

    @pytest.mark.asyncio
    async def test_plan_stop_with_existing_sources_breaks(self, monkeypatch):
        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        plans = iter(
            [
                {"action": "search", "queries": ["q"], "urls": []},
                {"action": "stop", "queries": [], "urls": []},
            ]
        )

        async def plan(*_args, **_kwargs):
            return next(plans)

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))
        events = []

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on", search_depth="multi",
            on_stage=events.append,
        )

        assert any(e.get("reason") == "plan_stop" for e in events)

    @pytest.mark.asyncio
    async def test_stop_without_sources_falls_back_to_search(self, monkeypatch):
        calls = []

        class Search:
            async def search_with_sources(self, **kwargs):
                calls.append(kwargs["query"])
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(
            Aicode,
            "plan_search_actions",
            AsyncMock(return_value={"action": "stop", "queries": [], "urls": []}),
        )
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on"
        )

        assert calls

    @pytest.mark.asyncio
    async def test_fetch_action_without_allowed_sources_falls_back(self, monkeypatch):
        calls = []

        class Search:
            async def search_with_sources(self, **kwargs):
                calls.append(kwargs["query"])
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(
            Aicode,
            "plan_search_actions",
            AsyncMock(return_value={"action": "fetch", "queries": [], "urls": ["https://a.test"]}),
        )
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on"
        )

        assert calls

    @pytest.mark.asyncio
    async def test_fetch_action_with_no_page_body_raises_fallback(self, monkeypatch):
        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        plans = iter(
            [
                {"action": "search", "queries": ["q"], "urls": []},
                {"action": "fetch", "urls": ["https://a.test"]},
            ]
        )

        async def plan(*_args, **_kwargs):
            return next(plans)

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))
        warnings_events = []

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on", search_depth="multi",
            on_stage=warnings_events.append,
        )

        assert any(e.get("status") == "failed" for e in warnings_events)

    @pytest.mark.asyncio
    async def test_fetch_action_already_fetched_is_skipped(self, monkeypatch):
        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        plans = iter(
            [
                {"action": "search", "queries": ["q"], "urls": []},
                {"action": "fetch", "urls": ["https://a.test"]},
            ]
        )

        async def plan(*_args, **_kwargs):
            return next(plans)

        async def pages(urls, seen=None, limit=2):
            seen.add("https://a.test")
            return [{"url": "https://a.test", "text": "body"}]

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "fetch_source_pages", pages)
        events = []

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on", search_depth="multi",
            on_stage=events.append,
        )

        assert any(e.get("reason") == "already_fetched" for e in events)

    @pytest.mark.asyncio
    async def test_fetch_action_returns_pages(self, monkeypatch):
        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        plans = iter(
            [
                {"action": "search", "queries": ["q"], "urls": []},
                {"action": "fetch", "urls": ["https://a.test"]},
            ]
        )

        async def plan(*_args, **_kwargs):
            return next(plans)

        async def pages(urls, seen=None, limit=2):
            return [{"url": "https://a.test", "text": "fetched body"}]

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "fetch_source_pages", pages)

        context, _, _, _, _ = await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on", search_depth="multi"
        )

        assert "fetched body" in context

    @pytest.mark.asyncio
    async def test_search_without_results_raises_failure_event(self, monkeypatch):
        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", []

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(
            Aicode,
            "plan_search_actions",
            AsyncMock(return_value={"action": "search", "queries": ["q"], "urls": []}),
        )
        # 连续两轮（第一次为空重试，第二次直接失败）
        monkeypatch.setattr(
            Aicode,
            "fetch_source_pages",
            AsyncMock(return_value=[]),
        )
        context, _, _, _, warnings = await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on"
        )

        assert warnings
        assert "网络搜索失败" in context

    @pytest.mark.asyncio
    async def test_empty_history_context_is_not_appended(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "compress_conversation_history", AsyncMock(return_value="")
        )
        context, _, _, _, _ = await Aicode._build_context(
            1, "q", _Db(), 5, False, 3, search_mode="off"
        )
        assert "对话历史" not in context

    @pytest.mark.asyncio
    async def test_auto_mode_with_legacy_boolean_maps_to_on_and_off(self, monkeypatch):
        monkeypatch.setattr(Aicode, "ai_decide_search", AsyncMock(return_value=False))
        monkeypatch.setattr(Aicode, "fetch_source_pages", AsyncMock(return_value=[]))

        class Search:
            async def search_with_sources(self, **_kwargs):
                return "", [{"title": "T", "url": "https://a.test", "snippet": "S"}]

        monkeypatch.setattr(Aicode, "FreeWebSearch", Search)
        monkeypatch.setattr(
            Aicode,
            "plan_search_actions",
            AsyncMock(return_value={"action": "search", "queries": ["q"], "urls": []}),
        )

        _, _, did_search, _, _ = await Aicode._build_context(
            1, "q", _Db(), None, True, 3, search_mode="auto"
        )
        assert did_search is True

        _, _, did_search, _, _ = await Aicode._build_context(
            1, "q", _Db(), None, False, 3, search_mode="auto"
        )
        assert did_search is False

    @pytest.mark.asyncio
    async def test_attachment_without_identity_field_keeps_filename_only(self, monkeypatch):
        async def parse_file(*_args, **_kwargs):
            return "普通正文，没有身份字段", {"filename": "notes.txt"}

        monkeypatch.setattr(Aicode, "get_or_parse_file", parse_file)
        captured = {}

        async def plan(prompt, attachment_names=None, **_kwargs):
            captured["names"] = list(attachment_names or [])
            return {"action": "stop", "queries": [], "urls": []}

        monkeypatch.setattr(Aicode, "plan_search_actions", plan)
        monkeypatch.setattr(Aicode, "ai_decide_search", AsyncMock(return_value=False))

        await Aicode._build_context(
            1, "q", _Db(), None, None, 3, search_mode="on",
            files_to_parse=["notes.txt"],
        )

        assert captured["names"] == ["notes.txt"]


class TestCompressHistory:
    @pytest.mark.asyncio
    async def test_empty_history_returns_blank(self):
        db = _Db()
        db.execute.return_value = _Result(rows=[])
        assert await Aicode.compress_conversation_history(db, 1, 2) == ""

    @pytest.mark.asyncio
    async def test_history_is_reversed_and_truncated(self):
        long_prompt = "p" * 200
        long_response = "r" * 200
        records = [
            SimpleNamespace(prompt=long_prompt, response=long_response)
            for _ in range(40)
        ]
        db = _Db()
        db.execute.return_value = _Result(rows=records)

        context = await Aicode.compress_conversation_history(db, 1, 2)

        assert "历史记录过长，已截断" in context
        assert context.startswith("\n\n--- 对话历史 ---")

    @pytest.mark.asyncio
    async def test_short_history_completes_without_truncation(self):
        db = _Db()
        db.execute.return_value = _Result(
            rows=[SimpleNamespace(prompt="p", response="r")]
        )

        context = await Aicode.compress_conversation_history(db, 1, 2)

        assert "用户：p" in context
        assert "历史记录过长" not in context

    @pytest.mark.asyncio
    async def test_database_error_returns_blank(self):
        db = _Db()
        db.execute.side_effect = RuntimeError("boom")
        assert await Aicode.compress_conversation_history(db, 1, 2) == ""


class TestGetOrParseFile:
    def _record(self, filename, cache_valid=False):
        record = SimpleNamespace(
            filename=filename,
            parsed_content="cached",
            parsed_at=SimpleNamespace(isoformat=lambda: "2026-01-01"),
        )
        record.is_parse_cache_valid = MagicMock(return_value=cache_valid)
        record.update_parse_cache = MagicMock()
        return record

    @pytest.mark.asyncio
    async def test_missing_record_returns_404(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(return_value="path")
        )
        db = _Db()
        db.execute.return_value = _Result(value=None)

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, db)

        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_image_is_described_and_cached(self, monkeypatch, tmp_path):
        image = tmp_path / "pic.png"
        image.write_bytes(b"x")
        record = self._record("pic.png")
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(return_value=str(image))
        )
        monkeypatch.setattr(
            Aicode,
            "analyze_image",
            AsyncMock(return_value={"description": "一只猫", "model_used": "vis"}),
        )
        db = _Db()
        db.execute.return_value = _Result(value=record)

        content, metadata = await Aicode.get_or_parse_file(
            str(image), 1, None, db, parse_prompt="描述"
        )

        assert content == "一只猫"
        assert metadata["type"] == "image"
        record.update_parse_cache.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsupported_extension_returns_422(self, monkeypatch):
        record = self._record("binary.exe")
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(return_value="path")
        )
        db = _Db()
        db.execute.return_value = _Result(value=record)

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, db)

        assert error.value.status_code == 422

    @pytest.mark.asyncio
    async def test_document_parse_failure_returns_422(self, monkeypatch):
        record = self._record("doc.pdf")
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(return_value="path")
        )
        monkeypatch.setattr(
            Aicode, "parse_document", MagicMock(side_effect=RuntimeError("bad"))
        )
        db = _Db()
        db.execute.return_value = _Result(value=record)

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, db)

        assert error.value.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_document_returns_422(self, monkeypatch):
        record = self._record("doc.txt")
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(return_value="path")
        )
        monkeypatch.setattr(Aicode, "parse_document", MagicMock(return_value="  "))
        db = _Db()
        db.execute.return_value = _Result(value=record)

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, db)

        assert error.value.status_code == 422

    @pytest.mark.asyncio
    async def test_file_not_found_is_mapped(self, monkeypatch):
        monkeypatch.setattr(
            Aicode,
            "verify_file_access",
            AsyncMock(side_effect=FileNotFoundError("missing")),
        )

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, _Db())

        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_parse_error_maps_to_500(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "verify_file_access", AsyncMock(side_effect=RuntimeError("boom"))
        )

        with pytest.raises(HTTPException) as error:
            await Aicode.get_or_parse_file("path", 1, None, _Db())

        assert error.value.status_code == 500


class TestVerifyFileAccess:
    @pytest.mark.asyncio
    async def test_absolute_path_outside_uploads_is_forbidden(self, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("x")

        with pytest.raises(HTTPException) as error:
            await Aicode.verify_file_access(str(outside), 1, None, _Db())

        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_absolute_path_inside_uploads_is_relativized(self, monkeypatch):
        uploads = Path("./uploads").resolve()
        uploads.mkdir(parents=True, exist_ok=True)
        inside = uploads / "ok.txt"
        inside.write_text("x")
        db = _Db()
        db.execute.return_value = _Result(value=SimpleNamespace(file_path="ok.txt"))

        result = await Aicode.verify_file_access(str(inside), 1, 5, db)

        assert result == "ok.txt"

    @pytest.mark.asyncio
    async def test_exact_miss_falls_back_to_filename(self):
        db = _Db()
        first = _Result(value=None)
        second = _Result(value=SimpleNamespace(file_path="docs/a.txt"))
        db.execute = AsyncMock(side_effect=[first, second])

        result = await Aicode.verify_file_access("a.txt", 1, 5, db)

        assert result == "docs/a.txt"

    @pytest.mark.asyncio
    async def test_missing_record_forbids(self):
        db = _Db()
        db.execute = AsyncMock(return_value=_Result(value=None))

        with pytest.raises(HTTPException) as error:
            await Aicode.verify_file_access("a.txt", 1, None, db)

        assert error.value.status_code == 403


class TestModelSelection:
    def test_files_win_over_reasoning(self):
        assert Aicode.select_model_for_prompt("x", True, True) == "Qwen/Qwen3.5-4B"

    def test_reasoning_flag_selects_reasoning_model(self):
        assert Aicode.select_model_for_prompt("x", True, False) == Aicode.DEFAULT_REASONING_MODEL

    def test_analysis_keyword_selects_architect(self):
        assert Aicode.select_model_for_prompt("请分析原理", False, False) == Aicode.DEFAULT_ARCHITECT_MODEL

    def test_plain_prompt_uses_fast_model(self):
        assert Aicode.select_model_for_prompt("hi", False, False) == Aicode.DEFAULT_FAST_MODEL


class TestStreamExtraBranches:
    def _patch(self, monkeypatch):
        _patch_fit(monkeypatch)

        async def context(**kwargs):
            return "CTX", [], False, False, []

        monkeypatch.setattr(Aicode, "_build_context", context)
        monkeypatch.setattr(Aicode, "save_history_to_db", AsyncMock(return_value=1))
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())

    @pytest.mark.asyncio
    async def test_cancel_event_set_mid_stream_stops(self, monkeypatch):
        self._patch(monkeypatch)

        async def fake_stream(**kwargs):
            yield json.dumps({"choices": [{"delta": {"content": "x"}}]})
            kwargs["cancel_event"].set()
            yield json.dumps({"choices": [{"delta": {"content": "y"}}]})

        async def call(**kwargs):
            return fake_stream(**kwargs)

        monkeypatch.setattr(Aicode, "call_llm", call)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert not any("conversation_id" in event for event in events)

    @pytest.mark.asyncio
    async def test_cancelled_generator_without_saved_partial(self, monkeypatch):
        self._patch(monkeypatch)

        class Boom:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise asyncio.CancelledError

        monkeypatch.setattr(Aicode, "call_llm", AsyncMock(return_value=Boom()))
        monkeypatch.setattr(Aicode, "_store_partial_response", MagicMock(return_value=None))
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert all("interrupted" not in event for event in events)


class TestPromptAndStreamCleanup:
    def test_select_prompt_template_prefers_registry(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.skill_registry.get_skill",
            MagicMock(side_effect=lambda name: f"custom:{name}"),
        )
        assert Aicode._select_prompt_template("解释", True) == "custom:chat_reasoning_prompt"
        assert Aicode._select_prompt_template("写代码", False) == "custom:chat_code_prompt"
        assert Aicode._select_prompt_template("闲聊", False) == "custom:chat_general_prompt"

    def test_select_prompt_template_falls_back_to_defaults(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.skill_registry.get_skill",
            MagicMock(side_effect=RuntimeError("no registry")),
        )
        assert Aicode._select_prompt_template("解释", True) == Aicode.REASONING_PROMPT
        assert Aicode._select_prompt_template("写代码", False) == Aicode.CODE_PROMPT
        assert Aicode._select_prompt_template("闲聊", False) == Aicode.GENERAL_PROMPT

    def test_select_prompt_template_falls_back_when_registry_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.skill_registry.get_skill", MagicMock(return_value=None)
        )
        assert Aicode._select_prompt_template("解释", True) == Aicode.REASONING_PROMPT
        assert Aicode._select_prompt_template("写代码", False) == Aicode.CODE_PROMPT
        assert Aicode._select_prompt_template("闲聊", False) == Aicode.GENERAL_PROMPT

    @pytest.mark.asyncio
    async def test_aclose_llm_stream_noops_for_none(self):
        await Aicode._aclose_llm_stream(None)

    @pytest.mark.asyncio
    async def test_aclose_llm_stream_releases_and_closes(self):
        released = []
        closed = []

        class Stream:
            def release_now(self):
                released.append(True)

            async def aclose(self):
                closed.append(True)

        await Aicode._aclose_llm_stream(Stream())

        assert released and closed

    @pytest.mark.asyncio
    async def test_aclose_llm_stream_without_aclose(self):
        class Stream:
            pass

        await Aicode._aclose_llm_stream(Stream())

    @pytest.mark.asyncio
    async def test_aclose_llm_stream_swallows_close_errors(self):
        class Stream:
            async def aclose(self):
                raise RuntimeError("close failed")

        await Aicode._aclose_llm_stream(Stream())

    @pytest.mark.asyncio
    async def test_aclose_llm_stream_returns_on_cancellation(self, monkeypatch):
        class Stream:
            async def aclose(self):
                return None

        async def cancelled(coro):
            if hasattr(coro, "close"):
                coro.close()
            raise asyncio.CancelledError

        monkeypatch.setattr(Aicode.asyncio, "shield", cancelled)
        await Aicode._aclose_llm_stream(Stream())


class TestStreamResponse:
    def _patch_common(self, monkeypatch, chunks=None):
        _patch_fit(monkeypatch)

        async def context(**kwargs):
            await kwargs["on_stage"]({"stage": "answering", "status": "started"})
            return "CTX", [{"title": "T"}], True, False, []

        monkeypatch.setattr(Aicode, "_build_context", context)

        async def fake_stream(**kwargs):
            for chunk in chunks or [
                json.dumps({"choices": [{"delta": {"content": "你好"}}]})
            ]:
                yield chunk

        monkeypatch.setattr(Aicode, "call_llm", AsyncMock(return_value=fake_stream()))
        monkeypatch.setattr(Aicode, "save_history_to_db", AsyncMock(return_value=9))
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())

    @pytest.mark.asyncio
    async def test_stream_happy_path_yields_stages_and_conversation(self, monkeypatch):
        self._patch_common(monkeypatch)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) for chunk in [item async for item in stream]]

        assert events[0]["stage"] == "answering"
        assert any("conversation_id" in event for event in events)

    @pytest.mark.asyncio
    async def test_stream_disconnect_stores_partial(self, monkeypatch):
        self._patch_common(monkeypatch)
        monkeypatch.setattr(
            Aicode, "_store_partial_response", MagicMock(return_value="resume-1")
        )
        stream = Aicode.stream_response(
            "1", "q", "m", 3, _Db(), _Request(disconnected=True)
        )

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["interrupted"] is True
        assert events[-1]["resume_id"] == "resume-1"

    @pytest.mark.asyncio
    async def test_stream_disconnect_without_saved_partial(self, monkeypatch):
        self._patch_common(monkeypatch)
        monkeypatch.setattr(Aicode, "_store_partial_response", MagicMock(return_value=None))
        stream = Aicode.stream_response(
            "1", "q", "m", None, _Db(), _Request(disconnected=True)
        )

        events = [json.loads(chunk) async for chunk in stream]

        assert all("interrupted" not in event for event in events)

    @pytest.mark.asyncio
    async def test_stream_empty_response_reports_error(self, monkeypatch):
        self._patch_common(monkeypatch, chunks=[json.dumps({"choices": [{"delta": {}}]})])
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["error"].startswith("AI 生成响应为空")

    @pytest.mark.asyncio
    async def test_stream_cancelled_error_saves_partial(self, monkeypatch):
        _patch_fit(monkeypatch)

        async def context(**_kwargs):
            return "", [], False, False, []

        monkeypatch.setattr(Aicode, "_build_context", context)

        class Boom:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise asyncio.CancelledError

        monkeypatch.setattr(Aicode, "call_llm", AsyncMock(return_value=Boom()))
        monkeypatch.setattr(
            Aicode, "_store_partial_response", MagicMock(return_value="resume-2")
        )
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["resume_id"] == "resume-2"

    @pytest.mark.asyncio
    async def test_stream_value_error_reports_internal_error(self, monkeypatch):
        self._patch_common(monkeypatch)

        async def boom(**kwargs):
            raise ValueError("bad")

        monkeypatch.setattr(Aicode, "call_llm", boom)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["error"] == "服务内部错误，请稍后重试"

    @pytest.mark.asyncio
    async def test_stream_llm_call_error_reports_message(self, monkeypatch):
        self._patch_common(monkeypatch)
        from app.utils.aicloud.llm_caller import LLMCallError

        async def boom(**kwargs):
            raise LLMCallError("限流")

        monkeypatch.setattr(Aicode, "call_llm", boom)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert "限流" in events[-1]["error"]

    @pytest.mark.asyncio
    async def test_stream_unexpected_error_reports_internal_error(self, monkeypatch):
        self._patch_common(monkeypatch)

        async def boom(**kwargs):
            raise KeyError("unexpected")

        monkeypatch.setattr(Aicode, "call_llm", boom)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["error"] == "服务内部错误，请稍后重试"

    @pytest.mark.asyncio
    async def test_stream_context_overflow_retries_with_compact_context(self, monkeypatch):
        _patch_fit(monkeypatch, context="context body")
        calls = {"count": 0}

        async def context(**_kwargs):
            return "context body", [], False, False, []

        monkeypatch.setattr(Aicode, "_build_context", context)
        monkeypatch.setattr(
            Aicode, "is_context_length_error", MagicMock(return_value=True)
        )

        class Gen:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if calls["count"]:
                    raise StopAsyncIteration
                calls["count"] += 1
                return json.dumps({"choices": [{"delta": {"content": "ok"}}]})

        async def fake_llm(**kwargs):
            if kwargs["prompt"].startswith("RETRY"):
                return Gen()
            raise ValueError("maximum context length exceeded")

        # 第一次直接抛上下文错误，第二次返回流
        attempts = {"count": 0}

        async def call(**kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ValueError("maximum context length exceeded")
            return Gen()

        monkeypatch.setattr(Aicode, "call_llm", call)
        monkeypatch.setattr(Aicode, "save_history_to_db", AsyncMock(return_value=1))
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert attempts["count"] == 2
        assert any("conversation_id" in event for event in events)

    @pytest.mark.asyncio
    async def test_stream_context_overflow_without_context_is_raised(self, monkeypatch):
        _patch_fit(monkeypatch, context="")

        async def context(**_kwargs):
            return "", [], False, False, []

        monkeypatch.setattr(Aicode, "_build_context", context)
        monkeypatch.setattr(
            Aicode, "is_context_length_error", MagicMock(return_value=True)
        )

        async def boom(**kwargs):
            raise ValueError("maximum context length exceeded")

        monkeypatch.setattr(Aicode, "call_llm", boom)
        stream = Aicode.stream_response("1", "q", "m", None, _Db(), _Request())

        events = [json.loads(chunk) async for chunk in stream]

        assert events[-1]["error"] == "服务内部错误，请稍后重试"

    @pytest.mark.asyncio
    async def test_stream_uses_resume_prefix(self, monkeypatch):
        self._patch_common(monkeypatch)
        monkeypatch.setattr(
            Aicode, "_restore_partial_prefix", MagicMock(return_value="prefix:")
        )
        captured = {}

        async def fake_stream(**kwargs):
            captured["prompt"] = kwargs["prompt"]
            yield json.dumps({"choices": [{"delta": {"content": "tail"}}]})

        monkeypatch.setattr(Aicode, "call_llm", AsyncMock(side_effect=fake_stream))
        save = AsyncMock(return_value=2)
        monkeypatch.setattr(Aicode, "save_history_to_db", save)
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())
        stream = Aicode.stream_response(
            "1", "q", "m", None, _Db(), _Request(), resume_from="rid"
        )

        _ = [chunk async for chunk in stream]

        assert "prefix:" in captured["prompt"]
        assert save.await_args.kwargs["response"] == "prefix:tail"


class TestGenerateResponse:
    def _patch(self, monkeypatch, response="答案"):
        _patch_fit(monkeypatch)
        monkeypatch.setattr(
            Aicode,
            "_build_context",
            AsyncMock(return_value=("ctx", [{"title": "T"}], True, False, [])),
        )
        monkeypatch.setattr(
            Aicode,
            "call_llm",
            AsyncMock(
                return_value={
                    "choices": [{"message": {"content": response}}],
                    "usage": {"total_tokens": 4},
                }
            ),
        )
        monkeypatch.setattr(Aicode, "save_history_to_db", AsyncMock(return_value=8))
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())

    @pytest.mark.asyncio
    async def test_generate_response_saves_history(self, monkeypatch):
        self._patch(monkeypatch)

        result = await Aicode.generate_response("1", "q", "m", None, _Db())

        assert result["response"] == "答案"
        assert result["conversation_id"] == 8
        Aicode.save_history_to_db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_response_empty_is_not_saved(self, monkeypatch):
        self._patch(monkeypatch, response="  ")
        save = Aicode.save_history_to_db

        result = await Aicode.generate_response("1", "q", "m", None, _Db())

        assert result["conversation_id"] is None
        assert result["error"]
        save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_response_retries_on_context_overflow(self, monkeypatch):
        _patch_fit(monkeypatch, context="ctx")
        monkeypatch.setattr(
            Aicode,
            "_build_context",
            AsyncMock(return_value=("ctx", [], False, False, [])),
        )
        monkeypatch.setattr(
            Aicode, "is_context_length_error", MagicMock(return_value=True)
        )
        attempts = {"count": 0}

        async def call(**kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ValueError("maximum context length")
            return {"choices": [{"message": {"content": "重试答案"}}], "usage": {}}

        monkeypatch.setattr(Aicode, "call_llm", call)
        monkeypatch.setattr(Aicode, "save_history_to_db", AsyncMock(return_value=3))
        monkeypatch.setattr(Aicode, "_append_shared_chat_messages", AsyncMock())

        result = await Aicode.generate_response("1", "q", "m", None, _Db())

        assert attempts["count"] == 2
        assert result["response"] == "重试答案"

    @pytest.mark.asyncio
    async def test_generate_response_unrelated_error_is_raised(self, monkeypatch):
        self._patch(monkeypatch)
        monkeypatch.setattr(
            Aicode, "is_context_length_error", MagicMock(return_value=False)
        )
        monkeypatch.setattr(
            Aicode, "call_llm", AsyncMock(side_effect=RuntimeError("boom"))
        )

        with pytest.raises(RuntimeError):
            await Aicode.generate_response("1", "q", "m", None, _Db())


class TestGenerateCodeEndpoint:
    @pytest.mark.asyncio
    async def test_stream_request_returns_streaming_response(self, monkeypatch):
        monkeypatch.setattr(Aicode, "stream_response", MagicMock(return_value=iter([])))
        response = await Aicode.generate_code(
            _Request(),
            CodeRequest(prompt="q", stream=True),
            token={"sub": "1"},
            db=_Db(),
        )
        assert response.media_type == "text/event-stream"
        assert "no-cache" in response.headers["cache-control"]

    @pytest.mark.asyncio
    async def test_non_stream_request_delegates(self, monkeypatch):
        generate = AsyncMock(return_value={"response": "x"})
        monkeypatch.setattr(Aicode, "generate_response", generate)

        response = await Aicode.generate_code(
            _Request(),
            CodeRequest(prompt="q"),
            token={"sub": "1"},
            db=_Db(),
        )

        assert response == {"response": "x"}

    @pytest.mark.asyncio
    async def test_auto_model_uses_file_selection(self, monkeypatch):
        generate = AsyncMock(return_value={})
        monkeypatch.setattr(Aicode, "generate_response", generate)
        select = MagicMock(return_value="auto-model")
        monkeypatch.setattr(Aicode, "select_model_for_prompt", select)

        await Aicode.generate_code(
            _Request(),
            CodeRequest(
                prompt="q",
                image_path="pic.png",
                files=[FileAttachment(server_path="doc.txt")],
            ),
            token={"sub": "1"},
            db=_Db(),
        )

        assert select.call_args.kwargs["has_files"] is True
        assert generate.await_args.kwargs["files_to_parse"] == ["pic.png", "doc.txt"]

    @pytest.mark.asyncio
    async def test_explicit_model_skips_selection_and_duplicate_file(self, monkeypatch):
        generate = AsyncMock(return_value={})
        monkeypatch.setattr(Aicode, "generate_response", generate)
        select = MagicMock()
        monkeypatch.setattr(Aicode, "select_model_for_prompt", select)

        await Aicode.generate_code(
            _Request(),
            CodeRequest(
                prompt="q",
                model="explicit-model",
                image_path="same.txt",
                files=[FileAttachment(server_path="same.txt")],
            ),
            token={"sub": "1"},
            db=_Db(),
        )

        select.assert_not_called()
        assert generate.await_args.kwargs["files_to_parse"] == ["same.txt"]

    @pytest.mark.asyncio
    async def test_http_exception_is_reraised(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "generate_response", AsyncMock(side_effect=HTTPException(400, "x"))
        )
        with pytest.raises(HTTPException):
            await Aicode.generate_code(
                _Request(), CodeRequest(prompt="q"), token={"sub": "1"}, db=_Db()
            )

    @pytest.mark.asyncio
    async def test_unexpected_error_maps_to_500(self, monkeypatch):
        monkeypatch.setattr(
            Aicode, "generate_response", AsyncMock(side_effect=RuntimeError("x"))
        )
        with pytest.raises(HTTPException) as error:
            await Aicode.generate_code(
                _Request(), CodeRequest(prompt="q"), token={"sub": "1"}, db=_Db()
            )
        assert error.value.status_code == 500


class TestDeleteHistoryEndpoint:
    @pytest.mark.asyncio
    async def test_requires_token(self):
        with pytest.raises(HTTPException) as error:
            await Aicode.delete_code_history(
                conversation_ids=[], all=False, token={}, db=_Db()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_requires_ids_or_all(self):
        with pytest.raises(HTTPException) as error:
            await Aicode.delete_code_history(
                conversation_ids=[], all=False, token={"sub": "1"}, db=_Db()
            )
        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_deletes_all(self, monkeypatch):
        db = _Db()
        monkeypatch.setattr(Aicode, "_delete_shared_chat_data", AsyncMock(return_value=2))
        monkeypatch.setattr(Aicode, "invalidate_history_caches", AsyncMock())

        result = await Aicode.delete_code_history(
            conversation_ids=[], all=True, token={"sub": "1"}, db=db
        )

        assert result["count"] == 3
        assert result["shared_count"] == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_selected_ids(self, monkeypatch):
        db = _Db()
        monkeypatch.setattr(Aicode, "_delete_shared_chat_data", AsyncMock(return_value=1))
        monkeypatch.setattr(Aicode, "invalidate_history_caches", AsyncMock())

        result = await Aicode.delete_code_history(
            conversation_ids=[5], all=False, token={"sub": "1"}, db=db
        )

        assert result["conversation_ids"] == [5]

    @pytest.mark.asyncio
    async def test_database_error_maps_to_500(self, monkeypatch):
        db = _Db()
        db.execute.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as error:
            await Aicode.delete_code_history(
                conversation_ids=[5], all=False, token={"sub": "1"}, db=db
            )

        assert error.value.status_code == 500


class TestResumeEndpoints:
    @pytest.mark.asyncio
    async def test_resume_missing_cache_returns_404(self, monkeypatch):
        monkeypatch.setattr(
            Aicode.partial_response_store, "get_partial_response", MagicMock(return_value=None)
        )
        with pytest.raises(HTTPException) as error:
            await Aicode.resume_code_generation(
                _Request(), {"resume_id": "x"}, token={"sub": "1"}, db=_Db()
            )
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_other_user_forbidden(self, monkeypatch):
        monkeypatch.setattr(
            Aicode.partial_response_store,
            "get_partial_response",
            MagicMock(return_value={"user_id": "2", "partial_response": "x"}),
        )
        with pytest.raises(HTTPException) as error:
            await Aicode.resume_code_generation(
                _Request(), {"resume_id": "x"}, token={"sub": "1"}, db=_Db()
            )
        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_resume_with_new_prompt_and_options(self, monkeypatch):
        cache = {
            "user_id": "1",
            "partial_response": "partial",
            "model": "m",
            "prompt": "orig",
            "conversation_id": 4,
        }
        monkeypatch.setattr(
            Aicode.partial_response_store, "get_partial_response", MagicMock(return_value=cache)
        )
        captured = {}

        def fake_stream(**kwargs):
            captured.update(kwargs)
            return iter([])

        monkeypatch.setattr(Aicode, "stream_response", fake_stream)

        await Aicode.resume_code_generation(
            _Request(),
            {
                "resume_id": "x",
                "prompt": "new",
                "model": "m2",
                "use_reasoning": True,
                "enable_search": False,
                "search_count": 9,
            },
            token={"sub": "1"},
            db=_Db(),
        )

        assert "new" in captured["prompt"]
        assert captured["model"] == "m2"
        assert captured["search_count"] == 9

    @pytest.mark.asyncio
    async def test_resume_without_new_prompt_uses_original(self, monkeypatch):
        cache = {"user_id": "1", "partial_response": "p", "prompt": "orig", "model": "m"}
        monkeypatch.setattr(
            Aicode.partial_response_store, "get_partial_response", MagicMock(return_value=cache)
        )
        captured = {}
        monkeypatch.setattr(
            Aicode, "stream_response", MagicMock(side_effect=lambda **kw: captured.update(kw) or iter([]))
        )

        await Aicode.resume_code_generation(
            _Request(), {"resume_id": "x"}, token={"sub": "1"}, db=_Db()
        )

        assert captured["prompt"] == "orig"

    @pytest.mark.asyncio
    async def test_get_partial_response_missing(self, monkeypatch):
        monkeypatch.setattr(
            Aicode.partial_response_store, "get_partial_response", MagicMock(return_value=None)
        )
        with pytest.raises(HTTPException) as error:
            await Aicode.get_partial_response("x", token={"sub": "1"})
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_partial_response_forbidden(self, monkeypatch):
        monkeypatch.setattr(
            Aicode.partial_response_store,
            "get_partial_response",
            MagicMock(return_value={"user_id": "2"}),
        )
        with pytest.raises(HTTPException) as error:
            await Aicode.get_partial_response("x", token={"sub": "1"})
        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_partial_response_returns_payload(self, monkeypatch):
        monkeypatch.setattr(
            Aicode.partial_response_store,
            "get_partial_response",
            MagicMock(
                return_value={
                    "user_id": "1",
                    "prompt": "p",
                    "partial_response": "r",
                    "model": "m",
                    "timestamp": "t",
                }
            ),
        )
        result = await Aicode.get_partial_response("x", token={"sub": "1"})
        assert result["partial_response"] == "r"
