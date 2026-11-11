"""Architect 分支补测：归一化、严格路径、完整性补全与批量规划。"""

import asyncio
import types

import pytest

from app.agent.architect import Architect
from app.agent.architect_json_parser import ArchitectJsonParser
from app.agent.complexity import ComplexityAnalysis, ProjectComplexity


def _architect() -> Architect:
    agent = Architect.__new__(Architect)
    agent.json_parser = ArchitectJsonParser()
    agent.model_name = "test-model"
    return agent


def _complexity(
    *,
    level=ProjectComplexity.MEDIUM,
    estimated_files=5,
    frontend=False,
    backend=True,
    database=False,
):
    return ComplexityAnalysis(
        level=level,
        estimated_files=estimated_files,
        has_frontend=frontend,
        has_backend=backend,
        has_database=database,
        has_auth=False,
        key_technologies=["Python"],
        risk_factors=[],
    )


class TestPrompts:
    def test_system_prompt_prefers_registry(self, monkeypatch):
        import app.services.skill_registry as registry

        monkeypatch.setattr(registry, "get_skill", lambda name: "custom prompt")
        assert _architect().SYSTEM_PROMPT == "custom prompt"

    def test_system_prompt_swallows_registry_error_then_uses_loader(self, monkeypatch):
        import app.services.skill_registry as registry
        import app.agent.architect as module

        def boom(_name):
            raise RuntimeError("registry down")

        monkeypatch.setattr(registry, "get_skill", boom)
        monkeypatch.setattr(module, "load_architect_prompt", lambda: "loaded prompt")
        assert _architect().SYSTEM_PROMPT == "loaded prompt"

    def test_system_prompt_falls_back_when_loader_returns_none(self, monkeypatch):
        import app.services.skill_registry as registry
        import app.agent.architect as module

        monkeypatch.setattr(registry, "get_skill", lambda name: None)
        monkeypatch.setattr(module, "load_architect_prompt", lambda: None)
        assert "首席软件架构师" in _architect().SYSTEM_PROMPT

    def test_fallback_prompt_mentions_json_only(self):
        assert "JSON" in _architect()._fallback_prompt()


class TestLanguageRules:
    def test_unknown_language_requests_inference(self):
        architect = _architect()
        detection = types.SimpleNamespace(needs_clarification=True)
        text = architect._build_language_rules_text(
            "zig", None, None, ["zig"], detection
        )
        assert "不在已知列表中" in text

    def test_no_backend_replaces_framework_and_structure(self):
        architect = _architect()
        detection = types.SimpleNamespace(needs_clarification=False)
        text = architect._build_language_rules_text(
            "python", None, None, ["python"], detection, has_backend=False
        )
        assert "默认后端框架：无" in text
        assert "按用户指定的文件路径生成" in text

    def test_frontend_and_extra_backend_languages_are_appended(self):
        architect = _architect()
        detection = types.SimpleNamespace(needs_clarification=False)
        text = architect._build_language_rules_text(
            "python", "javascript", "python", ["python", "javascript", "go"], detection
        )
        assert "前端语言：javascript" in text
        assert "辅助语言：go" in text

    def test_languages_needing_clarification_are_skipped(self):
        architect = _architect()
        detection = types.SimpleNamespace(needs_clarification=False)
        text = architect._build_language_rules_text(
            "python", "brainfuck", None, ["python", "brainfuck"], detection
        )
        assert "前端语言：brainfuck" not in text


