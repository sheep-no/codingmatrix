"""补丁/修复链路的文件读写必须离开事件循环。

`CodePatcher.apply_patch_to_file`（读原文件 + 原子写回）、
`ErrorRecoveryLoop` 的临时文件写入、`FilesMixin._validate_and_review_file`
错误恢复后的落盘都在协程里同步读写文件；这些函数在生成/修复协程中被并发
调用，阻塞会让事件循环停摆。这里用线程 id 断言它们在工作线程执行。
"""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent.code_patcher as code_patcher
from app.agent.code_patcher import CodePatcher
from app.agent.error_recovery import ErrorRecoveryLoop
from app.agent.orchestrator_files import FilesMixin


def _read_text_spy(seen, real):
    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real(self, *args, **kwargs)

    return spy


@pytest.mark.asyncio
async def test_code_patcher_reads_and_writes_off_event_loop(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    patch = (
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-line1\n"
        "+modified\n"
        " line2\n"
        " line3\n"
    )
    main_thread = threading.get_ident()
    reads = []
    writes = []
    real_read_text = Path.read_text
    real_atomic_write = code_patcher._atomic_write_text

    def atomic_write_spy(path, text):
        writes.append(threading.get_ident())
        return real_atomic_write(path, text)

    monkeypatch.setattr(Path, "read_text", _read_text_spy(reads, real_read_text))
    monkeypatch.setattr(code_patcher, "_atomic_write_text", atomic_write_spy)

    result = await CodePatcher().apply_patch_to_file(target, patch, output_dir=tmp_path)

    assert result.success is True
    assert reads and reads[0] != main_thread, "原文件读取仍在事件循环线程"
    assert writes and all(t != main_thread for t in writes), "原子写仍在事件循环线程"


@pytest.mark.asyncio
async def test_error_recovery_temp_write_off_event_loop(tmp_path, monkeypatch):
    main_thread = threading.get_ident()
    seen = []
    real_write_text = Path.write_text

    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)

    class _Validator:
        async def validate_single_file(self, path):
            return {"is_valid": True}

    loop = ErrorRecoveryLoop(_Validator(), reviewer=object())
    target = tmp_path / "main.py"
    seen.clear()

    ok, content = await loop.validate_and_fix(
        target, "x = 1\n", "主模块", "some-model"
    )

    assert ok is True
    assert content == "x = 1\n"
    assert seen and seen[0] != main_thread, "临时文件写入仍在事件循环线程"


@pytest.mark.asyncio
async def test_orchestrator_files_write_off_event_loop(tmp_path, monkeypatch):
    main_thread = threading.get_ident()
    seen = []
    real_write_text = Path.write_text

    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)

    class _Validator:
        def get_cached_validation_by_key(self, key):
            return None

    class _ErrorRecovery:
        async def validate_and_fix(self, **kwargs):
            return True, kwargs["content"]

    class _Host(FilesMixin):
        pass

    host = _Host()
    host.enable_error_recovery = True
    host.enable_review = False
    host.enable_validation = False
    host.model_assignment = SimpleNamespace(backend_model="some-model")
    host.output_dir = tmp_path
    host.validator = _Validator()
    host.error_recovery = _ErrorRecovery()
    host.callback = None

    ok, content = await host._validate_and_review_file("pkg/main.py", "x = 1\n", "主模块")

    assert ok is True
    assert content == "x = 1\n"
    assert seen and seen[0] != main_thread, "错误恢复后的落盘仍在事件循环线程"
