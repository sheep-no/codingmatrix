"""Runtime projection tests for the Core generation compatibility layer."""

from pathlib import Path

import pytest

from app.agent.orchestration import (
    AdapterResult,
    execute_core_generation,
)
from app.agent.orchestration.generation_scheduler import GeneratedContent
from app.agent.orchestration.plan import build_file_plan


@pytest.fixture(autouse=True)
def _isolated_checkpoint_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep Core checkpoint writes out of the repository data directory.
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))


class Adapter:
    """Minimal Core adapter whose generated result carries no workflow knowledge."""

    def __init__(self, plan):
        self._plan = plan
        self._shared_context = None

    def bind_shared_context(self, context):
        self._shared_context = context

    async def create_plan(self, request):
        return self._plan

    async def generate_file(self, context):
        return GeneratedContent(content=f"# {context.file_path}\n", model_name="test-model")

    async def finalize(self, state):
        manifest = (
            self._shared_context.get_artifact_manifest()
            if self._shared_context is not None
            else {}
        )
        success = state.status.value == "completed"
        return AdapterResult(
            success=success,
            result={
                "success": success,
                "output_dir": str(state.metadata.get("output_dir", "")),
                "total_files_created": len(manifest),
                "total_files": len(self._plan.files),
                "files": [dict(manifest[path]) for path in sorted(manifest)],
                "validation": {"status": "waiting_local_validation"},
                "errors": [],
                "warnings": [],
                "elapsed_time": 0.0,
            },
        )


def make_adapter() -> Adapter:
    return Adapter(
        build_file_plan(
            [
                {
                    "path": "main.py",
                    "language": "python",
                    "contract": {
                        "exports": ["main"],
                        "framework": "fastapi",
                        "runtime": "python",
                    },
                },
                {
                    "path": "service.py",
                    "language": "python",
                    "depends_on": ["main.py"],
                    "contract": {"framework": "fastapi", "runtime": "python"},
                },
            ],
            requested_paths=["main.py", "service.py"],
        )
    )


@pytest.mark.asyncio
async def test_execute_core_generation_projects_frozen_workflow(tmp_path: Path) -> None:
    output_dir = Path(tmp_path) / "generated"
    output_dir.mkdir()

    payload = await execute_core_generation(
        make_adapter(),
        requirement="create an app",
        task_id="runtime-task",
        session_id="runtime-session",
        mode="traditional",
        output_dir=output_dir,
        metadata={
            "language": "python",
            "framework": "fastapi",
            "runtime": "python",
            # Skip filesystem probing so the projection assertions stay deterministic.
            "profile_context": {},
            "toolchain_plan": {},
        },
    )

    workflow = payload["workflow"]
    assert workflow["workflow_id"] == "runtime-task-traditional"
    assert workflow["name"] == "traditional-generation"
    assert workflow["mode"] == "traditional"
    assert workflow["digest"]
    assert workflow["languages"] == ["python"]
    assert workflow["frameworks"] == ["fastapi"]
    assert workflow["runtimes"] == ["python"]
    nodes = {node["node_id"]: node for node in workflow["nodes"]}
    assert set(nodes) == {"plan", "file:main.py", "file:service.py"}
    assert nodes["plan"]["kind"] == "plan"
    assert nodes["plan"]["handler_ref"] == "orchestration.plan"
    assert nodes["file:main.py"]["handler_ref"] == "orchestration.generate_file"
    assert nodes["file:main.py"]["budget_scope"] == "file"
    assert nodes["file:main.py"]["technology"] == {
        "language": "python",
        "framework": "fastapi",
        "runtime": "python",
    }


def test_workflow_projection_is_empty_without_frozen_ir() -> None:
    from app.agent.orchestration.models import OrchestrationState
    from app.agent.orchestration.runtime import _workflow_projection

    state = OrchestrationState(
        task_id="task-1",
        session_id="session-1",
        engine_version="core-v1",
        mode="traditional",
    )

    assert _workflow_projection(state) == {}


@pytest.mark.asyncio
async def test_frozen_workflow_reaches_api_contract(tmp_path: Path) -> None:
    from app.api.v1.ai_agent.schemas import OrchestratorResponse

    output_dir = Path(tmp_path) / "generated"
    output_dir.mkdir()
    payload = await execute_core_generation(
        make_adapter(),
        requirement="create an app",
        task_id="runtime-task",
        session_id="runtime-session",
        mode="traditional",
        output_dir=output_dir,
        metadata={"profile_context": {}, "toolchain_plan": {}},
    )

    # The response model uses extra="ignore"; an undeclared field would be dropped
    # here and the frozen workflow would never reach an API consumer.
    response = OrchestratorResponse.model_validate(payload)

    assert response.workflow["digest"] == payload["workflow"]["digest"]
    assert {node["node_id"] for node in response.workflow["nodes"]} == {
        "plan",
        "file:main.py",
        "file:service.py",
    }
