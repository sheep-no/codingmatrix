"""get_apikey_manager 默认连接必须遵循 REDIS_URL 配置。

生产环境 Redis 位于独立容器，未显式注入 client 时若硬编码 localhost，
所有 Key 读写都会连接失败。
"""

import app.services.apikey_manager as ak_module
from app.core.config import settings


class _FakeRedis:
    pass


def test_default_client_uses_configured_redis_url(monkeypatch):
    monkeypatch.setattr(ak_module, "_apikey_manager", None)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://redis:6379/0")
    captured = {}

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        return _FakeRedis()

    monkeypatch.setattr(ak_module.redis, "from_url", fake_from_url)

    manager = ak_module.get_apikey_manager()

    assert captured["url"] == "redis://redis:6379/0"
    assert isinstance(manager.redis, _FakeRedis)


def test_default_client_falls_back_to_localhost(monkeypatch):
    monkeypatch.setattr(ak_module, "_apikey_manager", None)
    monkeypatch.setattr(settings, "REDIS_URL", "")
    captured = {}

    def fake_redis(**kwargs):
        captured.update(kwargs)
        return _FakeRedis()

    monkeypatch.setattr(ak_module.redis, "Redis", fake_redis)

    ak_module.get_apikey_manager()

    assert captured["host"] == "localhost"
    assert captured["port"] == 6379
