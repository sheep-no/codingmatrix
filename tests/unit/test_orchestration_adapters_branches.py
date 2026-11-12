"""Branch coverage for orchestration adapter helpers and failure paths."""

from __future__ import annotations

import pytest

from app.agent.orchestration import (
    GenerationRequest,
    IncrementalAdapter,
    SpecFirstAdapter,
    TraditionalAdapter,
)
from app.agent.orchestration import adapters as A
from app.agent.orchestration.models import OrchestrationState, OrchestrationStatus


class _Architect:
    async def design_architecture(self, requirement, complexity, callback=None):
        return {
            "language": "python",
            "file_plan": [
                {"path": "app.py", "description": "entry"},
                {"path": "config.py", "description": "config", "depends_on": ["app.py"]},
            ],
        }


class _Agent:
    """Minimal legacy-agent surface used by the adapters."""

    def __init__(self, tmp_path, *, complexity="default", assignment="default"):
        self.architect = _Architect()
        self.complexity = object() if complexity == "default" else complexity
        if assignment == "default":
            from types import SimpleNamespace

            self.model_assignment = SimpleNamespace(
                architect_model="arch",
                frontend_model="front",
                backend_model="back",
                reviewer_model="review",
                fallback_model="fallback",
            )
        else:
            self.model_assignment = assignment
        self.callback = None
        self.output_dir = tmp_path
        self.api_key_token = None
        self.events = []

    async def _initialize_components(self, requirement):
        self.initialized = requirement

    async def _initialize_components_fast(self, requirement):
        self.initialized = requirement

    async def _generate_single_file(
        self, file_info, project_context, total_files, generated_contents
    ):
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "m"}

    def _select_model_for_file(self, file_path):
        return "fallback"

    def _select_engineer(self, file_path):
        return object()

    async def _generate_file_with_model(
        self,
        file_path,
        file_info,
        engineer,
        model_name,
        project_context,
        generated_contents,
        spec_generator,
        dependency_graph,
        callback,
        *,
        persist=True,
    ):
        return f"# {file_path}\n"

    def _report_file_event(self, *args, **kwargs):
        self.events.append(("file", args, kwargs))

    def _report_file_diff_event(self, *args, **kwargs):
        self.events.append(("diff", args, kwargs))

    def _build_project_summary_from_graph(self, graph):
        return "summary"

    async def _analyze_changes_with_architect(self, requirement, summary, graph, callback):
        return []


class _CoreAgent(_Agent):
    async def _validate_content_syntax(self, file_path, content):
        return self.syntax_ok


def _state(status=OrchestrationStatus.COMPLETED, diagnostics=()):
    kwargs = dict(
        task_id="t",
        session_id="s",
        engine_version="e",
        mode="m",
        status=status,
        diagnostics=diagnostics,
    )
    if status is not OrchestrationStatus.RUNNING:
        kwargs["terminal_event_id"] = "evt"
        kwargs["applied_event_ids"] = ("evt",)
        kwargs["revision"] = 1
    return OrchestrationState(**kwargs)


def _request(metadata=None, requirement="build an app"):
    return GenerationRequest(
        requirement=requirement,
        task_id="t",
        session_id="s",
        metadata=metadata or {},
    )


class _Info:
    def __init__(self, raw_line):
        self.raw_line = raw_line


class _FakeLanguageAdapter:
    def __init__(self, lines, targets):
        self._lines = lines
        self._targets = targets

    def parse_imports(self, content, file_path):
        return [_Info(line) for line in self._lines]

    def resolve_import_to_file(self, info, file_path):
        return self._targets


class TestImportHelpers:
    def test_empty_content_or_adapter_is_noop(self):
        adapter = _FakeLanguageAdapter(["import calc"], ["calc.py"])

        assert A.preserved_local_import_gaps(adapter, "main.py", "", "x", ("calc.py",)) == ((), ())
        assert A.preserved_local_import_gaps(None, "main.py", "x", "x", ("calc.py",)) == ((), ())

    def test_duplicate_and_blank_raw_lines(self):
        adapter = _FakeLanguageAdapter(["import calc", "import calc", ""], ["calc.py"])

        diagnostics, missing = A.preserved_local_import_gaps(
            adapter, "main.py", "import calc\n", "", ("calc.py",)
        )

        assert diagnostics == ("incremental modify dropped local import of calc.py",)
        assert missing == ("import calc",)

    def test_restore_returns_content_when_nothing_to_add(self):
        assert A.restore_dropped_import_lines("X = 1\n", ["", " "]) == "X = 1\n"
        assert A.restore_dropped_import_lines("import os\n", ["import os"]) == "import os\n"

    def test_restore_after_shebang(self):
        restored = A.restore_dropped_import_lines("#!python\nX = 1\n", ["import os"])

        assert restored == "#!python\nimport os\nX = 1\n"

    def test_restore_reuses_existing_import_slot(self):
        content = "from calc import add\nprint(add(1, 2))\n"

        restored = A.restore_dropped_import_lines(
            content, ["from calc import add, subtract"]
        )

        assert restored.startswith("from calc import add, subtract\n")
        assert restored.count("from calc import") == 1

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("import value from 'pkg'", "from 'pkg'"),
            ("import numpy as np", "import numpy"),
            ("const x = require('pkg')", "require('pkg')"),
            ("plain text", "plain text"),
        ],
    )
    def test_import_statement_key_variants(self, line, expected):
        assert A._import_statement_key(line) == expected

    def test_split_line_ending_variants(self):
        assert A._split_line_ending("a\r\n") == ("a", "\r\n")
        assert A._split_line_ending("a\n") == ("a", "\n")
        assert A._split_line_ending("a") == ("a", "")


