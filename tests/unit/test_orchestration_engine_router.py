import pytest

from app.agent.orchestration import compare_shadow_results, route_generation


def _result(success, paths):
    return {"success": success, "generated_files": [{"path": path} for path in paths]}


def test_shadow_comparison_excludes_source_content():
    comparison = compare_shadow_results(
        {"success": True, "generated_files": [{"path": "app.py", "content": "one"}]},
        {"success": True, "generated_files": [{"path": "app.py", "content": "two"}]},
    )

    assert comparison["matches"] is True
    assert "content" not in comparison


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
