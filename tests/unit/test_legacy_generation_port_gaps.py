"""LegacyAgentGenerationPort 委托覆盖。"""

from pathlib import Path

import pytest

from app.agent.orchestration.ports import LegacyAgentGenerationPort


class _Agent:
    def __init__(self, tmp_path: Path):
        self.output_dir = str(tmp_path)
        self.architect = "architect"
        self.complexity = "complexity"
        self.model_assignment = "assignment"
        self.backend_engineer = "engineer"
        self.callback = "callback"
        self.api_key_token = "token"
        self.calls = []
        self.dependency_graph_obj = None

    async def _initialize_components(self, requirement):
        self.calls.append(("initialize", requirement))

    async def _initialize_components_fast(self, requirement):
        self.calls.append(("initialize_fast", requirement))

    async def _generate_single_file(self, *args):
        self.calls.append(("single", args))
        return {"path": "a.py"}

    def _select_model_for_file(self, file_path):
        return f"model:{file_path}"

    def _select_engineer(self, file_path):
        return f"engineer:{file_path}"

    async def _generate_file_with_model(self, *args, persist=True):
        self.calls.append(("model", args, persist))
        return {"persisted": persist}

    async def _validate_content_syntax(self, file_path, content):
        return "ok"

    def _build_project_summary_from_graph(self, graph):
        return f"summary:{graph}"

    async def _analyze_changes_with_architect(self, *args):
        return [{"path": "a.py"}]

    def _report_file_event(self, *args, **kwargs):
        self.calls.append(("file_event", args, kwargs))

    def _report_file_diff_event(self, *args, **kwargs):
        self.calls.append(("diff_event", args, kwargs))


@pytest.mark.asyncio
async def test_port_properties_and_optional_flags(tmp_path):
    agent = _Agent(tmp_path)
    port = LegacyAgentGenerationPort(agent)

    assert port.output_dir == Path(tmp_path)
    assert port.architect == "architect"
    assert port.complexity == "complexity"
    assert port.model_assignment == "assignment"
    assert port.backend_engineer == "engineer"
    assert port.callback == "callback"
    assert port.api_key_token == "token"
    assert port.has_file_generation_with_model is True
    assert port.has_content_syntax_validation is True


def test_port_optional_flags_are_false_for_bare_agent():
    port = LegacyAgentGenerationPort(object())

    assert port.complexity is None
    assert port.model_assignment is None
    assert port.backend_engineer is None
    assert port.callback is None
    assert port.api_key_token is None
    assert port.has_file_generation_with_model is False
    assert port.has_content_syntax_validation is False


@pytest.mark.asyncio
async def test_port_delegates_generation_calls(tmp_path):
    agent = _Agent(tmp_path)
    port = LegacyAgentGenerationPort(agent)

    await port.initialize_components("req")
    await port.initialize_components_fast("req-fast")
    single = await port.generate_single_file({}, {}, 1, {})
    model = await port.generate_file_with_model(
        "a.py", {}, "engineer", "model", {}, {}, None, None, None, persist=False
    )

    assert single == {"path": "a.py"}
    assert model == {"persisted": False}
    assert port.select_model_for_file("a.py") == "model:a.py"
    assert port.select_engineer("a.py") == "engineer:a.py"
    assert await port.validate_content_syntax("a.py", "") is True
    assert port.build_project_summary_from_graph("g") == "summary:g"
    assert await port.analyze_changes_with_architect("r", "s", "g", None) == [{"path": "a.py"}]


def test_port_sets_dependency_graph_and_reports_events(tmp_path):
    agent = _Agent(tmp_path)
    port = LegacyAgentGenerationPort(agent)
    marker = object()

    port.set_dependency_graph(marker)
    port.report_file_event("a.py", "x", "desc", "py", operation="create")
    port.report_file_diff_event("a.py", "old", "new")

    assert agent.dependency_graph_obj is marker
    assert agent.calls[-2][0] == "file_event"
    assert agent.calls[-1][0] == "diff_event"
    assert agent.calls[-1][2]["operation"] == "modify"


def test_port_event_reporters_are_noops_for_bare_agent():
    port = LegacyAgentGenerationPort(object())

    port.report_file_event("a.py", "x", "desc", "py")
    port.report_file_diff_event("a.py", "old", "new")
