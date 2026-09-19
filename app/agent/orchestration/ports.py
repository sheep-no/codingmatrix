"""Ports the orchestration core requires from a generation engine.

Core adapters depend on :class:`GenerationAgentPort` instead of reaching into a
concrete legacy agent. The private helpers of the legacy engine are mapped onto
this public contract in exactly one place, :class:`LegacyAgentGenerationPort`,
so the dependency direction keeps pointing inward and a single module owns the
compatibility surface. A change to a legacy private method can no longer reach
the orchestration layer without passing through that adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class GenerationAgentPort(Protocol):
    """The generation-engine surface Core adapters are allowed to use."""

    output_dir: Path
    architect: Any
    complexity: Any
    model_assignment: Any
    backend_engineer: Any
    callback: Any
    api_key_token: Any
    has_file_generation_with_model: bool
    has_content_syntax_validation: bool

    async def initialize_components(self, requirement: str) -> None: ...

    async def initialize_components_fast(self, requirement: str) -> None: ...

    async def generate_single_file(
        self,
        file_info: Mapping[str, Any],
        project_context: Mapping[str, Any],
        total_files: int,
        generated_contents: Mapping[str, str],
    ) -> Mapping[str, Any]: ...

    def select_model_for_file(self, file_path: str) -> str: ...

    def select_engineer(self, file_path: str) -> Any: ...

    async def generate_file_with_model(
        self,
        file_path: str,
        file_info: Mapping[str, Any],
        engineer: Any,
        model_name: str,
        project_context: Mapping[str, Any],
        generated_contents: Mapping[str, str],
        spec_generator: Any,
        dependency_graph: Any,
        callback: Any,
        *,
        persist: bool = True,
    ) -> Any: ...

    async def validate_content_syntax(self, file_path: str, content: str) -> bool: ...

    def build_project_summary_from_graph(self, graph: Any) -> str: ...

    async def analyze_changes_with_architect(
        self,
        requirement: str,
        summary: str,
        graph: Any,
        callback: Any,
    ) -> Sequence[Mapping[str, Any]]: ...

    def set_dependency_graph(self, graph: Any) -> None: ...

    def report_file_event(
        self,
        file_path: str,
        content: str,
        description: str,
        file_type: str,
        *,
        operation: str = "modify",
    ) -> None: ...

    def report_file_diff_event(
        self,
        file_path: str,
        original_content: str,
        new_content: str,
        *,
        operation: str = "modify",
    ) -> None: ...


class LegacyAgentGenerationPort:
    """Map the legacy agent's private helpers onto :class:`GenerationAgentPort`.

    This is the only module that names legacy private members. Optional
    helpers are reported through ``has_*`` flags and degrade to no-ops instead
    of leaking attribute probing into the adapters.
    """

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    @property
    def output_dir(self) -> Path:
        return Path(self._agent.output_dir)

    @property
    def architect(self) -> Any:
        return self._agent.architect

    @property
    def complexity(self) -> Any:
        return getattr(self._agent, "complexity", None)

    @property
    def model_assignment(self) -> Any:
        return getattr(self._agent, "model_assignment", None)

    @property
    def backend_engineer(self) -> Any:
        return getattr(self._agent, "backend_engineer", None)

    @property
    def callback(self) -> Any:
        return getattr(self._agent, "callback", None)

    @property
    def api_key_token(self) -> Any:
        return getattr(self._agent, "api_key_token", None)

    @property
    def has_file_generation_with_model(self) -> bool:
        return callable(getattr(self._agent, "_generate_file_with_model", None))

    @property
    def has_content_syntax_validation(self) -> bool:
        return callable(getattr(self._agent, "_validate_content_syntax", None))

    async def initialize_components(self, requirement: str) -> None:
        await self._agent._initialize_components(requirement)

    async def initialize_components_fast(self, requirement: str) -> None:
        await self._agent._initialize_components_fast(requirement)

    async def generate_single_file(
        self,
        file_info: Mapping[str, Any],
        project_context: Mapping[str, Any],
        total_files: int,
        generated_contents: Mapping[str, str],
    ) -> Mapping[str, Any]:
        return await self._agent._generate_single_file(
            file_info,
            project_context,
            total_files,
            generated_contents,
        )

    def select_model_for_file(self, file_path: str) -> str:
        return self._agent._select_model_for_file(file_path)

    def select_engineer(self, file_path: str) -> Any:
        return self._agent._select_engineer(file_path)

    async def generate_file_with_model(
        self,
        file_path: str,
        file_info: Mapping[str, Any],
        engineer: Any,
        model_name: str,
        project_context: Mapping[str, Any],
        generated_contents: Mapping[str, str],
        spec_generator: Any,
        dependency_graph: Any,
        callback: Any,
        *,
        persist: bool = True,
    ) -> Any:
        return await self._agent._generate_file_with_model(
            file_path,
            file_info,
            engineer,
            model_name,
            project_context,
            generated_contents,
            spec_generator,
            dependency_graph,
            callback,
            persist=persist,
        )

    async def validate_content_syntax(self, file_path: str, content: str) -> bool:
        return bool(await self._agent._validate_content_syntax(file_path, content))

    def build_project_summary_from_graph(self, graph: Any) -> str:
        return self._agent._build_project_summary_from_graph(graph)

    async def analyze_changes_with_architect(
        self,
        requirement: str,
        summary: str,
        graph: Any,
        callback: Any,
    ) -> Sequence[Mapping[str, Any]]:
        return await self._agent._analyze_changes_with_architect(
            requirement,
            summary,
            graph,
            callback,
        )

    def set_dependency_graph(self, graph: Any) -> None:
        self._agent.dependency_graph_obj = graph

    def report_file_event(
        self,
        file_path: str,
        content: str,
        description: str,
        file_type: str,
        *,
        operation: str = "modify",
    ) -> None:
        reporter = getattr(self._agent, "_report_file_event", None)
        if callable(reporter):
            reporter(file_path, content, description, file_type, operation=operation)

    def report_file_diff_event(
        self,
        file_path: str,
        original_content: str,
        new_content: str,
        *,
        operation: str = "modify",
    ) -> None:
        reporter = getattr(self._agent, "_report_file_diff_event", None)
        if callable(reporter):
            reporter(file_path, original_content, new_content, operation=operation)
