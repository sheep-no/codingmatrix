"""日志归档器回归测试。

覆盖 docs/evolution/modules/utility_tools.md 中核实的缺陷：
- LA2：多 worker 并发归档无文件锁，同一文件被双进程轮转会丢归档
- LA1：get_log_archiver 单例无锁
"""
import gzip
import threading
import time
from pathlib import Path

import app.utils.log_archiver as log_archiver_module
from app.utils.log_archiver import LogArchiver, get_log_archiver


def _make_archiver(log_dir: Path) -> LogArchiver:
    # max_size_bytes 取极小值，便于用普通大小的文件触发轮转
    return LogArchiver(log_dir=str(log_dir), max_size_mb=0.001, retention_days=7)


def _oversized_log(log_dir: Path, size: int = 4096) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "app.log"
    path.write_bytes(b"x" * size)
    return path


class TestArchiveLock:
    """LA2：归档操作应跨进程互斥"""

    def test_archive_lock_excludes_concurrent_archive(self, tmp_path):
        archiver = _make_archiver(tmp_path)
        _oversized_log(tmp_path)

        finished = threading.Event()
        thread = threading.Thread(
            target=lambda: (archiver.archive_all(), finished.set())
        )

        with archiver._archive_lock():
            thread.start()
            time.sleep(0.3)
            assert not finished.is_set(), "归档锁未阻止并发归档"

        thread.join(timeout=10)
        assert finished.is_set()

    def test_concurrent_archive_keeps_single_archive(self, tmp_path):
        archiver = _make_archiver(tmp_path)
        _oversized_log(tmp_path)

        errors = []

        def _run():
            try:
                archiver.archive_all()
            except Exception as exc:  # pragma: no cover - 失败即测试断言
                errors.append(exc)

        threads = [threading.Thread(target=_run) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors
        archives = list(tmp_path.glob("*.log.gz"))
        assert len(archives) == 1, archives
        assert not (tmp_path / "app.log").exists()
        with gzip.open(archives[0], "rb") as f:
            assert f.read() == b"x" * 4096


class TestArchiveAll:
    """归档主流程"""

    def test_oversized_log_is_rotated_and_compressed(self, tmp_path):
        archiver = _make_archiver(tmp_path)
        _oversized_log(tmp_path)

        stats = archiver.archive_all()

        assert len(stats["rotated"]) == 1
        assert not stats["errors"]
        assert not (tmp_path / "app.log").exists()
        assert len(list(tmp_path.glob("app_*.log.gz"))) == 1

    def test_small_log_is_left_untouched(self, tmp_path):
        archiver = _make_archiver(tmp_path)
        path = tmp_path / "small.log"
        path.write_bytes(b"tiny")

        stats = archiver.archive_all()

        assert stats["rotated"] == []


class TestSingleton:
    """LA1：单例获取"""

    def test_singleton_returns_same_instance(self, monkeypatch):
        monkeypatch.setattr(log_archiver_module, "_log_archiver", None)
        assert get_log_archiver() is get_log_archiver()