class TestJsonExtraction:
    def test_extract_returns_none_for_empty_response(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return ""

        architect.call_llm = fake
        assert (
            asyncio.run(architect._extract_json_with_llm("raw", _complexity())) is None
        )

    def test_extract_returns_none_for_non_dict(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return "[1, 2]"

        architect.call_llm = fake
        assert (
            asyncio.run(architect._extract_json_with_llm("raw", _complexity())) is None
        )

    def test_extract_returns_dict(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return '{"file_plan": []}'

        architect.call_llm = fake
        assert asyncio.run(
            architect._extract_json_with_llm("raw", _complexity())
        ) == {"file_plan": []}

    def test_extract_swallows_exceptions(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            raise RuntimeError("gateway down")

        architect.call_llm = fake
        assert (
            asyncio.run(architect._extract_json_with_llm("raw", _complexity())) is None
        )


class TestFilePlanNormalization:
    @pytest.mark.parametrize(
        "item",
        ["src/a.py", {"path": "src/a.py"}, {"file": "src/a.py"}, {"name": "src/a.py"}],
    )
    def test_supported_shapes_are_normalized(self, item):
        entry = Architect._normalize_file_plan_item(item, "python")
        assert entry["path"] == "src/a.py"
        assert entry["language"] == "python"

    def test_extensionless_known_project_file_is_kept(self):
        entry = Architect._normalize_file_plan_item({"path": "LICENSE"}, "python")
        assert entry["path"] == "LICENSE"

    def test_extensionless_unknown_name_is_dropped(self):
        assert Architect._normalize_file_plan_item({"path": "MakefileX"}, "python") is None

    def test_backslash_paths_are_normalized(self):
        entry = Architect._normalize_file_plan_item("src\\pkg\\a.py", "python")
        assert entry["path"] == "src/pkg/a.py"

    @pytest.mark.parametrize("item", [None, 5, [], {"path": ""}, {"path": ".."}])
    def test_invalid_items_are_dropped(self, item):
        assert Architect._normalize_file_plan_item(item, "python") is None

    def test_file_plan_deduplicates_and_requires_list(self):
        assert Architect._normalize_file_plan("not a list", "python") == []
        entries = Architect._normalize_file_plan(["a.py", "a.py", "b.py"], "python")
        assert [entry["path"] for entry in entries] == ["a.py", "b.py"]

    def test_harvest_skips_cycles_and_depth(self):
        architect = _architect()
        cyclic = {}
        cyclic["files"] = [cyclic]
        assert architect._harvest_file_plan(cyclic, "python") == []
        assert architect._harvest_file_plan({"files": [{"path": "a.py"}]}, "python", depth=6) == []

    def test_harvest_searches_nested_architecture(self):
        architect = _architect()
        harvested = architect._harvest_file_plan(
            {"architecture": {"file_plan": [{"path": "app/main.py"}]}}, "python"
        )
        assert harvested[0]["path"] == "app/main.py"

    def test_harvest_ignores_unrelated_values(self):
        architect = _architect()
        assert architect._harvest_file_plan({"note": "x"}, "python") == []
        assert architect._harvest_file_plan(42, "python") == []

    def test_harvest_recurses_into_list_items(self):
        architect = _architect()
        harvested = architect._harvest_file_plan(
            [{"note": "x"}, {"architecture": {"files": [{"path": "app/main.py"}]}}],
            "python",
        )
        assert harvested[0]["path"] == "app/main.py"

    def test_ensure_architecture_file_plan_parses_json_string(self):
        architect = _architect()
        result = architect._ensure_architecture_file_plan(
            {"file_plan": '[{"path": "main.py"}]'},
            "写 main.py",
            _complexity(),
            "python",
            None,
        )
        assert result["file_plan"][0]["path"] == "main.py"

    def test_ensure_architecture_file_plan_raises_without_plan(self):
        architect = _architect()
        with pytest.raises(ValueError, match="did not include a file_plan"):
            architect._ensure_architecture_file_plan(
                {"file_plan": []}, "需求", _complexity(), "python", None
            )

    def test_stale_aliases_are_dropped_after_harvest(self):
        architect = _architect()
        result = architect._ensure_architecture_file_plan(
            {
                "files": [{"path": "main.py"}],
                "architecture": {"files": [{"path": "main.py"}]},
            },
            "需求",
            _complexity(),
            "python",
            None,
        )
        assert "files" not in result
        assert "files" not in result["architecture"]


class TestJsonishAndCanonicalization:
    def test_parse_jsonish_non_string_passthrough(self):
        assert _architect()._parse_jsonish({"a": 1}) == {"a": 1}

    def test_parse_jsonish_blank_and_prose_unchanged(self):
        architect = _architect()
        assert architect._parse_jsonish("   ") == "   "
        assert architect._parse_jsonish("plain prose") == "plain prose"

    def test_parse_jsonish_falls_back_to_stdlib_json(self, monkeypatch):
        architect = _architect()

        def boom(text):
            raise ValueError("bad")

        monkeypatch.setattr(architect.json_parser, "safe_parse_json", boom)
        assert architect._parse_jsonish('{"a": 1}') == {"a": 1}

    def test_parse_jsonish_returns_original_when_both_fail(self, monkeypatch):
        architect = _architect()

        def boom(text):
            raise ValueError("bad")

        monkeypatch.setattr(architect.json_parser, "safe_parse_json", boom)
        assert architect._parse_jsonish("{broken") == "{broken"

    def test_canonicalize_interfaces_none_and_scalar(self):
        architect = _architect()
        assert architect._canonicalize_interfaces(None) == {}
        assert architect._canonicalize_interfaces(5) == {}

    def test_canonicalize_interfaces_list_passthrough(self):
        assert _architect()._canonicalize_interfaces([{"module": "a"}]) == [{"module": "a"}]

    def test_canonicalize_interfaces_single_entry(self):
        assert _architect()._canonicalize_interfaces({"module": "a"}) == {"module": "a"}

    def test_canonicalize_interfaces_entries_list(self):
        assert _architect()._canonicalize_interfaces({"entries": [{"module": "a"}]}) == [
            {"module": "a"}
        ]

    def test_canonicalize_interfaces_named_map(self):
        result = _architect()._canonicalize_interfaces({"a": {"exports": ["x"]}})
        assert result == [{"exports": ["x"], "module": "a", "owner": "a", "symbols": ["x"]}]

    def test_canonicalize_interfaces_passthrough_unstructured(self):
        assert _architect()._canonicalize_interfaces({"a": 1}) == {"a": 1}

    def test_drop_unnamed_dependencies_list(self):
        result = Architect._drop_unnamed_dependencies(["", "requests", {"name": ""}])
        assert result == ["requests"]

    def test_drop_unnamed_dependencies_single_object(self):
        assert Architect._drop_unnamed_dependencies({"name": ""}) == {}
        assert Architect._drop_unnamed_dependencies({"package": "x"}) == {
            "package": "x",
            "name": "x",
        }

    def test_drop_unnamed_dependencies_grouped(self):
        result = Architect._drop_unnamed_dependencies({"runtime": "", "dev": ["", "pytest"]})
        assert result["dev"] == ["pytest"]

    def test_drop_unnamed_dependencies_passthrough_non_collection(self):
        assert Architect._drop_unnamed_dependencies(5) == 5

    def test_drop_unnamed_dependencies_keeps_non_string_items(self):
        assert Architect._drop_unnamed_dependencies([5, "requests"]) == [5, "requests"]

    def test_drop_unnamed_dependencies_keeps_grouped_non_list_value(self):
        assert Architect._drop_unnamed_dependencies({"runtime": 5}) == {"runtime": 5}

    def test_coerce_architecture_fields_non_dict(self):
        assert _architect()._coerce_architecture_fields([]) == {}

    def test_coerce_parses_contract_and_imports(self):
        architect = _architect()
        result = architect._coerce_architecture_fields(
            {
                "file_plan": [
                    {
                        "path": "a.py",
                        "contract": '{"exports": ["x"]}',
                        "imports": '"b.py"',
                    },
                    {"path": "b.py", "imports": ""},
                    "not-a-dict",
                ]
            }
        )
        assert result["file_plan"][0]["contract"] == {"exports": ["x"]}
        assert result["file_plan"][0]["imports"] == ["b.py"]
        assert result["file_plan"][1]["imports"] == []

    def test_coerce_contract_non_dict_falls_back_to_empty(self):
        result = _architect()._coerce_architecture_fields(
            {"file_plan": [{"path": "a.py", "contract": "'prose'"}]}
        )
        assert result["file_plan"][0]["contract"] == {}

    def test_coerce_imports_list_is_kept(self):
        result = _architect()._coerce_architecture_fields(
            {"file_plan": [{"path": "a.py", "imports": '["b.py"]'}]}
        )
        assert result["file_plan"][0]["imports"] == ["b.py"]

    def test_canonicalize_rejects_empty(self):
        with pytest.raises(ValueError, match="architecture was empty"):
            _architect()._canonicalize_architecture(
                {}, "需求", _complexity(), "python", None
            )

    def test_canonicalize_fills_defaults(self):
        result = _architect()._canonicalize_architecture(
            {"file_plan": [{"path": "main.py"}]},
            "需求",
            _complexity(),
            "python",
            "javascript",
        )
        assert result["language"] == "python"
        assert result["frontend_language"] == "javascript"
        assert result["api_spec"] == {}
        assert result["db_schema"] == {}
        assert result["interfaces"] == {}
        assert result["dependencies"] == {}

    def test_canonicalize_resets_non_collection_interfaces(self):
        result = _architect()._canonicalize_architecture(
            {"file_plan": [{"path": "main.py"}], "interfaces": "oops"},
            "需求",
            _complexity(),
            "python",
            None,
        )
        assert result["interfaces"] == {}


class TestDefaultArchitectures:
    @pytest.mark.parametrize(
        ("language", "entry"),
        [
            ("python", "main.py"),
            ("javascript", "src/index.ts"),
            ("go", "main.go"),
            ("java", "src/main/java/com/example/Application.java"),
            ("rust", "src/main.rs"),
            ("zig", "main.zig"),
        ],
    )
    def test_entry_point_per_language(self, language, entry):
        result = _architect()._get_default_architecture(
            _complexity(), language=language
        )
        assert result["file_plan"][0]["path"] == entry

    def test_unknown_language_without_extension_uses_name(self, monkeypatch):
        import app.agent.language_detector as detector

        monkeypatch.setattr(
            detector.LanguageDetector,
            "get_language_specific_rules",
            staticmethod(lambda language: {}),
        )
        result = _architect()._get_default_architecture(
            _complexity(), language="brainfuck"
        )
        assert result["file_plan"][0]["path"] == "main.brainfuck"

    def test_project_type_variants(self):
        architect = _architect()
        assert (
            architect._get_default_architecture(
                _complexity(frontend=True, backend=True)
            )["project_type"]
            == "fullstack"
        )
        assert (
            architect._get_default_architecture(
                _complexity(frontend=True, backend=False)
            )["project_type"]
            == "frontend"
        )
        assert (
            architect._get_default_architecture(
                _complexity(frontend=False, backend=True)
            )["project_type"]
            == "backend"
        )
        assert (
            architect._get_default_architecture(
                _complexity(frontend=False, backend=False)
            )["project_type"]
            == "script"
        )

    def test_compact_eight_file_architecture_non_python_truncates(self):
        result = _architect()._get_compact_eight_file_architecture(
            "service", _complexity(), language="go"
        )
        assert result["used_compact_eight_file_plan"] is True
        assert len(result["file_plan"]) <= 8

    def test_compact_python_ticket_plan_sets_schema(self):
        result = _architect()._get_compact_eight_file_architecture(
            "build a ticket system with 工单", _complexity(), language="python"
        )
        assert result["project_spec"]["default"]["framework"] == "FastAPI"
        assert "tickets" in result["db_schema"]
        assert len(result["file_plan"]) == 8

    def test_compact_python_non_ticket_keeps_spec(self):
        result = _architect()._get_compact_eight_file_architecture(
            "build a blog", _complexity(), language="python"
        )
        assert "tickets" not in result["db_schema"]

    @pytest.mark.parametrize(
        ("language", "prefix", "ext"),
        [
            ("python", "app/", "py"),
            ("javascript", "src/", "js"),
            ("typescript", "src/", "ts"),
            ("go", "internal/", "go"),
            ("java", "", "java"),
            ("unknown", "", "py"),
        ],
    )
    def test_domain_file_plan_prefixes(self, language, prefix, ext):
        plan = _architect()._domain_file_plan(language, "order")
        paths = [entry["path"] for entry in plan]
        assert paths[0] == f"{prefix}models/order_model.{ext}"
        assert all(entry["language"] == language for entry in plan)

    def test_requirement_aware_adds_explicit_paths(self):
        result = _architect()._get_requirement_aware_default_architecture(
            "生成 app/models/order.py、app/services/order.py 和 main.py",
            _complexity(),
            language="python",
        )
        by_path = {entry["path"]: entry for entry in result["file_plan"]}
        assert by_path["app/models/order.py"]["file_type"] == "model"
        assert by_path["app/services/order.py"]["file_type"] == "service"
        assert by_path["app/services/order.py"]["imports"] == ["app/models/order.py"]
        assert by_path["main.py"]["imports"] == ["app/services/order.py"]

    def test_requirement_aware_unknown_path_is_utils(self):
        result = _architect()._get_requirement_aware_default_architecture(
            "生成 tools/report.py", _complexity(), language="python"
        )
        by_path = {entry["path"]: entry for entry in result["file_plan"]}
        assert by_path["tools/report.py"]["file_type"] == "utils"

    def test_requirement_aware_api_paths_are_classified(self):
        result = _architect()._get_requirement_aware_default_architecture(
            "生成 app/api/order.py", _complexity(), language="python"
        )
        by_path = {entry["path"]: entry for entry in result["file_plan"]}
        assert by_path["app/api/order.py"]["file_type"] == "api"

    def test_requirement_aware_skips_already_planned(self):
        result = _architect()._get_requirement_aware_default_architecture(
            "生成 main.py", _complexity(), language="python"
        )
        assert [entry["path"] for entry in result["file_plan"]].count("main.py") == 1


class TestModuleHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("from a.b import c", "a.b"),
            ("import a.b", "a.b"),
            ("a.b", "a.b"),
            ("from .relative import x", None),
            ("bad path", None),
            ("", None),
            (None, None),
        ],
    )
    def test_parse_import_to_module(self, raw, expected):
        assert Architect._parse_import_to_module(raw) == expected

    def test_planned_covers_by_candidate(self):
        assert Architect._planned_covers_module(
            {"pkg/mod.py"}, "pkg.mod", ["pkg/mod.py"]
        )

    def test_planned_covers_simple_module_by_stem(self):
        assert Architect._planned_covers_module({"helpers.py"}, "helpers", [])

    def test_planned_covers_dotted_module_by_parent_dir(self):
        assert Architect._planned_covers_module(
            {"pkg/mod/__init__.py"}, "pkg.mod", []
        )

    def test_planned_covers_package_init(self):
        assert Architect._planned_covers_module({"pkg/__init__.py"}, "pkg", [])

    def test_planned_covers_dotted_owner_directory(self):
        assert Architect._planned_covers_module({"pkg/core.py"}, "pkg.core", [])

    def test_planned_does_not_cover_unrelated(self):
        assert not Architect._planned_covers_module({"other.py"}, "pkg.core", [])

    def test_planned_empty_module(self):
        assert not Architect._planned_covers_module({"a.py"}, "", [])

    def test_is_external_module_without_adapter(self):
        assert Architect._is_external_module(None, "fastapi") is False
        assert Architect._is_external_module(types.SimpleNamespace(), "fastapi") is False

    def test_is_external_module_delegates(self):
        adapter = types.SimpleNamespace(is_known_external_module=lambda name: True)
        assert Architect._is_external_module(adapter, "fastapi") is True
        assert Architect._is_external_module(adapter, "") is False

    def test_strict_paths_none_for_empty_requirement(self):
        assert Architect._extract_strict_file_paths("") is None

    def test_strict_paths_none_without_scope_phrase(self):
        assert Architect._extract_strict_file_paths("做一个博客系统") is None

    def test_strict_paths_frozen_list(self):
        requirement = (
            "Generate exactly these files and no others: main.py, README.md, LICENSE."
        )
        assert Architect._extract_strict_file_paths(requirement) == {
            "main.py",
            "README.md",
            "LICENSE",
        }

    def test_strict_paths_frozen_ignores_invalid_tokens(self):
        requirement = "Generate exactly these files and no others: main.py, a b c."
        assert Architect._extract_strict_file_paths(requirement) == {"main.py"}

    def test_strict_paths_only_phrase(self):
        requirement = "只需要 main.py 和 helper.py 两个文件"
        assert Architect._extract_strict_file_paths(requirement) == {
            "main.py",
            "helper.py",
        }

    def test_prefer_most_specific_paths_strips_dot_slash(self):
        assert Architect._prefer_most_specific_paths({"./src/App.vue", "App.vue"}) == {
            "src/App.vue"
        }

    def test_prefer_keeps_genuinely_distinct_same_name(self):
        assert Architect._prefer_most_specific_paths(
            {"app/main.py", "tests/main.py"}
        ) == {"app/main.py", "tests/main.py"}

    def test_skip_boilerplate_none(self):
        assert Architect._skip_boilerplate_files(None) is False

    def test_skip_boilerplate_simple_single_file(self):
        assert (
            Architect._skip_boilerplate_files(
                types.SimpleNamespace(
                    level=types.SimpleNamespace(value="simple"), estimated_files=1
                )
            )
            is True
        )

    def test_skip_boilerplate_invalid_estimate(self):
        assert (
            Architect._skip_boilerplate_files(
                {"level": "simple", "estimated_files": "many"}
            )
            is False
        )

    @pytest.mark.parametrize(
        ("path", "expected_head"),
        [
            (".gitignore", ".gitignore"),
            ("./src/a.py", "./src/a.py"),
            ("src\\a.py", "src\\a.py"),
        ],
    )
    def test_path_module_forms_preserve_dot_files(self, path, expected_head):
        assert Architect._path_module_forms(path, "python")[0] == expected_head

    def test_path_module_forms_python_adds_dotted(self):
        forms = Architect._path_module_forms("src/app.py", "python")
        assert "src.app" in forms

    def test_path_module_forms_empty(self):
        assert Architect._path_module_forms("", "python") == []

    def test_import_remap_pairs_same_path_empty(self):
        assert Architect._import_remap_pairs("a.py", "a.py", "python") == []
        assert Architect._import_remap_pairs("", "a.py", "python") == []

    def test_rewrite_collapsed_imports_handles_missing_fields(self):
        item = {"imports": "not-a-list"}
        Architect._rewrite_collapsed_imports(item, [("old", "new")])
        assert item["imports"] == "not-a-list"

    def test_rewrite_collapsed_imports_skips_blank_value(self):
        item = {"imports": ["", "old.mod"]}
        Architect._rewrite_collapsed_imports(item, [("old.mod", "new.mod")])
        assert item["imports"] == ["", "new.mod"]


class TestCompleteness:
    def test_empty_plan_returns_input(self):
        architect = _architect()
        architecture = {"file_plan": []}
        assert architect._ensure_file_plan_completeness(architecture) is architecture

    def test_default_fields_are_filled(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {"file_plan": [{"path": "main.py"}]}, target_language="python"
        )
        item = result["file_plan"][0]
        assert item["file_type"] == "unknown"
        assert item["description"] == ""
        assert item["priority"] == 3
        assert item["imports"] == []
        assert item["language"] == "python"

    def test_strict_paths_replace_plan_and_rewrite_imports(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {"path": "utils.py", "imports": ["from utils import x"], "language": "python"},
                    {"path": "extra.py", "imports": [], "language": "python"},
                ]
            },
            target_language="python",
            strict_paths={"app/utils.py"},
        )
        paths = [entry["path"] for entry in result["file_plan"]]
        assert paths == ["app/utils.py"]
        assert result["strict_file_paths"] == ["app/utils.py"]
        assert result["file_plan"][0]["imports"] == ["from app.utils import x"]

    def test_frozen_scope_stops_at_sentence_boundary(self):
        requirement = (
            "Generate exactly these files and no others: main.py. "
            "Build a small tool afterwards."
        )
        assert Architect._extract_strict_file_paths(requirement) == {"main.py"}

    def test_external_imports_are_not_added_to_plan(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {
                        "path": "main.py",
                        "imports": ["import fastapi"],
                        "language": "python",
                    }
                ]
            },
            target_language="python",
        )
        assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]

    def test_strict_paths_create_missing_entry(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {"file_plan": [{"path": "main.py", "imports": [], "language": "python"}]},
            target_language="python",
            strict_paths={"app/new.py"},
        )
        entry = result["file_plan"][0]
        assert entry["path"] == "app/new.py"
        assert entry["description"] == "实现 app/new.py"
        assert entry["file_type"] == "unknown"

    def test_strict_paths_pick_shortest_basename_match(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {"path": "deep/nested/config.py", "imports": [], "language": "python"},
                    {"path": "config.py", "imports": [], "language": "python"},
                ]
            },
            target_language="python",
            strict_paths={"app/config.py"},
        )
        assert result["file_plan"][0]["path"] == "app/config.py"

    def test_external_plan_entries_are_removed(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {"path": "main.py", "imports": [], "language": "python"},
                    {"path": "fastapi/routing.py", "imports": [], "language": "python"},
                ]
            },
            target_language="python",
        )
        assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]

    def test_missing_imported_module_is_added(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {
                        "path": "main.py",
                        "imports": ["from helpers.util import run"],
                        "language": "python",
                    }
                ]
            },
            target_language="python",
        )
        assert "helpers/util.py" in [entry["path"] for entry in result["file_plan"]]

    def test_dict_import_items_are_parsed(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {
                "file_plan": [
                    {
                        "path": "main.py",
                        "imports": [
                            {"module": "from pkg.one import x", "items": ["from pkg.two import y"]}
                        ],
                        "language": "python",
                    }
                ]
            },
            target_language="python",
        )
        paths = [entry["path"] for entry in result["file_plan"]]
        assert "pkg/one.py" in paths
        assert "pkg/two.py" in paths

    def test_language_is_detected_when_not_provided(self):
        architect = _architect()
        result = architect._ensure_file_plan_completeness(
            {"file_plan": [{"path": "main.py", "imports": [], "language": "python"}]}
        )
        assert result["file_plan"][0]["language"] == "python"


