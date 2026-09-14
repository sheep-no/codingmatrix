import types

import pytest

from app.agent.dependency_graph import DependencyGraph
from app.agent.orchestrator_generation.traditional_generate import (
    _requires_layered_generation,
)


def test_small_project_with_dependencies_requires_layered_generation():
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("todo.py")
    graph.add_dependency("main.py", "todo.py")

    assert _requires_layered_generation(2, graph) is True


def test_small_project_without_dependencies_keeps_parallel_generation():
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("todo.py")

    assert _requires_layered_generation(2, graph) is False


@pytest.mark.asyncio
async def test_traditional_completeness_treats_empty_content_as_incomplete(tmp_path):
    from app.agent.orchestrator_generation.traditional_generate import (
        TraditionalGenerateMixin,
    )

    mixin = object.__new__(TraditionalGenerateMixin)
    completeness = await mixin._validate_project_completeness_traditional(
        [{"path": "main.py"}],
        {"main.py": "   \n"},
    )

    assert "main.py" in completeness["empty_files"]
    assert completeness["is_complete"] is False


@pytest.mark.asyncio
async def test_incremental_generate_failure_raises_after_rollback(tmp_path):
    from app.agent.orchestrator_generation.incremental_generate import (
        IncrementalGenerateMixin,
    )

    class _IncrementalTestOrchestrator(IncrementalGenerateMixin):
        def __init__(self, output_dir):
            self.output_dir = output_dir
            self.session_manager = types.SimpleNamespace(
                detect_incremental_changes=self._detect,
                get_file_plan_for_incremental=self._plan,
            )
            self.session_id = "s1"
            self.generated_files = []
            self.errors = []
            self.cancel_event = None

        async def _detect(self, *_args, **_kwargs):
            return {
                "state": types.SimpleNamespace(
                    unchanged_files=[],
                    changed_files=["main.py"],
                )
            }

        def _plan(self, _state):
            return [{"path": "main.py", "description": "entry"}]

        def _report_progress(self, *_args, **_kwargs):
            return None

        async def _generate_single_file(self, *_args, **_kwargs):
            return None

    orchestrator = _IncrementalTestOrchestrator(tmp_path)
    with pytest.raises(RuntimeError, match="incremental file generation failed"):
        await orchestrator._handle_incremental_generation(
            "add a helper",
            [{"path": "main.py", "description": "entry"}],
            {"architecture": {"language": "python"}},
            1,
        )