class TestTraditionalAdapterFailures:
    @pytest.mark.asyncio
    async def test_generation_failure_raises(self, tmp_path):
        agent = _Agent(tmp_path)
        adapter = TraditionalAdapter(agent)
        await adapter.create_plan(_request())

        async def failed(*args, **kwargs):
            return {"success": False}

        agent._generate_single_file = failed

        with pytest.raises(RuntimeError, match="traditional generation failed"):
            await adapter.generate_file(
                type("Ctx", (), {"file_path": "app.py", "upstream_contents": {}})()
            )

    @pytest.mark.asyncio
    async def test_missing_content_reads_generated_file(self, tmp_path):
        agent = _Agent(tmp_path)
        (tmp_path / "app.py").write_text("# from disk\n", encoding="utf-8")
        adapter = TraditionalAdapter(agent)
        await adapter.create_plan(_request())

        async def no_content(*args, **kwargs):
            return {"success": True, "model": "m"}

        agent._generate_single_file = no_content
        generated = await adapter.generate_file(
            type("Ctx", (), {"file_path": "app.py", "upstream_contents": {}})()
        )

        assert generated.content == "# from disk\n"

    @pytest.mark.asyncio
    async def test_finalize_unwraps_enum_complexity(self, tmp_path):
        agent = _Agent(tmp_path)
        adapter = TraditionalAdapter(agent)
        await adapter.create_plan(_request())
        agent.complexity = type("Cmp", (), {"level": type("Lvl", (), {"value": "medium"})()})()

        result = await adapter.finalize(_state())

        assert result.result["complexity"] == "medium"
        assert result.success is True

    def test_finalize_without_plan_and_context(self, tmp_path):
        adapter = TraditionalAdapter(_Agent(tmp_path))

        assert adapter._shared_context is None
        adapter.bind_shared_context(object())
        assert adapter._shared_context is not None


class TestPlannedHelpers:
    def test_complexity_and_assignment_defaults(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path, complexity=None, assignment=None))

        assert adapter._complexity_payload() == {"level": "small", "estimated_files": 1}
        assert adapter._model_assignment_payload() == {}

    def test_emit_events_skips_empty_content(self, tmp_path):
        agent = _Agent(tmp_path)
        adapter = SpecFirstAdapter(agent)

        adapter._emit_generated_file_events("a.py", "", {})

        assert agent.events == []

    def test_emit_events_create_and_diff(self, tmp_path):
        agent = _Agent(tmp_path)
        adapter = SpecFirstAdapter(agent)

        adapter._emit_generated_file_events(
            "a.py", "new\n", {"action": "add", "description": "d", "file_type": "py"}
        )
        adapter._emit_generated_file_events("a.py", "new\n", {}, "old\n")

        assert agent.events[0][2]["operation"] == "create"
        assert agent.events[1][2]["operation"] == "modify"

    def test_freeze_plan_coerces_string_dependencies(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))

        plan = adapter._freeze_plan(
            [
                {"path": "a.py", "dependencies": "b.py"},
                {"path": "b.py"},
            ]
        )

        assert plan.files[0].dependencies == ("b.py",)

    def test_validate_local_imports_variants(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))
        adapter._file_entries = {"app/main.py": {}, "app/models.py": {}}

        assert adapter._validate_local_imports("main.js", "") == ()
        assert adapter._validate_local_imports("main.py", "def broken(\n")[0].startswith(
            "syntax error:"
        )
        assert adapter._validate_local_imports(
            "main.py", "import app.main\nfrom app.models import thing\n"
        ) == ()
        assert adapter._validate_local_imports(
            "main.py",
            "from . import sibling\nimport app.ghost\nimport app.ghost\n",
        ) == ("local import outside frozen file set: app.ghost",)

    def test_contract_file_role_variants(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))
        adapter._file_entries = {"a.py": {"role": "entry"}, "b.py": {"type": "model"}}

        assert adapter._contract_file_role("a.py") == "entry"
        assert adapter._contract_file_role("b.py") == "model"
        assert adapter._contract_file_role("missing.py") is None

    def test_candidate_contract_unsupported_language(self, tmp_path, monkeypatch):
        adapter = SpecFirstAdapter(_Agent(tmp_path))

        def unsupported(language):
            raise LookupError("no adapter")

        monkeypatch.setattr(A, "get_language_adapter", unsupported)
        language_adapter, diagnostics = adapter._validate_candidate_contract("a.py", "X = 1\n")

        assert language_adapter is None
        assert "contract parser capability unsupported" in diagnostics[0]

    def test_candidate_contract_invalid_declaration(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))
        adapter._file_entries = {
            "a.py": {"contract": {"assertions": [{"fact": ""}]}}
        }

        language_adapter, diagnostics = adapter._validate_candidate_contract("a.py", "X = 1\n")

        assert language_adapter is not None
        assert "invalid contract declaration" in diagnostics[0]


