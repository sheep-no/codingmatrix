"""Prometheus alert rules must stay wired to the exported empty stream metric."""

from pathlib import Path

import yaml

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def _load(name):
    return yaml.safe_load((CONFIGS / name).read_text(encoding="utf-8"))


def test_prometheus_loads_alert_rules():
    config = _load("prometheus.yml")

    assert config["rule_files"] == ["alert_rules.yml"]
    assert (CONFIGS / "alert_rules.yml").is_file()
    assert config["scrape_configs"][0]["authorization"]["credentials_file"] == (
        "/etc/monitoring/metrics_token"
    )
    targets = config["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert targets == ["localhost:9093"]


def test_empty_stream_alerts_use_exported_metric():
    rules = _load("alert_rules.yml")["groups"][0]["rules"]
    by_name = {rule["alert"]: rule for rule in rules}

    for name in ("LlmEmptyStreamSpike", "LlmEmptyStreamProviderSustained"):
        rule = by_name[name]
        assert "llm_empty_streams_total" in rule["expr"]
        assert rule["labels"]["severity"] in {"warning", "critical"}
        assert rule["annotations"]["description"]

    assert "sum by (provider, model)" in by_name["LlmEmptyStreamSpike"]["expr"]
    assert "sum by (provider)" in by_name["LlmEmptyStreamProviderSustained"]["expr"]


def test_compose_prometheus_scrapes_with_token_and_routes_alerts():
    config = _load("prometheus.compose.yml")

    job = config["scrape_configs"][0]
    assert job["static_configs"][0]["targets"] == ["api:8080"]
    assert job["metrics_path"] == "/api/v1/health/metrics"
    assert job["authorization"]["credentials_file"] == "/etc/monitoring/metrics_token"

    targets = config["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert targets == ["alertmanager:9093"]
    assert config["rule_files"] == ["/etc/prometheus/alert_rules.yml"]


def test_alertmanager_delivers_to_authenticated_api_webhook():
    config = _load("alertmanager.yml")

    route = config["route"]
    assert route["receiver"] == "api-webhook"
    receiver = next(item for item in config["receivers"] if item["name"] == "api-webhook")
    webhook = receiver["webhook_configs"][0]
    assert webhook["url"] == "http://api:8080/api/v1/health/alerts"
    assert webhook["http_config"]["authorization"]["credentials_file"] == (
        "/etc/monitoring/metrics_token"
    )
    # 配置文件只引用挂载的令牌文件，不落任何明文令牌
    assert "credentials" not in webhook["http_config"]["authorization"]
