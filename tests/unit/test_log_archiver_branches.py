"""Branch coverage for app/utils/log_archiver.py."""

import gzip
import os
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.utils import log_archiver as module
from app.utils.log_archiver import LogArchiver


def _archiver(tmp_path: Path, **kwargs) -> LogArchiver:
    defaults = {
        "log_dir": str(tmp_path),
        "max_size_mb": 0.001,
        "retention_days": 7,
    }
    defaults.update(kwargs)
    return LogArchiver(**defaults)


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# discovery / size checks
# ---------------------------------------------------------------------------


def test_get_log_files_missing_dir_returns_empty(tmp_path) -> None:
    archiver = LogArchiver(log_dir=str(tmp_path / "missing"))

    assert archiver.get_log_files() == []


def test_get_log_files_sorted_by_mtime(tmp_path) -> None:
    first = _write(tmp_path / "a.log")
    second = _write(tmp_path / "b.log")
    os.utime(first, (100, 100))
    os.utime(second, (200, 200))

    assert [p.name for p in LogArchiver(str(tmp_path)).get_log_files()] == [
        "a.log",
        "b.log",
    ]


def test_should_rotate_missing_file_returns_false(tmp_path) -> None:
    assert LogArchiver(str(tmp_path)).should_rotate_by_size(tmp_path / "none.log") is False


def test_should_rotate_by_size_boundary(tmp_path) -> None:
    archiver = _archiver(tmp_path)
    path = _write(tmp_path / "app.log", b"x" * 2048)

    assert archiver.should_rotate_by_size(path) is True


def test_rotate_missing_file_returns_none(tmp_path) -> None:
    assert LogArchiver(str(tmp_path)).rotate_file(tmp_path / "none.log") is None


# ---------------------------------------------------------------------------
# rotation formats
# ---------------------------------------------------------------------------


def test_rotate_uncompressed_moves_file(tmp_path) -> None:
    archiver = _archiver(tmp_path, compression_enabled=False)
    path = _write(tmp_path / "app.log", b"body")

    archived = archiver.rotate_file(path)

    assert archived is not None
    assert archived.suffix == ".log"
    assert archived.read_bytes() == b"body"
    assert not path.exists()


def test_rotate_zip_format_creates_archive(tmp_path) -> None:
    archiver = _archiver(tmp_path, archive_format="zip")
    path = _write(tmp_path / "app.log", b"zipbody")

    archived = archiver.rotate_file(path)

    assert archived is not None
    assert archived.suffix == ".zip"
    with zipfile.ZipFile(archived) as zf:
        assert zf.read("app.log") == b"zipbody"
    assert not path.exists()


