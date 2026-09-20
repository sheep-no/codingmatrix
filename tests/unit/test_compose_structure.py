"""docker-compose 配置结构回归。

container_runtime.md CR5：基础 Compose 曾把 jaeger 服务错误缩进到
networks 之下，导致它既不是服务，也让 networks 携带非法属性。
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / name).read_text(encoding="utf-8"))


def test_jaeger_is_a_service_not_a_network_entry():
    compose = _load("docker-compose.yml")

    assert "jaeger" in compose["services"]
    assert set(compose["networks"]) == {"ai-agent-net"}


def test_jaeger_stays_optional_via_profile():
    compose = _load("docker-compose.yml")

    assert compose["services"]["jaeger"]["profiles"] == ["observability"]
    # 默认启动集不应包含可选观测服务
    default_services = {
        name
        for name, service in compose["services"].items()
        if not service.get("profiles")
    }
    assert "jaeger" not in default_services


def test_prod_compose_service_and_network_names_are_consistent():
    compose = _load("docker-compose.prod.yml")

    assert {"api", "celery", "nginx", "redis", "scheduler"} <= set(compose["services"])
    assert set(compose["networks"]) == {"ai-agent-prod-net"}
