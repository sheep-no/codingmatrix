from pathlib import Path

import pytest

from app.agent.orchestration import (
    CORE_ENGINE,
    LEGACY_ENGINE,
    GenerationRequest,
    TraditionalAdapter,
    engine_metadata,
    select_engine,
)
from app.agent.workflow_registry import build_legacy_workflow, run_workflow


class _Architect:
    async def design_architecture(self, requirement, complexity, callback=None):
        return {
            "language": "python",
            "file_plan": [
                {"path": "app.py", "description": "application entry point"},
                {"path": "config.py", "description": "configuration", "depends_on": ["app.py"]},
            ],
        }


class _Agent:
    def __init__(self, tmp_path):
        self.architect = _Architect()
        self.complexity = object()
        self.callback = None
        self.output_dir = Path(tmp_path)

    async def _initialize_components(self, requirement):
        self.initialized_requirement = requirement

    async def _generate_single_file(self, file_info, project_context, total_files, generated_contents):
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "test-model"}

    def _select_model_for_file(self, file_path):
        return "fallback-model"


@pytest.mark.asyncio
async def test_traditional_adapter_creates_plan_and_generates_file(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build a python app",
        task_id="task-1",
        session_id="session-1",
        metadata={},
    )

    plan = await adapter.create_plan(request)
    generated = await adapter.generate_file(
        type("Context", (), {
            "file_path": "app.py",
            "upstream_contents": {},
        })()
    )

    assert [item.path for item in plan.files] == ["app.py", "config.py"]
    assert generated.content == "# app.py\n"
    assert generated.model_name == "test-model"


def test_engine_selection_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATION_ENGINE", raising=False)
    assert select_engine() == LEGACY_ENGINE
    assert select_engine(CORE_ENGINE) == CORE_ENGINE
    assert engine_metadata(CORE_ENGINE)["engine_version"] == "core-v1"


@pytest.mark.asyncio
async def test_legacy_workflow_checkpoint_contains_selected_engine(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", "core")
    workflow = build_legacy_workflow("test", "/test", lambda state: {"success": True})

    state = await run_workflow(
        workflow,
        session_id="session-adapter-test",
        task_id="task-adapter-test",
    )

    assert state.metadata["engine"] == CORE_ENGINE
    assert state.metadata["engine_version"] == "core-v1"
    assert state.metadata["engine_route"] == "experimental"


@pytest.mark.asyncio
async def test_traditional_adapter_requires_plan(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    context = type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()

    with pytest.raises(RuntimeError, match="create_plan"):
        await adapter.generate_file(context)
