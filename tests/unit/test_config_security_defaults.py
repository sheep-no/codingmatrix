"""覆盖 config.py 的安全默认值派生（CFG1 / CFG4）。

CFG1：SECRET_KEY 的生产校验原先读 `os.getenv("ENV")`，与 pydantic 从 `.env`
解析的 ENV 双轨——仅写 `.env` 不导出环境变量的部署会绕过生产校验，静默落到
固定开发密钥（多 worker 各自实例 → JWT 跨 worker 验签失败）。

CFG4：ALLOWED_HOSTS 原被 `replace(",", "|")` 直接当作 CORS origin 正则，
未锚定、未转义，`re.search` 让 `https://localhost.evil.com` 这类子串也放行。
"""

import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("ENV", "SECRET_KEY", "ALLOWED_HOSTS"):
        monkeypatch.delenv(name, raising=False)


def _settings(**kwargs) -> Settings:
    # 禁用 .env，确保断言只受显式传参影响
    return Settings(_env_file=None, **kwargs)


def test_production_without_secret_key_rejected():
    """ENV=production（来自 .env 或传参）且未设 SECRET_KEY 必须报错。"""
    with pytest.raises(ValidationError):
        _settings(ENV="production", SECRET_KEY="")


def test_development_without_secret_key_uses_stable_dev_key():
    settings = _settings(ENV="development", SECRET_KEY="")
    assert settings.SECRET_KEY == "development-only-secret-key-change-me"


def test_short_secret_key_rejected():
    with pytest.raises(ValidationError):
        _settings(ENV="production", SECRET_KEY="short")


def test_production_with_secret_key_accepted():
    key = "x" * 32
    settings = _settings(ENV="production", SECRET_KEY=key)
    assert settings.SECRET_KEY == key


@pytest.mark.parametrize(
    "origin",
    (
        "http://localhost:3000",
        "https://127.0.0.1:5173",
        "http://localhost",
        "http://0.0.0.0:8000",
    ),
)
def test_cors_origin_regex_allows_listed_hosts(origin):
    pattern = _settings(ALLOWED_HOSTS="localhost,127.0.0.1,0.0.0.0").cors_origin_regex
    assert re.search(pattern, origin)


@pytest.mark.parametrize(
    "origin",
    (
        "https://localhost.evil.com",
        "https://evil.com",
        "http://notlocalhost",
        "https://127x0x0x1.com",
        "https://localhost:3000/path",
    ),
)
def test_cors_origin_regex_rejects_substring_and_unescaped(origin):
    pattern = _settings(ALLOWED_HOSTS="localhost,127.0.0.1,0.0.0.0").cors_origin_regex
    assert not re.search(pattern, origin)


def test_cors_origin_regex_escapes_domain_hosts():
    pattern = _settings(ALLOWED_HOSTS="your-domain.com,api.your-domain.com").cors_origin_regex
    assert re.search(pattern, "https://api.your-domain.com")
    assert re.search(pattern, "http://your-domain.com:8080")
    assert not re.search(pattern, "https://your-domainXcom")
    assert not re.search(pattern, "https://evil-your-domain.com")


def test_cors_origin_regex_none_when_hosts_empty():
    assert _settings(ALLOWED_HOSTS="").cors_origin_regex is None


def test_provider_registry_is_reused_within_process():
    """CFG5：注册表只依赖静态配置，同一进程内应复用而非每次重建。"""
    settings = get_settings()
    assert settings.get_provider_registry() is settings.get_provider_registry()


def test_settings_exposes_no_unwired_allowed_models_field():
    """CFG2：ALLOWED_MODELS 为死配置，已移除；生效白名单唯一来源为 MODEL_REGISTRY。"""
    assert not hasattr(get_settings(), "ALLOWED_MODELS")


def test_settings_exposes_no_unwired_allowed_file_types_field():
    """CFG3：ALLOWED_FILE_TYPES 零消费（上传实际用 file_upload.ALLOWED_EXTENSIONS），已移除。"""
    assert not hasattr(get_settings(), "ALLOWED_FILE_TYPES")


def test_metrics_token_is_optional_but_never_short():
    """监控令牌留空表示仅允许 JWT；一旦配置必须足够长以抵抗猜测。"""
    assert _settings(METRICS_TOKEN="").METRICS_TOKEN == ""
    assert _settings(METRICS_TOKEN="m" * 16).METRICS_TOKEN == "m" * 16
    with pytest.raises(ValidationError):
        _settings(METRICS_TOKEN="short")


def test_alert_notifier_defaults_are_disabled():
    """未配置通知渠道时保持静默，避免默认向外部发送告警。"""
    settings = _settings()

    assert settings.ALERT_WEBHOOK_URL == ""
    assert settings.ALERT_SMTP_HOST == ""
    assert settings.ALERT_NOTIFY_MIN_SEVERITY == "warning"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ALERT_WEBHOOK_URL", "ftp://example.com/hook"),
        ("ALERT_WEBHOOK_TYPE", "telegram"),
        ("ALERT_NOTIFY_MIN_SEVERITY", "debug"),
        ("ALERT_SMTP_SECURITY", "plain"),
    ),
)
def test_alert_notifier_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _settings(**{field: value})


@pytest.mark.parametrize("port", (0, 65536))
def test_alert_smtp_port_bounds(port):
    with pytest.raises(ValidationError):
        _settings(ALERT_SMTP_PORT=port)
