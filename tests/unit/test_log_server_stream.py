"""LogService 日志流轮转感知回归（db_layer.md DB9）。

原实现 position 只增不减，日志归档/轮转后新文件更短，
seek 到旧 position 永远读不到内容，流式端点静默失明。
"""

import asyncio
import importlib
import json
from pathlib import Path

log_server = importlib.import_module("app.db.log_server")


def _write(path: Path, message: str) -> None:
    path.write_text(
        json.dumps({"level": "INFO", "message": message}) + "\n",
        encoding="utf-8",
    )


async def _next(gen, timeout: float = 3.0):
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


async def _prime(gen) -> None:
    """让惰性 generator 先跑起来，在文件末尾定好 position 再进入轮询。"""
    pending = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.5)
    return pending


async def test_stream_pushes_appended_lines(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    gen = log_server.LogService(log_dir=str(tmp_path)).stream_logs_with_filter(
        log_type="app"
    )
    try:
        pending = await _prime(gen)
        _write(log_file, "first-entry")
        assert "first-entry" in await asyncio.wait_for(pending, timeout=3)
    finally:
        await gen.aclose()


async def test_stream_recovers_after_rotation(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("", encoding="utf-8")
    gen = log_server.LogService(log_dir=str(tmp_path)).stream_logs_with_filter(
        log_type="app"
    )
    try:
        pending = await _prime(gen)
        _write(log_file, "before-rotation-with-a-long-message")
        assert "before-rotation" in await asyncio.wait_for(pending, timeout=3)

        # 轮转：归档后新建同名文件，长度小于已消费的 position
        log_file.write_text("", encoding="utf-8")
        _write(log_file, "after-rotate")
        assert "after-rotate" in await _next(gen)
    finally:
        await gen.aclose()


async def test_stream_reports_missing_file(tmp_path):
    gen = log_server.LogService(
        log_dir=str(tmp_path / "missing")
    ).stream_logs_with_filter(log_type="app")
    try:
        assert "日志文件不存在" in await _next(gen)
    finally:
        await gen.aclose()
