import pytest

from app.agent.orchestration import (
    CORE_ENGINE,
    LEGACY_ENGINE,
    compare_shadow_results,
    engine_metadata,
    route_generation,
    select_engine,
)


def _result(success, paths):
    return {"success": success, "generated_files": [{"path": path} for path in paths]}


def test_shadow_comparison_excludes_source_content():
    comparison = compare_shadow_results(
        {"success": True, "generated_files": [{"path": "app.py", "content": "one"}]},
        {"success": True, "generated_files": [{"path": "app.py", "content": "two"}]},
    )

    assert comparison["matches"] is True
    assert "content" not in comparison


def test_engine_flag_defaults_to_legacy_and_accepts_explicit_core(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATION_ENGINE", raising=False)

    assert select_engine() == LEGACY_ENGINE
    assert select_engine("core") == CORE_ENGINE
    assert engine_metadata("core")["engine_route"] == "experimental"


@pytest.mark.asyncio
async def test_core_flag_falls_back_to_legacy_until_core_handler_is_wired(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", "core")

    async def legacy():
        return _result(True, ["app.py"])

    routed = await route_generation(legacy)

    assert routed.engine == CORE_ENGINE
    assert routed.result["success"] is True


@pytest.mark.asyncio
async def test_route_generation_selects_core_and_runs_legacy_shadow(monkeypatch):
    calls = []

    async def legacy():
        calls.append("legacy")
        return _result(True, ["app.py"])

    async def core():
        calls.append("core")
        return _result(True, ["app.py"])

    routed = await route_generation(legacy, core, requested_engine="core", shadow=True)

    assert routed.engine == "core"
    assert calls == ["core", "legacy"]
    assert routed.shadow["matches"] is True
