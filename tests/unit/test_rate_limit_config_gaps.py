"""rate_limit_config setter/remove 分支补测。"""

from app.services.rate_limit_config import RateLimitConfig


def test_setters_update_limits():
    config = RateLimitConfig()

    config.set_global_limit(10, 30)
    config.set_ip_limit(5, 20)
    config.set_user_limit(3, 10)

    assert config.global_limit == (10, 30)
    assert config.ip_limit == (5, 20)
    assert config.user_limit == (3, 10)


def test_endpoint_rule_add_and_remove():
    config = RateLimitConfig()

    config.set_endpoint_rule("/api/v1/custom", 7, 15)
    assert config.get_endpoint_rule("/api/v1/custom/sub") == (7, 15)

    config.remove_endpoint_rule("/api/v1/custom")
    assert config.get_endpoint_rule("/api/v1/custom/sub") == (60, 60)


def test_remove_unknown_endpoint_is_noop():
    config = RateLimitConfig()
    config.remove_endpoint_rule("/not/there")
    assert config.get_endpoint_rule("/not/there") == (60, 60)


def test_set_enabled_toggles():
    config = RateLimitConfig()
    config.set_enabled(False)
    assert config.enabled is False
    config.set_enabled(True)
    assert config.enabled is True


def test_default_endpoint_rule_for_unknown_path():
    assert RateLimitConfig().get_endpoint_rule("/unknown") == (60, 60)


def test_longest_prefix_wins():
    config = RateLimitConfig()
    config.set_endpoint_rule("/api/v1", 1, 60)
    config.set_endpoint_rule("/api/v1/code", 2, 60)

    assert config.get_endpoint_rule("/api/v1/code/x") == (2, 60)


def test_environment_override_for_login(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_LIMIT", "42")
    config = RateLimitConfig()
    assert config.get_endpoint_rule("/api/v1/login") == (42, 60)


def test_invalid_environment_override_ignored(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_LIMIT", "not-a-number")
    config = RateLimitConfig()
    assert config.get_endpoint_rule("/api/v1/login") == (5, 60)


def test_max_window_uses_largest_rule():
    config = RateLimitConfig()
    config.set_endpoint_rule("/api/v1/slow", 1, 900)
    assert config.max_window == 900


def test_singleton_accessor():
    from app.services import rate_limit_config as module

    module._rate_limit_config_instance = None
    first = module.get_rate_limit_config()
    second = module.get_rate_limit_config()
    assert first is second


def test_to_dict_snapshot():
    config = RateLimitConfig()
    payload = config.to_dict()
    assert payload["enabled"] is True
    assert payload["global"] == {"limit": 1000, "window": 60}
    assert payload["endpoints"]["/api/v1/login"]["limit"] == 5
