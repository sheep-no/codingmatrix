"""Branch coverage for app/utils/dynamic_package_manager.py."""

import json

import pytest

from app.utils import dynamic_package_manager as module
from app.utils.dynamic_package_manager import (
    DynamicPackageManager,
    PackageEvaluation,
)


@pytest.fixture
def files(tmp_path, monkeypatch):
    whitelist = tmp_path / "dynamic_whitelist.json"
    evaluations = tmp_path / "package_evaluations.json"
    monkeypatch.setattr(DynamicPackageManager, "WHITELIST_FILE", whitelist)
    monkeypatch.setattr(DynamicPackageManager, "EVALUATION_LOG_FILE", evaluations)
    return whitelist, evaluations


@pytest.fixture
def manager(files):
    return DynamicPackageManager()


# ---------------------------------------------------------------------------
# loading persisted state
# ---------------------------------------------------------------------------


def test_load_whitelist_and_evaluations(files) -> None:
    whitelist, evaluations = files
    whitelist.write_text(json.dumps({"packages": ["alpha", "beta"]}), encoding="utf-8")
    evaluations.write_text(
        json.dumps(
            {
                "gamma": {
                    "package_name": "gamma",
                    "is_safe": True,
                    "risk_level": "safe",
                    "reason": "ok",
                    "category": "utility",
                }
            }
        ),
        encoding="utf-8",
    )

    manager = DynamicPackageManager()

    assert manager._dynamic_whitelist == {"alpha", "beta"}
    assert manager._evaluations["gamma"].is_safe is True


def test_load_corrupt_whitelist_logs_warning(files, monkeypatch) -> None:
    whitelist, _ = files
    whitelist.write_text("{bad", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    manager = DynamicPackageManager()

    assert manager._dynamic_whitelist == set()
    assert warnings


def test_load_corrupt_evaluations_logs_warning(files, monkeypatch) -> None:
    whitelist, evaluations = files
    del whitelist
    evaluations.write_text("{bad", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    manager = DynamicPackageManager()

    assert manager._evaluations == {}
    assert warnings


def test_save_whitelist_failure_logs_warning(files, monkeypatch) -> None:
    manager = DynamicPackageManager()
    manager._dynamic_whitelist = {"alpha"}
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.json, "dumps", boom)

    manager._save_dynamic_whitelist()

    assert warnings


def test_save_evaluations_failure_logs_warning(files, monkeypatch) -> None:
    manager = DynamicPackageManager()
    manager._evaluations["alpha"] = PackageEvaluation(
        "alpha", True, "safe", "ok", "utility"
    )
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.json, "dumps", boom)

    manager._save_evaluation_log()

    assert warnings


def test_save_evaluations_writes_added_flag(files) -> None:
    manager = DynamicPackageManager()
    manager._evaluations["alpha"] = PackageEvaluation(
        "alpha", True, "safe", "ok", "utility", added_to_whitelist=True
    )

    manager._save_evaluation_log()

    data = json.loads(files[1].read_text(encoding="utf-8"))
    assert data["alpha"]["added_to_whitelist"] is True


# ---------------------------------------------------------------------------
# name checks
# ---------------------------------------------------------------------------


def test_is_in_whitelist_static_and_dynamic(manager) -> None:
    manager._dynamic_whitelist.add("custom-pkg")

    assert manager.is_in_whitelist("FastAPI") is True
    assert manager.is_in_whitelist("custom_pkg") is True
    assert manager.is_in_whitelist("unknown") is False


def test_is_blocked_raw_and_normalized(manager) -> None:
    assert manager.is_blocked("requests2") is True
    assert manager.is_blocked("  Requests2  ") is True
    assert manager.is_blocked("urlllib3") is True
    assert manager.is_blocked("fastapi") is False


def test_get_full_whitelist_merges(manager) -> None:
    manager._dynamic_whitelist.add("custom")

    whitelist = manager.get_full_whitelist()

    assert "fastapi" in whitelist
    assert "custom" in whitelist


# ---------------------------------------------------------------------------
# evaluate_and_install
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_whitelisted_package(manager) -> None:
    result = await manager.evaluate_and_install("FastAPI")

    assert result.is_safe is True
    assert result.category == "whitelist"


@pytest.mark.asyncio
async def test_evaluate_blocked_package(manager) -> None:
    result = await manager.evaluate_and_install("requests2")

    assert result.is_safe is False
    assert result.risk_level == "blocked"


@pytest.mark.asyncio
async def test_evaluate_cached_result(manager) -> None:
    cached = PackageEvaluation("alpha", True, "low_risk", "cached", "utility")
    manager._evaluations["alpha"] = cached

    assert await manager.evaluate_and_install("alpha") is cached


@pytest.mark.asyncio
async def test_evaluate_safe_package_adds_to_whitelist(files) -> None:
    async def evaluator(prompt):
        return '{"is_safe": true, "risk_level": "safe", "reason": "ok", "category": "web"}'

    manager = DynamicPackageManager(llm_eval_fn=evaluator)

    result = await manager.evaluate_and_install("brand-new-tool")

    assert result.is_safe is True
    assert result.added_to_whitelist is True
    assert "brand-new-tool" in manager._dynamic_whitelist
    assert files[0].exists()
    assert files[1].exists()


