"""engine_router 选择、await 与 shadow 对比补测。"""

import pytest

from app.agent.orchestration.engine_router import (
    EngineRouteResult,
    compare_shadow_results,
    route_generation,
)
from app.agent.orchestration.routing import CORE_ENGINE, LEGACY_ENGINE, select_engine


def test_select_engine_defaults_and_override():
    assert select_engine(None) == LEGACY_ENGINE
    assert select_engine("core") == CORE_ENGINE
    assert select_engine("legacy") == LEGACY_ENGINE


def test_compare_shadow_results_file_dicts():
    primary = {"success": True, "generated_files": {"a.py": "x"}}
    shadow = {"success": True, "files": [{"path": "a.py"}]}

    result = compare_shadow_results(primary, shadow)

    assert result["matches"] is True
    assert result["primary_file_count"] == 1


def test_compare_shadow_reports_differences():
    result = compare_shadow_results(
        {"success": True, "files": [{"path": "a.py"}]},
        {"success": False, "files": [{"path": "b.py"}]},
    )

    assert result["matches"] is False
    assert result["missing_from_primary"] == ["b.py"]
    assert result["missing_from_shadow"] == ["a.py"]


def test_compare_shadow_handles_non_dict_inputs():
    result = compare_shadow_results("plain", None)
    assert result["primary_success"] is None
    assert result["primary_file_count"] == 0


def test_compare_shadow_ignores_invalid_list_items():
    result = compare_shadow_results({"files": ["x", {"no_path": 1}]}, {"files": []})
    assert result["primary_file_count"] == 0


async def test_route_generation_runs_sync_handler():
    result = await route_generation(lambda: {"success": True}, requested_engine="legacy")
    assert result == EngineRouteResult("legacy", {"success": True}, None)


async def test_route_generation_awaits_async_handler():
    async def handler():
        return {"success": True}

    result = await route_generation(handler, requested_engine="legacy")
    assert result.result == {"success": True}


async def test_route_generation_core_without_handler_falls_back():
    result = await route_generation(lambda: "legacy", requested_engine="core")
    assert result.engine == CORE_ENGINE
    assert result.result == "legacy"


async def test_route_generation_selects_core():
    result = await route_generation(
        lambda: "legacy", lambda: "core", requested_engine="core"
    )
    assert result.result == "core"


async def test_route_generation_shadow_compares_other_engine():
    async def legacy():
        return {"success": True, "files": [{"path": "a.py"}]}

    async def core():
        return {"success": True, "files": [{"path": "a.py"}]}

    result = await route_generation(
        legacy, core, requested_engine="legacy", shadow=True
    )

    assert result.shadow["matches"] is True
    assert "metadata" in result.shadow


async def test_route_generation_shadow_core_engine_uses_legacy_for_comparison():
    result = await route_generation(
        lambda: {"success": True},
        lambda: {"success": False},
        requested_engine="core",
        shadow=True,
    )

    assert result.engine == CORE_ENGINE
    assert result.result == {"success": False}
    assert result.shadow["shadow_success"] is True


async def test_route_generation_without_core_skips_shadow():
    result = await route_generation(lambda: "only", shadow=True)
    assert result.shadow is None


def test_file_paths_non_list_non_dict_returns_empty():
    from app.agent.orchestration.engine_router import _file_paths

    assert _file_paths({"files": "not-a-list"}) == set()
