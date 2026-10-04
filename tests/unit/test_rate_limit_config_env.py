"""RateLimitConfig 环境变量覆盖回归测试。

E2E（CI）在同一分钟窗口内密集登录 /api/v1/login，耗尽默认 5次/60秒
配额并误伤 encrypted-login 用例；CI 通过 RATE_LIMIT_LOGIN_LIMIT 放宽。
"""

import importlib

from app.services import rate_limit_config as rlc_module


def _fresh_config(monkeypatch, value):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_LIMIT", value)
    importlib.reload(rlc_module)
    return rlc_module.RateLimitConfig()


def test_login_limit_env_override(monkeypatch):
    config = _fresh_config(monkeypatch, "1000")

    limit, window = config.get_endpoint_rule("/api/v1/login")

    assert limit == 1000
    assert window == 60


def test_default_login_limit_unchanged(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_LOGIN_LIMIT", raising=False)
    importlib.reload(rlc_module)
    config = rlc_module.RateLimitConfig()

    limit, window = config.get_endpoint_rule("/api/v1/login")

    assert (limit, window) == (5, 60)


def test_invalid_env_value_falls_back_to_default(monkeypatch):
    config = _fresh_config(monkeypatch, "not-a-number")

    limit, window = config.get_endpoint_rule("/api/v1/login")

    assert (limit, window) == (5, 60)


def test_singleton_reload_keeps_module_api(monkeypatch):
    config = _fresh_config(monkeypatch, "500")

    assert rlc_module.rate_limit_config is not None
    assert isinstance(config, rlc_module.RateLimitConfig)
