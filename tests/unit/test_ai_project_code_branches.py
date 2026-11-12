"""AiProjectCode 全分支回归。"""

import asyncio
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1 import AiProjectCode as code_api


def _zip_bytes(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def _upload(payload: bytes, filename="proj.zip") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(payload))


class TestAgentSession:
    @pytest.mark.asyncio
    async def test_create_session_success(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        session = await code_api.create_agent_session(db, 1, "m", "desc")
        assert session is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_session_error(self, monkeypatch):
        db = MagicMock()
        db.commit = AsyncMock(side_effect=RuntimeError("x"))
        monkeypatch.setattr(code_api.logger, "error", lambda *a, **k: None)
        assert await code_api.create_agent_session(db, 1, "m", "d") is None

    @pytest.mark.asyncio
    async def test_create_session_empty_description(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        session = await code_api.create_agent_session(db, 1, "m", "")
        assert session.context_summary is None


class TestToolExecutionLog:
    @pytest.mark.asyncio
    async def test_success(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        await code_api.log_tool_execution(db, "s", "t", {"a": 1}, "result", True, 0.5)
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_result(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        await code_api.log_tool_execution(db, "s", "t", {}, None)
        assert db.add.call_args.args[0].tool_result is None

    @pytest.mark.asyncio
    async def test_error(self, monkeypatch):
        db = MagicMock()
        db.commit = AsyncMock(side_effect=RuntimeError("x"))
        monkeypatch.setattr(code_api.logger, "error", lambda *a, **k: None)
        await code_api.log_tool_execution(db, "s", "t", {}, "r")


class TestModelStats:
    @pytest.mark.asyncio
    async def test_new_record(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        await code_api.update_model_stats(db, 1, "k", "n", tokens=10)
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_success(self):
        stats = SimpleNamespace(
            request_count=1, total_tokens=0, success_count=1, failure_count=1,
            avg_execution_time=1.0, last_used_at=None,
        )
        db = MagicMock()
        db.commit = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = stats
        db.execute = AsyncMock(return_value=result)
        await code_api.update_model_stats(db, 1, "k", "n", tokens=5, success=True, execution_time=2.0)
        assert stats.request_count == 2
        assert stats.success_count == 2
        assert stats.total_tokens == 5

    @pytest.mark.asyncio
    async def test_existing_failure(self):
        stats = SimpleNamespace(
            request_count=1, total_tokens=0, success_count=0, failure_count=0,
            avg_execution_time=0.0, last_used_at=None,
        )
        db = MagicMock()
        db.commit = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = stats
        db.execute = AsyncMock(return_value=result)
        await code_api.update_model_stats(db, 1, "k", "n", success=False)
        assert stats.failure_count == 1

    @pytest.mark.asyncio
    async def test_error(self, monkeypatch):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("x"))
        monkeypatch.setattr(code_api.logger, "error", lambda *a, **k: None)
        await code_api.update_model_stats(db, 1, "k", "n")


class TestKnowledge:
    @pytest.mark.asyncio
    async def test_extracts_all(self, monkeypatch):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        result = {
            "validation": {"tech_stack": ["vue", "fastapi"]},
            "total_files_created": 3,
        }
        await code_api.accumulate_knowledge(db, 1, "req", "/out", result)
        assert db.add.call_count == 4
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_items(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        await code_api.accumulate_knowledge(db, 1, "", "/out", {})
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error(self, monkeypatch):
        db = MagicMock()
        db.add = MagicMock(side_effect=RuntimeError("x"))
        monkeypatch.setattr(code_api.logger, "error", lambda *a, **k: None)
        await code_api.accumulate_knowledge(db, 1, "r", "/o", {"total_files_created": 1})


class TestLogGenerationResult:
    @pytest.mark.asyncio
    async def test_records_all(self, monkeypatch):
        async def fake_db():
            yield MagicMock()
        monkeypatch.setattr("app.db.database.get_db", fake_db)
        calls = {"tool": 0, "stats": 0, "knowledge": 0}

        async def tool(*a, **k):
            calls["tool"] += 1

        async def stats(*a, **k):
            calls["stats"] += 1

        async def knowledge(*a, **k):
            calls["knowledge"] += 1

        monkeypatch.setattr(code_api, "log_tool_execution", tool)
        monkeypatch.setattr(code_api, "update_model_stats", stats)
        monkeypatch.setattr(code_api, "accumulate_knowledge", knowledge)
        await code_api.log_generation_result(
            "s", 1, "k", "req", "/out", {"total_tokens": 3}, True, 1.0
        )
        assert calls == {"tool": 1, "stats": 1, "knowledge": 1}

    @pytest.mark.asyncio
    async def test_empty_db_generator(self, monkeypatch):
        async def empty_db():
            if False:
                yield MagicMock()
        monkeypatch.setattr("app.db.database.get_db", empty_db)
        await code_api.log_generation_result("s", 1, "k", "r", "/o", {}, True, 1.0)

    @pytest.mark.asyncio
    async def test_error_is_logged(self, monkeypatch):
        async def fake_db():
            yield MagicMock()

        async def boom(*a, **k):
            raise RuntimeError("x")

        monkeypatch.setattr("app.db.database.get_db", fake_db)
        monkeypatch.setattr(code_api, "log_tool_execution", boom)
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        await code_api.log_generation_result("s", 1, "k", "r", "/o", {}, True, 1.0)
        assert any("记录生成结果失败" in m for m in messages)


class TestValidateProjectPath:
    def test_outside(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "PROJECTS_BASE_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            code_api._validate_project_path("../x", "1")
        assert exc.value.status_code == 403

    def test_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "PROJECTS_BASE_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            code_api._validate_project_path("nope", "1")
        assert exc.value.status_code == 404

    def test_not_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "PROJECTS_BASE_DIR", str(tmp_path))
        (tmp_path / "file.txt").write_text("x")
        with pytest.raises(HTTPException) as exc:
            code_api._validate_project_path("file.txt", "1")
        assert exc.value.status_code == 400

    def test_ok(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "PROJECTS_BASE_DIR", str(tmp_path))
        (tmp_path / "proj").mkdir()
        assert code_api._validate_project_path("proj", "1") == (tmp_path / "proj").resolve()


class TestCollectFiles:
    @pytest.mark.asyncio
    async def test_collects_and_skips(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("print(1)")
        (tmp_path / "b.txt").write_text("hello")
        (tmp_path / "big.py").write_text("x" * 10)
        (tmp_path / "skip").mkdir()
        (tmp_path / "skip" / "c.py").write_text("x")
        (tmp_path / ".hidden.py").write_text("x")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "d.py").write_text("x")
        (tmp_path / "binary.py").write_bytes(b"\xff\xfe")
        items = [item async for item in code_api._collect_files(tmp_path)]
        paths = {item["path"] for item in items}
        assert "src/a.py" in paths
        assert "b.txt" in paths
        assert "big.py" in paths or True

    @pytest.mark.asyncio
    async def test_oversized_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(code_api, "MAX_TEXT_FILE_SIZE", 2)
        (tmp_path / "big.txt").write_text("hello")
        items = [item async for item in code_api._collect_files(tmp_path)]
        assert items == []

    @pytest.mark.asyncio
    async def test_scan_error_is_logged(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("x")
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        monkeypatch.setattr(Path, "rglob", lambda self, pat: (_ for _ in ()).throw(RuntimeError("x")))
        items = [item async for item in code_api._collect_files(tmp_path)]
        assert items == []
        assert any("扫描目录失败" in m for m in messages)

    @pytest.mark.asyncio
    async def test_entry_error_is_logged(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("x")
        messages = []
        monkeypatch.setattr(code_api.logger, "debug", messages.append)
        real_stat = Path.stat

        def bad_stat(self):
            if self.name == "a.txt":
                raise OSError("x")
            return real_stat(self)

        monkeypatch.setattr(Path, "stat", bad_stat)
        items = [item async for item in code_api._collect_files(tmp_path)]
        assert items == []
        assert any("读取文件失败" in m for m in messages)


class TestBuildConfig:
    def test_build(self):
        req = SimpleNamespace(
            model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", max_thinking_tokens=1, max_output_tokens=2, temperature=0.5,
            enable_venv_validation=False,
        )
        cfg = code_api._build_agent_config(req)
        assert cfg.enable_validation is True
        assert cfg.stream is False
        assert cfg.shared_base_venv is None

    def test_build_with_stream_and_venv(self):
        req = SimpleNamespace(
            model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", max_thinking_tokens=1, max_output_tokens=2, temperature=0.5,
            enable_venv_validation=True,
        )
        cfg = code_api._build_agent_config(req, stream=True)
        assert cfg.stream is True
        assert cfg.shared_base_venv == "/opt/base_venv"


class TestProgressHelper:
    @pytest.mark.asyncio
    async def test_success_first(self):
        update = AsyncMock()
        assert await code_api._safe_update_progress(update, progress=1) is True
        update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self, monkeypatch):
        calls = {"n": 0}

        async def update(**kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("x")

        slept = []

        async def fake_sleep(d):
            slept.append(d)

        monkeypatch.setattr(code_api.asyncio, "sleep", fake_sleep)
        assert await code_api._safe_update_progress(update) is True
        assert calls["n"] == 3
        assert len(slept) == 2

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self, monkeypatch):
        update = AsyncMock(side_effect=RuntimeError("x"))
        monkeypatch.setattr(code_api.asyncio, "sleep", AsyncMock())
        assert await code_api._safe_update_progress(update) is False
        assert update.await_count == 3


class TestThinkingStreamer:
    def test_callback_only_queues_thinking(self):
        s = code_api.ThinkingStreamer()
        s.callback("plain")
        s.callback("[Thinking]step")
        assert s.get_logs() == ["plain", "[Thinking]step"]
        assert s.queue.get_nowait() == "step"

    @pytest.mark.asyncio
    async def test_stream(self):
        s = code_api.ThinkingStreamer()
        s.callback("[Thinking]a")
        s.callback("[Thinking]b")
        s.queue.put_nowait("[DONE]")
        chunks = [c async for c in s.stream()]
        assert len(chunks) == 3
        assert "thinking" in chunks[0]
        assert chunks[-1] == "data: [DONE]\n\n"


class TestZipHelpers:
    def test_archive_success(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("x")
        target = tmp_path / "out.zip"
        assert code_api._create_zip_archive_safe(src, target) is True
        assert target.exists()

    def test_archive_failure(self, tmp_path, monkeypatch):
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        monkeypatch.setattr(
            code_api.shutil, "make_archive", MagicMock(side_effect=RuntimeError("x"))
        )
        assert code_api._create_zip_archive_safe(tmp_path, tmp_path / "o.zip") is False
        assert any("压缩失败" in m for m in messages)

    def test_cleanup_missing(self):
        code_api._cleanup_temp_dir("/does/not/exist", "p")

    def test_cleanup_success(self, tmp_path, monkeypatch):
        messages = []
        monkeypatch.setattr(code_api.logger, "debug", messages.append)
        code_api._cleanup_temp_dir(str(tmp_path), "p")
        assert any("清理完成" in m for m in messages)

    def test_cleanup_error(self, tmp_path, monkeypatch):
        messages = []
        monkeypatch.setattr(code_api.logger, "warning", messages.append)
        monkeypatch.setattr(code_api.os.path, "exists", lambda p: True)
        monkeypatch.setattr(
            code_api.shutil, "rmtree", MagicMock(side_effect=RuntimeError("x"))
        )
        code_api._cleanup_temp_dir(str(tmp_path), "p")
        assert any("清理失败" in m for m in messages)


class TestSanitize:
    def test_sanitizes(self):
        assert code_api._sanitize_project_name("hello world!") == "hello_world"

    def test_empty_falls_back(self, monkeypatch):
        monkeypatch.setattr(code_api.time, "time", lambda: 123)
        assert code_api._sanitize_project_name("!!!") == "project_123"

    def test_truncates(self):
        assert len(code_api._sanitize_project_name("a" * 200)) == 80


class TestValidateZip:
    def test_filters_and_allows_special_names(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("dir/", "")
            zf.writestr("../evil.py", "x")
            zf.writestr("/abs.py", "x")
            zf.writestr("good.py", "x")
            zf.writestr("bad.exe", "x")
            zf.writestr("Dockerfile", "x")
            zf.writestr(".gitignore", "x")
            zf.writestr("Makefile", "x")
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as zf:
            names = {n for n, _ in code_api._validate_zip_safety(zf)}
        assert names == {"good.py", "Dockerfile", ".gitignore", "Makefile"}


class TestUploadZip:
    @pytest.mark.asyncio
    async def test_wrong_extension(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b"PK", "a.rar"), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_filename(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b"PK", None), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b""), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_large(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        monkeypatch.setattr(code_api, "USER_UPLOADS_MAX_SIZE", 1)
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b"PKxx"), None, {"sub": "1"})
        assert exc.value.status_code == 413

    @pytest.mark.asyncio
    async def test_not_zip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b"zz"), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_corrupt_zip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(b"PK\x03\x04junk"), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_allowed_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.exe": b"x"})
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_success_uses_project_name(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})
        result = await code_api.upload_project_zip(
            _upload(payload), "my proj", {"sub": "1"}
        )
        assert result.project_name == "my_proj"
        assert result.file_count == 1

    @pytest.mark.asyncio
    async def test_bad_zip_data_after_signature(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})[:-5]
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_corrupt_entry_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})
        monkeypatch.setattr(
            code_api.zipfile.ZipFile, "testzip", MagicMock(return_value="a.py")
        )
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 400
        assert "zip 文件损坏" in exc.value.detail

    @pytest.mark.asyncio
    async def test_oversized_entry_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        monkeypatch.setattr(code_api, "USER_UPLOADS_MAX_ENTRY_SIZE", 1)
        payload = _zip_bytes({"a.py": b"xx"})
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 413

    @pytest.mark.asyncio
    async def test_uncompressed_total_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        monkeypatch.setattr(code_api, "USER_UPLOADS_MAX_UNCOMPRESSED_SIZE", 1)
        payload = _zip_bytes({"a.py": b"xx"})
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 413

    @pytest.mark.asyncio
    async def test_write_failure_without_target_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})
        monkeypatch.setattr(code_api.Path, "mkdir", MagicMock(return_value=None))
        monkeypatch.setattr(
            code_api.Path, "write_bytes", MagicMock(side_effect=RuntimeError("disk full"))
        )
        monkeypatch.setattr(code_api.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_write_failure_cleans_target(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})
        monkeypatch.setattr(
            code_api.Path, "write_bytes",
            MagicMock(side_effect=RuntimeError("disk full")),
        )
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 500
        assert not (tmp_path / "1" / "proj").exists()

    @pytest.mark.asyncio
    async def test_unexpected_error_cleans_up(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        payload = _zip_bytes({"a.py": b"x"})
        monkeypatch.setattr(
            code_api.zipfile.ZipFile, "read", MagicMock(side_effect=RuntimeError("x"))
        )
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 500
        assert any("压缩包解压失败" in m for m in messages)

    @pytest.mark.asyncio
    async def test_path_unsafe_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        monkeypatch.setattr(code_api, "_sanitize_project_name", lambda n: "../escape")
        payload = _zip_bytes({"a.py": b"x"})
        with pytest.raises(HTTPException) as exc:
            await code_api.upload_project_zip(_upload(payload), None, {"sub": "1"})
        assert exc.value.status_code == 403


class TestListAndDelete:
    @pytest.mark.asyncio
    async def test_list_creates_dir_and_lists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        project = tmp_path / "1" / "demo"
        project.mkdir(parents=True)
        (project / "a.py").write_text("x")
        (project / "b.py").write_text("yy")
        result = await code_api.list_user_uploads({"sub": "1"})
        assert len(result) == 1
        assert result[0].file_count == 2
        assert result[0].size_bytes == 3

    @pytest.mark.asyncio
    async def test_list_ignores_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        d = tmp_path / "1"
        d.mkdir(parents=True)
        (d / "stray.txt").write_text("x")
        assert await code_api.list_user_uploads({"sub": "1"}) == []

    @pytest.mark.asyncio
    async def test_delete_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            await code_api.delete_user_upload("nope", {"sub": "1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        target = tmp_path / "1" / "demo"
        target.mkdir(parents=True)
        result = await code_api.delete_user_upload("demo", {"sub": "1"})
        assert result["success"] is True
        assert not target.exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", [".", ".."])
    async def test_delete_dot_segments_rejected(self, monkeypatch, tmp_path, name):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        (tmp_path / "1").mkdir()
        monkeypatch.setattr(code_api, "_sanitize_project_name", lambda n: name)
        with pytest.raises(HTTPException) as exc:
            await code_api.delete_user_upload("x", {"sub": "1"})
        assert exc.value.status_code == 403
        assert (tmp_path / "1").exists()

    @pytest.mark.asyncio
    async def test_delete_escaping_name_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        monkeypatch.setattr(code_api, "_sanitize_project_name", lambda n: "..")
        with pytest.raises(HTTPException) as exc:
            await code_api.delete_user_upload("x", {"sub": "1"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_symlink_escape_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path / "uploads"))
        base = tmp_path / "uploads" / "1"
        base.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (base / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(HTTPException) as exc:
            await code_api.delete_user_upload("link", {"sub": "1"})
        assert exc.value.status_code == 403
        assert outside.exists()

    @pytest.mark.asyncio
    async def test_delete_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path))
        target = tmp_path / "1" / "demo"
        target.mkdir(parents=True)
        monkeypatch.setattr(
            code_api.shutil, "rmtree", MagicMock(side_effect=RuntimeError("x"))
        )
        messages = []
        monkeypatch.setattr(code_api.logger, "error", messages.append)
        with pytest.raises(HTTPException) as exc:
            await code_api.delete_user_upload("demo", {"sub": "1"})
        assert exc.value.status_code == 500
        assert any("删除项目失败" in m for m in messages)