class TestPlannedGenerate:
    @pytest.mark.asyncio
    async def test_generate_requires_plan(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))

        with pytest.raises(RuntimeError, match="create_plan must run"):
            await adapter.generate_file(
                type("Ctx", (), {"file_path": "a.py", "upstream_contents": {}})()
            )

    @pytest.mark.asyncio
    async def test_invalid_model_response_returns_diagnostic(self, tmp_path):
        agent = _Agent(tmp_path)

        async def tool_call(*args, **kwargs):
            return '{"tool": "write_file"}'

        agent._generate_file_with_model = tool_call
        adapter = SpecFirstAdapter(agent)
        await adapter.create_plan(
            _request({"specification": {"language": "python", "file_plan": [{"path": "a.py"}]}})
        )

        generated = await adapter.generate_file(
            type("Ctx", (), {"file_path": "a.py", "upstream_contents": {}})()
        )

        assert generated.content == ""
        assert generated.validation_passed is False
        assert generated.diagnostics == ("model returned tool-call JSON",)

    @pytest.mark.asyncio
    async def test_java_spring_rules_are_added(self, tmp_path):
        agent = _Agent(tmp_path)

        async def java_source(*args, **kwargs):
            return "public class Main {}\n"

        agent._generate_file_with_model = java_source
        adapter = SpecFirstAdapter(agent)
        await adapter.create_plan(
            _request(
                {
                    "specification": {
                        "language": "java",
                        "framework": "spring",
                        "file_plan": [{"path": "Main.java"}],
                    }
                }
            )
        )

        await adapter.generate_file(
            type("Ctx", (), {"file_path": "Main.java", "upstream_contents": {}})()
        )

        rules = adapter._project_context["generation_contract"]["rules"]
        assert any("top-level type" in rule for rule in rules)

    @pytest.mark.asyncio
    async def test_dropped_import_without_restore_marks_invalid(self, tmp_path, monkeypatch):
        agent = _Agent(tmp_path)

        async def generate(*args, **kwargs):
            return "import calc\n"

        agent._generate_file_with_model = generate
        adapter = SpecFirstAdapter(agent)
        await adapter.create_plan(
            _request({"specification": {"language": "python", "file_plan": [{"path": "main.py"}]}})
        )
        adapter._file_entries["main.py"]["original_content"] = "import calc\n"
        adapter._file_entries["main.py"]["action"] = "modify"
        monkeypatch.setattr(
            A,
            "preserved_local_import_gaps",
            lambda *args, **kwargs: (("dropped local import",), ("import calc",)),
        )

        generated = await adapter.generate_file(
            type("Ctx", (), {"file_path": "main.py", "upstream_contents": {}})()
        )

        assert generated.validation_passed is False
        assert "dropped local import" in generated.diagnostics

    @pytest.mark.asyncio
    async def test_content_syntax_validation_can_fail(self, tmp_path):
        agent = _CoreAgent(tmp_path)
        agent.syntax_ok = False
        adapter = SpecFirstAdapter(agent)
        await adapter.create_plan(
            _request({"specification": {"language": "python", "file_plan": [{"path": "a.py"}]}})
        )

        generated = await adapter.generate_file(
            type("Ctx", (), {"file_path": "a.py", "upstream_contents": {}})()
        )

        assert generated.validation_passed is False


class TestPlannedFinalize:
    @pytest.mark.asyncio
    async def test_nested_diagnostics_are_flattened(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))
        diagnostics = (
            {"message": "top"},
            {"details": {"nodes": "not-a-mapping"}},
            {"details": {"nodes": {"a.py": "not-a-mapping"}}},
            {
                "details": {
                    "nodes": {
                        "b.py": {
                            "diagnostics": (
                                "not-a-mapping",
                                {"message": " inner "},
                                {"message": ""},
                            )
                        }
                    }
                }
            },
        )

        result = await adapter.finalize(_state(diagnostics=diagnostics))

        assert "top" in result.result["errors"]
        assert "b.py: inner" in result.result["errors"]


