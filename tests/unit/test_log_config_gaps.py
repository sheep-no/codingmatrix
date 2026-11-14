"""log_config 动态级别、文件 handler 摘挂与异常分支补测。"""

import logging

from app.services import log_config as module
from app.services.log_config import LogConfigService, LogLevel


def _fresh():
    service = LogConfigService()
    service._current_level = {}
    service._log_to_file = True
    service._detached_file_handlers = []
    return service


def test_from_string_invalid_falls_back_to_info():
    assert LogLevel.from_string("bogus") is LogLevel.INFO
    assert LogLevel.from_string("debug") is LogLevel.DEBUG


def test_set_log_level_success_and_unknown_logger():
    service = _fresh()

    assert service.set_log_level("app.test", "warning") is True
    assert service.get_log_level("app.test") == "WARNING"
    assert service.get_log_level("unset") == "INFO"
    assert service.get_all_levels() == {"app.test": "WARNING"}


def test_set_log_level_failure_returns_false(monkeypatch):
    service = _fresh()

    def boom(value):
        raise RuntimeError("locked")

    monkeypatch.setattr(module.LogLevel, "from_string", boom)

    assert service.set_log_level("app", "INFO") is False


def test_set_global_level_success():
    service = _fresh()

    assert service.set_global_level("error") is True
    assert service._current_level[""] == "ERROR"
    assert logging.root.level == logging.ERROR


def test_set_global_level_failure(monkeypatch):
    service = _fresh()

    def boom(level):
        raise OSError("locked")

    monkeypatch.setattr(module.logging.root, "setLevel", boom)

    assert service.set_global_level("INFO") is False


def test_file_logging_toggle_detaches_and_restores(tmp_path):
    service = _fresh()
    logger = logging.getLogger("gap.log_config")
    handler = logging.FileHandler(tmp_path / "gap.log")
    logger.addHandler(handler)
    try:
        assert service.set_file_logging(False) is True
        assert handler not in logger.handlers
        assert service.is_file_logging_enabled() is False

        assert service.set_file_logging(True) is True
        assert handler in logger.handlers
        assert service.is_file_logging_enabled() is True
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_file_logging_toggle_failure(monkeypatch):
    service = _fresh()

    class BadLogger:
        def removeHandler(self, handler):
            raise RuntimeError("locked")

    monkeypatch.setattr(service, "_iter_file_handlers", lambda: iter([(BadLogger(), object())]))

    assert service.set_file_logging(False) is False


def test_get_config_shape():
    service = _fresh()

    assert service.get_config() == {
        "log_level": "INFO",
        "global_level": "INFO",
        "log_to_file": True,
        "log_to_console": True,
    }


def test_singleton_reinitialization_is_noop():
    first = LogConfigService()
    second = LogConfigService()
    assert first is second
