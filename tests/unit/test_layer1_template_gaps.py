"""layer1 领域模板加载、分类映射与去重补测。"""

import json
import logging
from pathlib import Path

import pytest

from app.agent.orchestrator_requirements import layer1_template as module
from app.agent.orchestrator_requirements.layer1_template import (
    _load_domain_template,
    compute_template_confidence,
    layer1_cross_domain_template,
)


def _write(tmp_path, name, payload):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


async def test_no_domains_returns_empty():
    assert await layer1_cross_domain_template("anything", []) == []


async def test_missing_template_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "DOMAIN_TEMPLATES_DIR", tmp_path)
    assert await layer1_cross_domain_template("req", ["missing"]) == []


async def test_invalid_json_returns_none(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    module.logger.addHandler(handler)
    try:
        assert _load_domain_template(path) is None
    finally:
        module.logger.removeHandler(handler)
    assert any("领域模板加载失败" in r.getMessage() for r in records)


async def test_all_template_sections_mapped(monkeypatch, tmp_path):
    payload = {
        "domain": "banking",
        "core_modules": [
            {"name": "账户模块", "category": "core", "impact": "high"},
            {"name": "转账模块"},
        ],
        "non_functional_requirements": [
            {"item": "高可用", "category": "reliability", "priority": "high"},
            {"item": "审计"},
        ],
        "common_pitfalls": ["并发转账超卖"],
        "key_decisions": [
            {"question": "选型数据库", "impact": "architecture"},
            {"question": "消息队列"},
        ],
    }
    _write(tmp_path, "banking", payload)
    monkeypatch.setattr(module, "DOMAIN_TEMPLATES_DIR", tmp_path)

    items = await layer1_cross_domain_template("银行转账系统", ["banking"])

    assert [i.category for i in items] == [
        "functional", "functional",
        "architectural", "architectural",
        "risk",
        "decision", "decision",
    ]
    first = items[0]
    assert first.content == "账户模块"
    assert first.sub_category == "core"
    assert first.impact == "high"
    assert first.source == "domain_template:banking"
    assert items[1].sub_category == "core"

    assert items[2].sub_category == "reliability"
    assert items[2].impact == "high"
    assert items[3].sub_category == ""

    assert items[4].content == "并发转账超卖"
    assert items[4].sub_category == "common_pitfall"

    assert items[5].sub_category == "architecture"
    assert items[6].sub_category == "architecture"

    # 非功能需求与风险项在基础置信度上打折
    assert items[2].confidence < first.confidence
    assert items[4].confidence < first.confidence
    assert items[5].confidence < first.confidence


async def test_dedup_keeps_higher_confidence(monkeypatch, tmp_path):
    higher = {
        "domain": "banking",
        "core_modules": [{"name": "账户", "category": "core"}],
    }
    lower = {
        "domain": "unknown",
        "core_modules": [{"name": "账户", "category": "core"}],
    }
    _write(tmp_path, "banking", higher)
    _write(tmp_path, "unknown", lower)
    monkeypatch.setattr(module, "DOMAIN_TEMPLATES_DIR", tmp_path)

    items = await layer1_cross_domain_template(
        "银行金融转账存款贷款账户支付", ["unknown", "banking"]
    )

    assert len(items) == 1
    assert items[0].source == "domain_template:banking"


async def test_dedup_keeps_first_when_confidence_equal(monkeypatch, tmp_path):
    payload = {"domain": "unknown", "core_modules": [{"name": "账户"}]}
    _write(tmp_path, "a", payload)
    _write(tmp_path, "b", payload)
    monkeypatch.setattr(module, "DOMAIN_TEMPLATES_DIR", tmp_path)

    items = await layer1_cross_domain_template("req", ["a", "b"])

    assert len(items) == 1
    assert items[0].source == "domain_template:a"


def test_confidence_unknown_domain_default():
    assert compute_template_confidence("whatever", {"domain": "mystery"}) == 0.7


def test_confidence_scales_with_keyword_hits():
    template = {"domain": "banking"}
    none = compute_template_confidence("nothing", template)
    some = compute_template_confidence("银行转账", template)
    all_hits = compute_template_confidence(
        "银行金融转账存款贷款账户支付", template
    )
    assert none == 0.5
    assert none < some < all_hits == 1.0


def test_confidence_caps_at_one():
    template = {"domain": "ecommerce"}
    result = compute_template_confidence("电商商城购物商品订单库存", template)
    assert result == 1.0