class TestExpandFilePlan:
    def _architect(self):
        return _architect()

    def test_frozen_strict_scope_is_skipped(self):
        architect = self._architect()
        architecture = {"file_plan": [{"path": "main.py"}], "strict_file_paths": ["main.py"]}
        assert asyncio.run(
            architect.expand_file_plan(architecture, _complexity(), 10)
        ) is architecture

    def test_already_at_target_is_skipped(self):
        architect = self._architect()
        architecture = {"file_plan": [{"path": "main.py"}, {"path": "b.py"}]}
        assert asyncio.run(
            architect.expand_file_plan(architecture, _complexity(), 2)
        ) is architecture

    def test_batches_stop_when_no_new_files(self):
        architect = self._architect()
        architecture = {
            "file_plan": [{"path": "main.py", "imports": [], "language": "python"}],
            "language": "python",
        }

        async def no_new(*_args, **_kwargs):
            return []

        architect._generate_batch_files = no_new
        result = asyncio.run(architect.expand_file_plan(architecture, _complexity(), 3))
        assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]

    def test_batches_merge_new_files(self):
        architect = self._architect()
        architecture = {
            "file_plan": [{"path": "main.py", "imports": [], "language": "python"}],
            "language": "python",
        }
        batches = [
            [{"path": "service.py", "imports": [], "language": "python"}],
            [],
        ]

        async def fake(*_args, **_kwargs):
            return batches.pop(0)

        architect._generate_batch_files = fake
        result = asyncio.run(architect.expand_file_plan(architecture, _complexity(), 2))
        paths = [entry["path"] for entry in result["file_plan"]]
        assert "service.py" in paths

    def test_batches_skip_entries_without_path(self):
        architect = self._architect()
        architecture = {
            "file_plan": [{"path": "main.py", "imports": [], "language": "python"}],
            "language": "python",
        }
        batches = [[{"path": ""}, {"path": "service.py", "imports": [], "language": "python"}], []]

        async def fake(*_args, **_kwargs):
            return batches.pop(0)

        architect._generate_batch_files = fake
        result = asyncio.run(architect.expand_file_plan(architecture, _complexity(), 2))
        assert [entry["path"] for entry in result["file_plan"]] == ["main.py", "service.py"]

    def test_missing_graph_files_are_added_before_batches(self, monkeypatch):
        architect = self._architect()
        architecture = {
            "file_plan": [{"path": "main.py", "imports": [], "language": "python"}],
            "language": "python",
        }

        class FakeGraph:
            def __init__(self, language_adapter=None):
                pass

            def build_from_architecture(self, arch):
                return None

            def get_missing_files(self):
                return ["helpers.py"]

            def add_missing_files(self, arch):
                arch["file_plan"].append(
                    {"path": "helpers.py", "imports": [], "language": "python"}
                )
                return arch

        monkeypatch.setattr("app.agent.dependency_graph.DependencyGraph", FakeGraph)

        async def no_new(*_args, **_kwargs):
            return []

        architect._generate_batch_files = no_new
        result = asyncio.run(architect.expand_file_plan(architecture, _complexity(), 2))
        assert "helpers.py" in [entry["path"] for entry in result["file_plan"]]


