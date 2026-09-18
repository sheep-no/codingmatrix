from types import SimpleNamespace

from app.agent.orchestration.routing import select_engine
from app.api.v1.ai_agent.orchestrate_endpoints import (
    PASSTHROUGH_SSE_EVENTS,
    _pipeline_mode_banner,
    _pipeline_mode_payload,
)


def test_new_project_explores_and_skips_unmatched_skills():
    request = SimpleNamespace(
        engine=None,
        incremental=False,
        spec_first=True,
        enable_skills=True,
    )
    payload = _pipeline_mode_payload(request, "")
    assert payload["type"] == "pipeline_mode"
    assert payload["engine"] == "legacy"
    assert payload["incremental"] is False
    assert payload["tools"] == "explore"
    assert payload["frozen_contract"] is False
    assert payload["skills_injected"] is False
    assert "可探盘" in payload["message"]
    banner = _pipeline_mode_banner(payload)
    assert banner.startswith("[Pipeline Mode]")
    assert "tools=explore" in banner


def test_core_incremental_freezes_tools_when_skills_injected():
    request = SimpleNamespace(
        engine="core",
        incremental=True,
        spec_first=True,
        enable_skills=True,
    )
    payload = _pipeline_mode_payload(request, "[user:whisper-ellipsis]\nbody")
    assert payload["engine"] == "core"
    assert payload["tools"] == "frozen"
    assert payload["frozen_contract"] is True
    assert payload["skills_injected"] is True
    assert "冻结后直写" in payload["message"]
    assert "If tools=frozen" in _pipeline_mode_banner(payload)


def test_incremental_without_explicit_engine_reports_selected_engine():
    """The banner must match the engine build_legacy_workflow will actually run."""
    request = SimpleNamespace(
        engine=None,
        incremental=True,
        spec_first=True,
        enable_skills=True,
    )
    payload = _pipeline_mode_payload(request, "")
    selected = select_engine(None)
    assert payload["engine"] == selected
    assert payload["tools"] == ("frozen" if selected == "core" else "explore")
    assert payload["frozen_contract"] is (selected == "core")


def test_enable_skills_false_is_visible():
    request = SimpleNamespace(
        engine="legacy",
        incremental=True,
        spec_first=False,
        enable_skills=False,
    )
    payload = _pipeline_mode_payload(request, "")
    assert payload["enable_skills"] is False
    assert payload["tools"] == "explore"
    assert "Skill 关闭" in payload["message"]


def test_pipeline_mode_is_passthrough_sse():
    assert "pipeline_mode" in PASSTHROUGH_SSE_EVENTS