def test_rotate_failure_cleans_partial_archive(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    path = _write(tmp_path / "app.log", b"body")
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    def boom(*args, **kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(module.shutil, "copyfileobj", boom)

    assert archiver.rotate_file(path) is None
    assert path.exists()
    assert not list(tmp_path.glob("*.gz"))
    assert errors


def test_rotate_failure_without_partial_file(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    path = _write(tmp_path / "app.log", b"body")
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    def boom(*args, **kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(module.shutil, "copyfileobj", boom)
    real_exists = Path.exists

    def fake_exists(self):
        if self.name.endswith(".gz"):
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    assert archiver.rotate_file(path) is None
    assert errors


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def _age(path: Path, days: int) -> None:
    ts = time.time() - days * 86400
    os.utime(path, (ts, ts))


def test_cleanup_dry_run_keeps_old_files(tmp_path) -> None:
    archiver = _archiver(tmp_path)
    old = _write(tmp_path / "old.log.gz")
    _age(old, 30)

    cleaned = archiver.cleanup_old_logs(dry_run=True)

    assert cleaned == [old]
    assert old.exists()


def test_cleanup_deletes_old_files_and_skips_fresh(tmp_path) -> None:
    archiver = _archiver(tmp_path)
    old = _write(tmp_path / "old.log.gz")
    fresh = _write(tmp_path / "fresh.log.gz")
    _age(old, 30)

    cleaned = archiver.cleanup_old_logs()

    assert cleaned == [old]
    assert not old.exists()
    assert fresh.exists()


def test_cleanup_without_compression_matches_any_archive(tmp_path) -> None:
    archiver = _archiver(tmp_path, compression_enabled=False)
    old = _write(tmp_path / "old.log.1")
    _age(old, 30)

    assert archiver.cleanup_old_logs() == [old]
    assert not old.exists()


def test_cleanup_logs_error_on_unlink_failure(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    old = _write(tmp_path / "old.log.gz")
    _age(old, 30)
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    def boom(self):
        raise OSError("locked")

    monkeypatch.setattr(Path, "unlink", boom)

    assert archiver.cleanup_old_logs() == []
    assert errors


# ---------------------------------------------------------------------------
# archive_all
# ---------------------------------------------------------------------------


def test_archive_lock_without_fcntl_yields_directly(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    monkeypatch.setattr(module, "fcntl", None)
    entered = []

    with archiver._archive_lock():
        entered.append(True)

    assert entered == [True]


def test_archive_all_rotates_archives_and_cleans(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    _write(tmp_path / "big.log", b"x" * 4096)
    _write(tmp_path / "old.log.1", b"y" * 4096)
    stale = _write(tmp_path / "stale.log.gz", b"z")
    _age(stale, 30)

    stats = archiver.archive_all()

    assert len(stats["rotated"]) == 1
    assert len(stats["archived"]) == 1
    assert stats["cleaned"] == [str(stale)]
    assert not stats["errors"]


def test_archive_all_skips_archive_extension(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    _write(tmp_path / "already.log.gz", b"z")
    rotated = []
    monkeypatch.setattr(
        archiver,
        "rotate_file",
        lambda path: rotated.append(path) or None,
    )

    stats = archiver.archive_all()

    assert all(not str(path).endswith(".gz") for path in rotated)
    assert stats["archived"] == []


def test_archive_all_records_rotation_errors(tmp_path, monkeypatch) -> None:
    archiver = _archiver(tmp_path)
    _write(tmp_path / "big.log", b"x" * 4096)
    _write(tmp_path / "old.log.1", b"y" * 4096)

    def boom(path):
        raise OSError("rotate failed")

    monkeypatch.setattr(archiver, "rotate_file", boom)

    stats = archiver.archive_all()

    assert set(stats["errors"]) == {"big.log", "old.log.1"}


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_get_archive_stats_empty(tmp_path) -> None:
    stats = LogArchiver(str(tmp_path)).get_archive_stats()

    assert stats["file_count"] == 0
    assert stats["oldest_file"] is None
    assert stats["newest_file"] is None


def test_get_archive_stats_reports_oldest_and_newest(tmp_path) -> None:
    older = _write(tmp_path / "older.log.gz", b"aa")
    newer = _write(tmp_path / "newer.log.gz", b"bbbb")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    stats = LogArchiver(str(tmp_path)).get_archive_stats()

    assert stats["file_count"] == 2
    assert stats["total_size_bytes"] == 6
    assert stats["oldest_file"] == "older.log.gz"
    assert stats["newest_file"] == "newer.log.gz"


def test_get_archive_stats_without_compression_uses_generic_pattern(tmp_path) -> None:
    _write(tmp_path / "a.log.1", b"a")

    stats = LogArchiver(str(tmp_path), compression_enabled=False).get_archive_stats()

    assert stats["file_count"] == 1


# ---------------------------------------------------------------------------
# singleton / task
# ---------------------------------------------------------------------------


def test_get_log_archiver_builds_once(monkeypatch) -> None:
    monkeypatch.setattr(module, "_log_archiver", None)
    built = []

    class Fake(LogArchiver):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            built.append(self)

    monkeypatch.setattr(module, "LogArchiver", Fake)

    first = module.get_log_archiver()
    second = module.get_log_archiver()

    assert first is second
    assert len(built) == 1


def test_build_log_archiver_reads_settings(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.core import config

    fake_settings = SimpleNamespace(
        LOG_DIR="/tmp/logs", LOG_RETENTION_DAYS=5, LOG_COMPRESS_OLD_LOGS=False
    )
    monkeypatch.setattr(config, "settings", fake_settings)

    archiver = module._build_log_archiver()

    assert str(archiver.log_dir) == "/tmp/logs"
    assert archiver.retention_days == 5
    assert archiver.compression_enabled is False


def test_build_log_archiver_defaults_dir_when_missing(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.core import config

    fake_settings = SimpleNamespace(LOG_RETENTION_DAYS=5, LOG_COMPRESS_OLD_LOGS=True)
    monkeypatch.setattr(config, "settings", fake_settings)

    archiver = module._build_log_archiver()

    assert str(archiver.log_dir) == "logs"


@pytest.mark.asyncio
async def test_run_archive_task_returns_stats(monkeypatch) -> None:
    stats = {"rotated": ["a"], "cleaned": ["b"]}

    class Fake:
        def archive_all(self):
            return stats

    monkeypatch.setattr(module, "get_log_archiver", lambda: Fake())
    logs = []
    monkeypatch.setattr(
        module.logger, "info", lambda *args, **kwargs: logs.append(args)
    )

    assert await module.run_archive_task() == stats
    assert logs


@pytest.mark.asyncio
async def test_run_archive_task_returns_error(monkeypatch) -> None:
    class Fake:
        def archive_all(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "get_log_archiver", lambda: Fake())
    monkeypatch.setattr(module.logger, "error", lambda *args, **kwargs: None)

    assert await module.run_archive_task() == {"error": "boom"}