class TestGenerateBatchFiles:
    def _architect(self):
        return _architect()

    def _architecture(self, **overrides):
        architecture = {
            "file_plan": [{"path": "main.py", "description": "入口"}],
            "language": "python",
            "tech_stack": ["FastAPI"],
            "requirement": "构建服务",
        }
        architecture.update(overrides)
        return architecture

    def _run(self, architect, architecture, response):
        async def fake(prompt, system_prompt=""):
            fake.prompt = prompt
            return response

        architect.call_llm = fake
        result = asyncio.run(
            architect._generate_batch_files(
                architecture, types.SimpleNamespace(key_technologies=[]), 5
            )
        )
        return result, fake.prompt

    def test_language_hints_are_included(self):
        architect = self._architect()
        result, prompt = self._run(
            architect,
            self._architecture(
                frontend_language="javascript",
                backend_language="go",
                all_languages=["python", "javascript", "go"],
            ),
            "[]",
        )
        assert result == []
        assert "前端语言：javascript" in prompt
        assert "后端语言：go" in prompt
        assert "项目使用多种语言" in prompt

    def test_missing_requirement_falls_back_to_project_type(self):
        architect = self._architect()
        _, prompt = self._run(
            architect, self._architecture(requirement="", project_type="backend"), "[]"
        )
        assert "需求：backend" in prompt

    def test_list_response_is_accepted(self):
        architect = self._architect()
        result, _ = self._run(
            architect, self._architecture(), '[{"path": "app/x.py"}]'
        )
        assert result[0]["path"] == "app/x.py"

    def test_dict_response_with_plan(self):
        architect = self._architect()
        result, _ = self._run(
            architect,
            self._architecture(),
            '{"file_plan": [{"path": "app/y.py"}]}',
        )
        assert result[0]["path"] == "app/y.py"

    def test_missing_fields_are_filled(self):
        architect = self._architect()
        result, _ = self._run(
            architect,
            self._architecture(frontend_language="javascript"),
            '[{"path": "src/Card.vue", "file_type": "frontend_component"}, {"path": "app/z.py"}]',
        )
        assert result[0]["description"] == ""
        assert result[0]["priority"] == 3
        assert result[0]["imports"] == []
        assert result[0]["language"] == "javascript"
        assert result[1]["language"] == "python"

    def test_duplicate_paths_are_filtered(self):
        architect = self._architect()
        result, _ = self._run(
            architect,
            self._architecture(),
            '[{"path": "main.py"}, {"path": "new.py"}]',
        )
        assert [entry["path"] for entry in result] == ["new.py"]

    def test_invalid_items_are_skipped(self):
        architect = self._architect()
        result, _ = self._run(
            architect,
            self._architecture(),
            '[null, 1, {"description": "no path"}, {"path": "ok.py"}]',
        )
        assert [entry["path"] for entry in result] == ["ok.py"]

    def test_scalar_response_raises(self):
        architect = self._architect()
        with pytest.raises(ValueError, match="顶层必须是对象或数组"):
            self._run(architect, self._architecture(), '"text"')

    def test_empty_response_raises(self):
        architect = self._architect()
        with pytest.raises(ValueError, match="batch file plan was empty"):
            self._run(architect, self._architecture(), "  ")

    def test_parse_errors_are_reraised(self):
        architect = self._architect()
        architect.json_parser = types.SimpleNamespace(
            safe_parse_json=lambda text: (_ for _ in ()).throw(ValueError("bad json"))
        )
        with pytest.raises(ValueError, match="bad json"):
            self._run(architect, self._architecture(), "{}")

    def test_non_container_parse_result_raises(self):
        architect = self._architect()
        architect._safe_parse_json = lambda _text: 5
        with pytest.raises(ValueError, match="not a JSON array or object"):
            self._run(architect, self._architecture(), "anything")


