"""LogService 边界补测：解析、过滤与流异常退避。"""

import asyncio
import json

import pytest

from app.db.log_server import LogFilter, LogService


def test_parse_log_line_skips_blank():
    assert LogService()._parse_log_line("   ") is None


def test_parse_log_line_reads_json():
    parsed = LogService()._parse_log_line('{"level": "INFO", "message": "x"}')

    assert parsed == {"level": "INFO", "message": "x"}


def test_parse_log_line_reads_python_format():
    line = "2024-01-02 03:04:05 - app.services.chat[123] - ERROR - main.py:42 - boom"

    parsed = LogService()._parse_log_line(line)

    assert parsed["name"] == "app.services.chat"
    assert parsed["process"] == "123"
    assert parsed["level"] == "ERROR"
    assert parsed["location"] == "main.py:42"
    assert parsed["message"] == "boom"
    assert parsed["_raw"] == line


def test_parse_log_line_falls_back_to_unknown():
    parsed = LogService()._parse_log_line("plain text")

    assert parsed["level"] == "UNKNOWN"
    assert parsed["message"] == "plain text"


def test_apply_filters_without_filters():
    assert LogService()._apply_filters({"level": "INFO"}, {}) is True


def test_apply_filters_level_and_keyword():
    service = LogService()

    assert service._apply_filters({"level": "INFO"}, {"level": "error"}) is False
    assert service._apply_filters({"level": "ERROR"}, {"level": "error"}) is True
    assert service._apply_filters({"level": "INFO", "message": "abc"}, {"keyword": "zzz"}) is False
    assert service._apply_filters({"level": "INFO", "message": "ABC"}, {"keyword": "ab"}) is True


def test_apply_filters_non_string_message_passes_keyword():
    assert LogService()._apply_filters({"message": {"nested": 1}}, {"keyword": "x"}) is True


def test_log_filter_to_dict():
    assert LogFilter(level="ERROR", keyword="ws").to_dict() == {
        "level": "ERROR",
        "keyword": "ws",
    }


async def _next(gen, timeout=3.0):
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


async def test_stream_skips_service_self_logs(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(log_type="app")
    try:
        pending = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.4)
        log_file.write_text(
            json.dumps({"message": "日志流开启"}) + "\n"
            + json.dumps({"message": "keep-me"}) + "\n",
            encoding="utf-8",
        )

        assert "keep-me" in await asyncio.wait_for(pending, timeout=3)
    finally:
        await gen.aclose()


async def test_stream_applies_filters(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(
        log_type="app", filters={"level": "ERROR", "keyword": "boom"}
    )
    try:
        pending = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.4)
        log_file.write_text(
            json.dumps({"level": "INFO", "message": "boom"}) + "\n"
            + json.dumps({"level": "ERROR", "message": "nope"}) + "\n"
            + json.dumps({"level": "ERROR", "message": "boom happened"}) + "\n",
            encoding="utf-8",
        )

        payload = json.loads(await asyncio.wait_for(pending, timeout=3))

        assert payload["message"] == "boom happened"
    finally:
        await gen.aclose()


async def test_stream_reports_first_error_and_backs_off(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    original_open = log_server_open = __import__("aiofiles").open

    def boom(*_args, **_kwargs):
        raise OSError("read failed")

    monkeypatch.setattr("aiofiles.open", boom)
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    gen = service.stream_logs_with_filter(log_type="app")
    try:
        payload = json.loads(await _next(gen))

        assert "日志流异常" in payload["message"]
        assert payload["error"] == "read failed"
        with pytest.raises(asyncio.CancelledError):
            await gen.__anext__()
        assert slept == [0.3]
    finally:
        await gen.aclose()
        monkeypatch.setattr("aiofiles.open", original_open)


async def test_stream_handles_cancellation(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(log_type="app")

    async def cancel_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("asyncio.sleep", cancel_sleep)
    try:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await gen.aclose()


async def test_stream_emits_heartbeat_every_ten_errors(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))

    def boom(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr("aiofiles.open", boom)
    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) >= 10:
            raise asyncio.CancelledError

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    gen = service.stream_logs_with_filter(log_type="app")
    messages = []
    try:
        async for chunk in gen:
            messages.append(json.loads(chunk))
    except asyncio.CancelledError:
        pass
    finally:
        await gen.aclose()

    assert len(messages) == 2
    assert messages[0]["level"] == "ERROR"


async def test_stream_missing_file_generator_finishes(tmp_path):
    gen = LogService(log_dir=str(tmp_path / "missing")).stream_logs_with_filter(
        log_type="app"
    )

    assert "日志文件不存在" in await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_stream_skips_internal_blank_lines(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(log_type="app")
    try:
        pending = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.4)
        log_file.write_text(
            json.dumps({"message": "keep"}) + "\n\n"
            + json.dumps({"message": "other"}) + "\n",
            encoding="utf-8",
        )

        first = json.loads(await asyncio.wait_for(pending, timeout=3))
        second = json.loads(await _next(gen))

        assert first["message"] == "keep"
        assert second["message"] == "other"
    finally:
        await gen.aclose()


async def test_stream_polls_empty_file_without_output(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(log_type="app")
    try:
        pending = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.8)
        log_file.write_text(json.dumps({"message": "later"}) + "\n", encoding="utf-8")

        payload = json.loads(await asyncio.wait_for(pending, timeout=3))

        assert payload["message"] == "later"
    finally:
        await gen.aclose()


async def test_stream_survives_file_rotation_between_polls(tmp_path, monkeypatch):
    import app.db.log_server as log_server_module

    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    service = LogService(log_dir=str(tmp_path))
    gen = service.stream_logs_with_filter(log_type="app")
    polls = {"count": 0}

    async def fake_sleep(_seconds):
        polls["count"] += 1
        if polls["count"] == 1:
            log_file.unlink()
            return
        raise asyncio.CancelledError

    monkeypatch.setattr(log_server_module.asyncio, "sleep", fake_sleep)
    try:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await gen.aclose()
