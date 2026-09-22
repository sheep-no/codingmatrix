"""日志子系统配置接线回归测试。

覆盖 docs/evolution/modules/core_layer.md 的 CFG3 剩余三项、FV6、LGC4
与 docs/evolution/modules/services.md 的 LC1：
- LOG_RETENTION_DAYS / LOG_COMPRESS_OLD_LOGS 接线到 LogArchiver
- LOG_CLEANUP_SCHEDULE 接线到调度间隔
- LogConfigService.set_file_logging 真实摘挂文件 handler（LC1）
- CompressedRotatingFileHandler 死类已删除（FV6）
"""

import importlib
import logging
from datetime import timedelta

import pytest

from app.core.config import settings
import app.utils.log_archiver as log_archiver_module
from app.services.log_config import log_config_service


@pytest.fixture
def restore_settings():
    original = (
        settings.LOG_RETENTION_DAYS,
        settings.LOG_COMPRESS_OLD_LOGS,
        settings.LOG_CLEANUP_SCHEDULE,
    )
    yield
    (
        settings.LOG_RETENTION_DAYS,
        settings.LOG_COMPRESS_OLD_LOGS,
        settings.LOG_CLEANUP_SCHEDULE,
    ) = original


@pytest.fixture
def restore_file_logging():
    yield
    # 用例结束后恢复文件日志，避免摘下的 handler 污染其他测试
    log_config_service.set_file_logging(True)


class TestArchiverConfigWiring:
    def test_archiver_reads_retention_and_compression(
        self, monkeypatch, restore_settings
    ):
        monkeypatch.setattr(settings, "LOG_RETENTION_DAYS", 5)
        monkeypatch.setattr(settings, "LOG_COMPRESS_OLD_LOGS", False)
        monkeypatch.setattr(log_archiver_module, "_log_archiver", None)

        archiver = log_archiver_module.get_log_archiver()

        assert archiver.retention_days == 5
        assert archiver.compression_enabled is False


class TestCleanupScheduleWiring:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("daily", 1),
            ("weekly", 7),
            ("monthly", 30),
            (" Weekly ", 7),
            ("bogus", 7),
        ],
    )
    def test_schedule_mapping(self, monkeypatch, restore_settings, value, expected):
        scheduler = importlib.import_module("app.db.scheduler")
        monkeypatch.setattr(settings, "LOG_CLEANUP_SCHEDULE", value)
        assert scheduler._log_cleanup_interval_days() == expected

    def test_registered_job_uses_default_weekly_interval(self):
        scheduler = importlib.import_module("app.db.scheduler")
        jobs = {entry[0].id: entry[0] for entry in scheduler.scheduler._pending_jobs}
        assert jobs["log_cleanup"].trigger.interval == timedelta(days=7)


class TestFileLoggingToggle:
    def test_toggle_detaches_and_reattaches_file_handlers(
        self, tmp_path, restore_file_logging
    ):
        logger = logging.getLogger("probe_file_logging_toggle")
        handler = logging.FileHandler(tmp_path / "probe.log")
        logger.addHandler(handler)
        try:
            assert log_config_service.set_file_logging(False) is True
            assert log_config_service.is_file_logging_enabled() is False
            assert handler not in logger.handlers

            assert log_config_service.set_file_logging(True) is True
            assert log_config_service.is_file_logging_enabled() is True
            assert handler in logger.handlers
        finally:
            logger.removeHandler(handler)
            handler.close()


class TestDeadClassRemoved:
    def test_compressed_rotating_handler_removed(self):
        from app.core import logging_config

        assert not hasattr(logging_config, "CompressedRotatingFileHandler")
