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
