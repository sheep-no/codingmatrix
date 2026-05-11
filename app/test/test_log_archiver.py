"""
日志归档模块测试
"""
import gzip
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
import pytest


class TestLogArchiver:
    """日志归档器测试"""

    @pytest.fixture
    def temp_log_dir(self):
        """创建临时日志目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def archiver(self, temp_log_dir):
        """创建日志归档器实例"""
        from app.utils.log_archiver import LogArchiver
        return LogArchiver(
            log_dir=str(temp_log_dir),
            max_size_mb=0.001,
            retention_days=1,
            compression_enabled=True
        )

    def test_create_archiver(self, temp_log_dir):
        """测试创建归档器"""
        from app.utils.log_archiver import LogArchiver
        archiver = LogArchiver(log_dir=str(temp_log_dir))
        assert archiver.log_dir == temp_log_dir
        assert archiver.max_size_bytes == 100 * 1024 * 1024
        assert archiver.retention_days == 7

    def test_get_log_files_empty(self, archiver):
        """测试空目录返回空列表"""
        files = archiver.get_log_files()
        assert files == []

    def test_get_log_files_with_files(self, archiver, temp_log_dir):
        """测试获取日志文件"""
        (temp_log_dir / "app.log").touch()
        (temp_log_dir / "error.log").touch()
        files = archiver.get_log_files()
        assert len(files) == 2

    def test_should_rotate_by_size_false_for_small_file(self, archiver, temp_log_dir):
        """测试小文件不需要轮转"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("small content")
        assert archiver.should_rotate_by_size(test_file) == False

    def test_should_rotate_by_size_true_for_large_file(self, archiver, temp_log_dir):
        """测试大文件需要轮转"""
        test_file = temp_log_dir / "test.log"
        test_file.write_bytes(b"x" * (archiver.max_size_bytes + 1))
        assert archiver.should_rotate_by_size(test_file) == True

    def test_rotate_file_creates_archive(self, archiver, temp_log_dir):
        """测试轮转文件创建归档"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("test content")
        result = archiver.rotate_file(test_file)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".gz"
        assert not test_file.exists()

    def test_rotate_file_compresses_content(self, archiver, temp_log_dir):
        """测试轮转时压缩内容"""
        content = "test content " * 100
        test_file = temp_log_dir / "test.log"
        test_file.write_text(content)

        result = archiver.rotate_file(test_file)
        assert result is not None

        with gzip.open(result, 'rt') as f:
            assert f.read() == content

    def test_cleanup_old_logs(self, archiver, temp_log_dir):
        """测试清理过期日志"""
        old_file = temp_log_dir / "old.log.gz"
        old_file.write_text("old content")

        old_time = time.time() - (archiver.retention_days + 1) * 86400
        os.utime(old_file, (old_time, old_time))

        cleaned = archiver.cleanup_old_logs()
        assert len(cleaned) == 1
        assert not old_file.exists()

    def test_cleanup_preserves_recent_logs(self, archiver, temp_log_dir):
        """测试清理保留近期日志"""
        recent_file = temp_log_dir / "recent.log.gz"
        recent_file.write_text("recent content")

        recent_time = time.time() - (archiver.retention_days - 1) * 86400
        os.utime(recent_file, (recent_time, recent_time))

        cleaned = archiver.cleanup_old_logs()
        assert len(cleaned) == 0
        assert recent_file.exists()

    def test_archive_stats(self, archiver, temp_log_dir):
        """测试获取归档统计"""
        content = "x" * 10000
        test_file = temp_log_dir / "test.log.gz"
        with gzip.open(test_file, 'wb') as f:
            f.write(content.encode())
        stats = archiver.get_archive_stats()
        assert stats["file_count"] == 1
        assert stats["total_size_bytes"] > 50
        assert stats["total_size_mb"] >= 0

    def test_get_log_archiver_singleton(self):
        """测试单例模式"""
        from app.utils.log_archiver import get_log_archiver
        archiver1 = get_log_archiver()
        archiver2 = get_log_archiver()
        assert archiver1 is archiver2

    @pytest.mark.asyncio
    async def test_run_archive_task(self):
        """测试归档任务"""
        from app.utils.log_archiver import run_archive_task
        result = await run_archive_task()
        assert "rotated" in result
        assert "cleaned" in result
        assert "errors" in result


class TestLogRotationHandler:
    """日志轮转处理器测试"""

    def test_create_handler(self, tmp_path):
        """测试创建处理器"""
        from app.utils.log_archiver import LogRotationHandler
        log_file = tmp_path / "test.log"
        handler = LogRotationHandler(str(log_file), max_bytes=1000)
        assert handler.log_file == log_file
        assert handler.max_bytes == 1000