class TestSpecFirstFailures:
    @pytest.mark.asyncio
    async def test_spec_generation_failure_raises(self, tmp_path, monkeypatch):
        from app.agent.spec_first_generator import SpecFirstGenerator

        async def fail(*args, **kwargs):
            return False

        monkeypatch.setattr(SpecFirstGenerator, "generate_all_specs", fail)
        adapter = SpecFirstAdapter(_Agent(tmp_path))

        with pytest.raises(RuntimeError, match="Spec-First specification generation failed"):
            await adapter.create_plan(_request({"user_requirement": "build it"}))

    @pytest.mark.asyncio
    async def test_empty_architecture_file_plan_raises(self, tmp_path):
        adapter = SpecFirstAdapter(_Agent(tmp_path))

        with pytest.raises(ValueError, match="non-empty file_plan"):
            await adapter.create_plan(
                _request({"architecture": {"language": "python", "file_plan": []}})
            )

    def test_allowed_plan_tests_depend_on_sources(self):
        entries = SpecFirstAdapter._build_allowed_file_plan(
            ["models.py", "tests/test_models.py"]
        )
        tests = next(entry for entry in entries if entry["path"].startswith("tests/"))

        assert tests["dependencies"] == ["models.py"]


class TestIncrementalFailures:
    @pytest.mark.asyncio
    async def test_missing_project_raises(self, tmp_path):
        adapter = IncrementalAdapter(_Agent(tmp_path))

        with pytest.raises(RuntimeError, match="requires an existing project"):
            await adapter.create_plan(
                _request(
                    {
                        "architecture": {"language": "python"},
                        "dependency_graph": None,
                        "change_plan": [{"path": "a.py", "action": "add"}],
                    }
                )
            )

    @pytest.mark.asyncio
    async def test_rebuild_without_nodes_raises(self, tmp_path):
        # 只有被跳过的目录内容，依赖图重建后没有任何节点
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "dep.js").write_text("module.exports = 1\n")
        adapter = IncrementalAdapter(_Agent(tmp_path))

        with pytest.raises(RuntimeError, match="could not rebuild"):
            await adapter.create_plan(
                _request(
                    {
                        "architecture": {"language": "python"},
                        "dependency_graph": None,
                        "change_plan": [{"path": "a.py", "action": "add"}],
                    }
                )
            )

    @pytest.mark.asyncio
    async def test_empty_change_plan_raises(self, tmp_path):
        from types import SimpleNamespace

        adapter = IncrementalAdapter(_Agent(tmp_path))

        with pytest.raises(ValueError, match="at least one affected file"):
            await adapter.create_plan(
                _request(
                    {
                        "architecture": {"language": "python"},
                        "dependency_graph": SimpleNamespace(adjacency={}),
                        "change_plan": [],
                    }
                )
            )

    @pytest.mark.asyncio
    async def test_deleting_absent_file_is_not_transactional(self, tmp_path):
        from types import SimpleNamespace

        adapter = IncrementalAdapter(_Agent(tmp_path))

        with pytest.raises(ValueError, match="deletion is not transactional"):
            await adapter.create_plan(
                _request(
                    {
                        "architecture": {"language": "python"},
                        "dependency_graph": SimpleNamespace(adjacency={}),
                        "change_plan": [{"path": "gone.py", "action": "delete"}],
                    }
                )
            )

    @pytest.mark.asyncio
    async def test_modifying_absent_file_reraises(self, tmp_path):
        from types import SimpleNamespace

        adapter = IncrementalAdapter(_Agent(tmp_path))

        with pytest.raises(ValueError, match="absent from snapshot"):
            await adapter.create_plan(
                _request(
                    {
                        "architecture": {"language": "python"},
                        "dependency_graph": SimpleNamespace(adjacency={}),
                        "change_plan": [{"path": "gone.py", "action": "modify"}],
                    }
                )
            )

    @pytest.mark.asyncio
    async def test_missing_external_dependency_is_skipped(self, tmp_path):
        from types import SimpleNamespace

        (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
        adapter = IncrementalAdapter(_Agent(tmp_path))

        await adapter.create_plan(
            _request(
                {
                    "architecture": {"language": "python"},
                    "dependency_graph": SimpleNamespace(
                        adjacency={"existing.py": {"missing.py"}}
                    ),
                    "change_plan": [
                        {"path": "existing.py", "action": "modify"}
                    ],
                }
            )
        )

        assert "missing.py" not in adapter._generated_contents