@pytest.mark.asyncio
async def test_evaluate_unsafe_package_not_added(manager) -> None:
    async def evaluator(prompt):
        return '{"is_safe": false, "risk_level": "high_risk", "reason": "bad", "category": "unknown"}'

    manager.llm_eval_fn = evaluator

    result = await manager.evaluate_and_install("suspicious-tool")

    assert result.is_safe is False
    assert "suspicious-tool" not in manager._dynamic_whitelist


# ---------------------------------------------------------------------------
# AI evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_evaluate_without_llm_uses_heuristics(manager) -> None:
    result = await manager._ai_evaluate_package("requests")

    assert result.is_safe is True


@pytest.mark.asyncio
async def test_ai_evaluate_success(manager) -> None:
    async def evaluator(prompt):
        assert "requests-helper" in prompt
        return '{"is_safe": true, "risk_level": "low_risk", "reason": "fine", "category": "utility"}'

    manager.llm_eval_fn = evaluator

    result = await manager._ai_evaluate_package("requests-helper")

    assert result.reason == "fine"


@pytest.mark.asyncio
async def test_ai_evaluate_failure_falls_back(manager, monkeypatch) -> None:
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    async def evaluator(prompt):
        raise RuntimeError("llm down")

    manager.llm_eval_fn = evaluator

    result = await manager._ai_evaluate_package("http-client")

    assert result.is_safe is True
    assert warnings


# ---------------------------------------------------------------------------
# heuristics
# ---------------------------------------------------------------------------


def test_heuristic_flags_typosquat(manager) -> None:
    result = manager._heuristic_evaluate("requesst")

    assert result.is_safe is False
    assert result.risk_level == "high_risk"


def test_heuristic_accepts_dev_keyword(manager) -> None:
    result = manager._heuristic_evaluate("my-async-tool")

    assert result.risk_level == "low_risk"
    assert "async" in result.reason


def test_heuristic_rejects_short_name(manager) -> None:
    result = manager._heuristic_evaluate("zzz")

    assert result.is_safe is False
    assert result.risk_level == "medium_risk"


def test_heuristic_default_low_risk(manager) -> None:
    result = manager._heuristic_evaluate("randompackage")

    assert result.is_safe is True
    assert result.risk_level == "low_risk"
    assert result.category == "unknown"


def test_typosquat_guards() -> None:
    assert DynamicPackageManager._is_likely_typosquat("requests", "requests") is False
    assert DynamicPackageManager._is_likely_typosquat("req", "requests") is False
    assert DynamicPackageManager._is_likely_typosquat("requestz", "requests") is True
    assert DynamicPackageManager._is_likely_typosquat("completely-different", "redis") is False


# ---------------------------------------------------------------------------
# response parsing
# ---------------------------------------------------------------------------


def test_parse_json_response(manager) -> None:
    result = manager._parse_evaluation_response(
        "pkg",
        'prefix {"is_safe": true, "risk_level": "safe", "reason": "why", "category": "web"} suffix',
    )

    assert result.is_safe is True
    assert result.category == "web"


def test_parse_json_response_defaults(manager) -> None:
    # Empty objects do not match the non-empty regex, so parsing falls back
    # to the text heuristic path.
    result = manager._parse_evaluation_response("pkg", "{}")

    assert result.is_safe is False
    assert result.risk_level == "medium_risk"
    assert result.reason == "AI 评估（文本解析）"
    assert result.category == "unknown"


def test_parse_json_response_uses_defaults_for_missing_keys(manager) -> None:
    result = manager._parse_evaluation_response("pkg", '{"extra": 1}')

    assert result.is_safe is False
    assert result.risk_level == "medium_risk"
    assert result.reason == "AI 评估"
    assert result.category == "unknown"


def test_parse_invalid_json_uses_text(manager) -> None:
    result = manager._parse_evaluation_response("pkg", "{not valid json}")

    assert result.is_safe is False
    assert result.risk_level == "medium_risk"
    assert result.reason == "AI 评估（文本解析）"


def test_parse_text_mentions_safe(manager) -> None:
    result = manager._parse_evaluation_response("pkg", "This package is safe to use")

    assert result.is_safe is True
    assert result.risk_level == "safe"


# ---------------------------------------------------------------------------
# normalization / filtering
# ---------------------------------------------------------------------------


def test_normalize_package_name(manager) -> None:
    assert manager._normalize_package_name("  My_Pkg[extra] ") == "my-pkg"
    assert manager._normalize_package_name("A__B--C") == "a-b-c"


def test_filter_packages(manager) -> None:
    manager._dynamic_whitelist.add("custom-pkg")

    allowed, rejected = manager.filter_packages(
        ["fastapi", "custom_pkg", "requests2", "unknown-package"]
    )

    assert allowed == ["fastapi", "custom_pkg"]
    assert rejected == ["requests2", "unknown-package"]