class TestDesignArchitecture:
    def _design(self, architect, requirement, complexity):
        return asyncio.run(architect.design_architecture(requirement, complexity))

    def test_parse_failure_uses_llm_extraction(self):
        architect = _architect()
        calls = []

        async def fake(prompt, system_prompt=""):
            calls.append(prompt)
            if len(calls) == 1:
                return "not json"
            return '{"file_plan": [{"path": "main.py", "file_type": "entry"}]}'

        architect.call_llm = fake
        result = self._design(architect, "写 main.py", _complexity())
        assert result["file_plan"][0]["path"] == "main.py"

    def test_parse_failure_and_extraction_failure_raises(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return "not json"

        architect.call_llm = fake
        with pytest.raises(ValueError, match="JSON extraction failed"):
            self._design(architect, "写 main.py", _complexity())

    def test_empty_response_raises(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return "   "

        architect.call_llm = fake
        with pytest.raises(ValueError, match="architecture was empty"):
            self._design(architect, "写 main.py", _complexity())

    def test_parsed_empty_object_raises(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return "{}"

        architect.call_llm = fake
        with pytest.raises(ValueError, match="architecture was empty"):
            self._design(architect, "写 main.py", _complexity())

    def test_non_object_json_raises(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return "[1, 2]"

        architect.call_llm = fake
        architect._safe_parse_json = lambda text: [1, 2]
        with pytest.raises(ValueError, match="was not a JSON object"):
            self._design(architect, "写 main.py", _complexity())

    def test_feedback_is_appended_to_prompt(self):
        architect = _architect()
        captured = {}

        async def fake(prompt, system_prompt=""):
            captured["prompt"] = prompt
            return '{"file_plan": [{"path": "main.py"}]}'

        architect.call_llm = fake
        asyncio.run(
            architect.design_architecture(
                "写 main.py", _complexity(), feedback="依赖缺失"
            )
        )
        assert "依赖缺失" in captured["prompt"]

    def test_callback_uses_streaming_call(self):
        architect = _architect()
        seen = {}

        async def fake_tools(prompt, system_prompt, tools=None, enable_streaming_thinking=None, callback=None):
            seen["tools"] = tools
            return '{"file_plan": [{"path": "main.py"}]}'

        architect.call_llm_with_tools = fake_tools

        def cb(_chunk):
            return None

        result = asyncio.run(
            architect.design_architecture("写 main.py", _complexity(), callback=cb)
        )
        assert seen["tools"] == {}
        assert result["requirement"] == "写 main.py"

    def test_llm_exception_is_reraised(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            raise RuntimeError("gateway down")

        architect.call_llm = fake
        with pytest.raises(RuntimeError, match="gateway down"):
            self._design(architect, "写 main.py", _complexity())

    def test_missing_project_spec_gets_default(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return '{"file_plan": [{"path": "main.py"}]}'

        architect.call_llm = fake
        result = self._design(architect, "写 main.py", _complexity())
        assert result["project_spec"] == {"default": {"terminology": {}}}

    def test_file_languages_are_inferred(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return (
                '{"file_plan": ['
                '{"path": "src/Card.vue", "file_type": "frontend_component"},'
                '{"path": "app/api.py", "file_type": "api"}]}'
            )

        architect.call_llm = fake
        result = self._design(architect, "构建 Vue 前端和 Python 后端", _complexity())
        by_path = {entry["path"]: entry for entry in result["file_plan"]}
        assert by_path["src/Card.vue"]["language"] == "javascript"
        assert by_path["app/api.py"]["language"] == "python"

    def test_strict_paths_trim_file_plan(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return (
                '{"file_plan": ['
                '{"path": "main.py", "file_type": "entry"},'
                '{"path": "extra.py", "file_type": "utils"}]}'
            )

        architect.call_llm = fake
        result = self._design(architect, "只要 main.py 一个文件", _complexity())
        assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]

    def test_api_paths_get_leading_slash(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return (
                '{"api_spec": {"paths": {"items": {}}},'
                '"file_plan": [{"path": "main.py"}]}'
            )

        architect.call_llm = fake
        result = self._design(architect, "写 main.py", _complexity())
        assert list(result["api_spec"]["paths"]) == ["/items"]

    def test_non_dict_api_spec_and_db_schema_are_reset(self):
        architect = _architect()

        async def fake(prompt, system_prompt=""):
            return (
                '{"api_spec": "oops", "db_schema": 5,'
                '"file_plan": [{"path": "main.py"}]}'
            )

        architect.call_llm = fake
        result = self._design(architect, "写 main.py", _complexity())
        assert result["api_spec"] == {}
        assert result["db_schema"] == {}
