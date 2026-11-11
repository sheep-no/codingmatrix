"""DependencyGraph 分支补测：路径校验、引用解析、去重/重构、持久化与源码解析。

补测暴露的真实缺陷：`_infer_file_description` 的规则链挂在 `elif` 上，
只要构造时传入语言适配器且文件不是包入口，`database/config/schema/core`
等规则全部被跳过，`add_missing_files` 自动补齐的文件描述恒为 `None`。
"""

import json

import pytest

from app.agent.adapters.python import PythonLanguageAdapter
from app.agent.dependency_graph import DependencyGraph


def _python_graph():
    return DependencyGraph(language_adapter=PythonLanguageAdapter())


class TestAddFileValidation:
    def test_empty_path_is_ignored(self):
        graph = DependencyGraph()
        graph.add_file("")
        assert graph.nodes == {}

    def test_path_with_space_or_special_chars_is_rejected(self):
        graph = DependencyGraph()
        for path in ("my file.py", "a,b.py", "a;b.py"):
            graph.add_file(path)
        assert graph.nodes == {}

    def test_bare_package_name_is_rejected_but_meta_files_kept(self):
        graph = DependencyGraph()
        graph.add_file("axios")
        graph.add_file("Dockerfile")
        graph.add_file("Makefile")
        assert "axios" not in graph.nodes
        assert "Dockerfile" in graph.nodes

    def test_backslashes_and_duplicate_slashes_are_normalized(self):
        graph = DependencyGraph()
        graph.add_file("app\\\\models//user.py")
        assert "app/models/user.py" in graph.nodes


class TestLooksLikeProjectFile:
    def test_reference_shapes(self):
        looks = DependencyGraph._looks_like_project_file
        assert looks("") is False
        assert looks("   ") is False
        assert looks("models/user.py") is True
        assert looks("main.py") is True
        assert looks("fastapi") is False


class TestResolveDependencyReference:
    def test_self_and_empty_references_do_not_resolve(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        assert graph._resolve_dependency_reference("a.py", "a.py") is None
        assert graph._resolve_dependency_reference("a.py", "") is None
        assert graph._resolve_dependency_reference("a.py", "./a.py") is None

    def test_exact_and_verbatim_match(self):
        graph = DependencyGraph()
        graph.add_file("app/models.py")
        assert graph._resolve_dependency_reference("x.py", "app/models.py") == "app/models.py"
        assert graph._resolve_dependency_reference("x.py", "./app/models.py") == "app/models.py"

    def test_ambiguous_filename_is_not_resolved(self):
        graph = DependencyGraph()
        graph.add_file("a/models.py")
        graph.add_file("b/models.py")
        assert graph._resolve_dependency_reference("x.py", "models.py") is None

    def test_segment_match_resolves_unique_module(self):
        graph = DependencyGraph()
        graph.add_file("app/models/user.py")
        assert graph._resolve_dependency_reference("x.py", "models/user") == "app/models/user.py"

    def test_verbatim_key_match_when_normalized_differs(self):
        graph = DependencyGraph()
        graph.add_file("./a.py")
        # 节点键保留前导 "./"，归一化后的 "a.py" 不在图中，但原引用命中。
        assert graph._resolve_dependency_reference("x.py", "./a.py") == "./a.py"

    def test_punctuation_only_reference_returns_none(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        assert graph._resolve_dependency_reference("a.py", "./") is None


class TestAddDependencyCycle:
    def test_reverse_edge_is_rejected_at_insert_time(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_dependency("a.py", "b.py")

        graph.add_dependency("b.py", "a.py")

        assert "a.py" not in graph.adjacency["b.py"]

    def test_duplicate_dependency_is_not_added_twice(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_dependency("a.py", "b.py")
        graph.add_dependency("a.py", "b.py")
        assert graph.nodes["a.py"].dependencies == ["b.py"]

    def test_self_dependency_is_ignored(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_dependency("a.py", "a.py")
        assert graph.adjacency["a.py"] == set()


class TestTransitiveDependents:
    def test_depth_limit_and_cycle_safety(self):
        graph = DependencyGraph()
        for name in ("a.py", "b.py", "c.py"):
            graph.add_file(name)
        graph.add_dependency("b.py", "a.py")
        graph.add_dependency("c.py", "b.py")

        # depth=0 只遍历直接下游，「b.py」本身在 depth=0 入队后仍会记录。
        assert graph._get_transitive_dependents("a.py", max_depth=0) == ["b.py"]
        assert graph._get_transitive_dependents("a.py", max_depth=1) == ["b.py", "c.py"]
        assert graph._get_transitive_dependents("a.py") == ["b.py", "c.py"]

    def test_skips_out_of_budget_depth(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_dependency("b.py", "a.py")
        assert graph._get_transitive_dependents("a.py", max_depth=-1) == []


class TestBuildFromSpecs:
    def test_openapi_paths_and_schemas_create_files(self):
        graph = DependencyGraph()
        specs = {
            "openapi": {
                "paths": {"/api/users/{id}": {"get": {}}, "/": {}},
                "components": {"schemas": {"UserProfile": {}}},
            }
        }
        graph.build_from_specs(specs)

        assert "app/api/api_users.py" in graph.nodes
        assert "app/services/api_users_service.py" in graph.nodes
        assert "app/models/user_profile.py" in graph.nodes
        assert "app/services/api_users_service.py" in graph.adjacency["app/api/api_users.py"]

    def test_specs_without_openapi_are_noop(self):
        graph = DependencyGraph()
        graph.build_from_specs({"other": "x"})
        assert graph.nodes == {}

    def test_openapi_object_with_content_attribute(self):
        class Spec:
            content = {"paths": {"/items": {}}, "components": {}}

        graph = DependencyGraph()
        graph.build_from_specs({"openapi": Spec()})
        assert "app/api/items.py" in graph.nodes


class TestBuildFromArchitectureValidation:
    def test_blank_and_invalid_paths_are_skipped(self):
        graph = DependencyGraph()
        architecture = {
            "file_plan": [
                {"path": ""},
                {"path": "bad path.py"},
                {"path": "bad,name.py"},
                {"path": "axios"},
                {"path": "Dockerfile"},
            ]
        }
        graph.build_from_architecture(architecture)

        assert set(graph.nodes) == {"Dockerfile"}

    def test_dotted_module_path_is_converted(self):
        graph = DependencyGraph()
        architecture = {"file_plan": [{"path": "app.models.user.py"}]}
        graph.build_from_architecture(architecture)

        assert "app/models/user.py" in graph.nodes
        assert architecture["file_plan"][0]["path"] == "app/models/user.py"

    def test_suspicious_dotted_path_is_left_unchanged(self):
        graph = DependencyGraph()
        architecture = {"file_plan": [{"path": "src.app.utils"}]}
        graph.build_from_architecture(architecture)

        assert "src.app.utils" in graph.nodes
        assert architecture["file_plan"][0]["path"] == "src.app.utils"

    def test_dotted_file_name_is_kept(self):
        graph = DependencyGraph()
        architecture = {"file_plan": [{"path": "vite.config.js"}]}
        graph.build_from_architecture(architecture)
        assert "vite.config.js" in graph.nodes

    def test_duplicate_paths_are_removed(self):
        graph = DependencyGraph()
        architecture = {
            "file_plan": [{"path": "a.py"}, {"path": "./a.py"}, {"path": "a.py"}]
        }
        graph.build_from_architecture(architecture)
        assert len(architecture["file_plan"]) == 1

    def test_utils_type_is_preserved_when_path_rules_cannot_refine(self):
        graph = DependencyGraph()
        architecture = {
            "file_plan": [{"path": "mystery.xyz", "file_type": "utils"}]
        }
        graph.build_from_architecture(architecture)
        assert graph.nodes["mystery.xyz"].file_type == "utils"

    def test_unknown_type_without_inference_is_recorded(self):
        graph = _python_graph()
        architecture = {"file_plan": [{"path": "mystery.xyz", "file_type": "unknown"}]}
        graph.build_from_architecture(architecture)
        assert graph.nodes["mystery.xyz"].file_type == "unknown"
        assert graph.get_unknown_type_files() == ["mystery.xyz"]

    def test_empty_path_entry_is_not_added(self):
        graph = DependencyGraph()
        architecture = {"file_plan": [{"path": "", "file_type": "utils"}]}
        graph.build_from_architecture(architecture)
        assert graph.nodes == {}

    def test_explicit_dependencies_and_imports_are_resolved(self):
        graph = _python_graph()
        architecture = {
            "file_plan": [
                {"path": "models.py", "file_type": "model"},
                {"path": "services.py", "file_type": "service"},
                {"path": "api.py", "file_type": "api"},
            ]
        }
        architecture["file_plan"][1]["dependencies"] = ["models.py"]
        architecture["file_plan"][2]["imports"] = ["app.services"]

        graph.build_from_architecture(architecture)

        assert "models.py" in graph.adjacency["services.py"]

    def test_update_file_type_ignores_unknown_and_missing(self):
        graph = DependencyGraph()
        graph.add_file("a.py", file_type="model")
        graph.update_file_type("a.py", "unknown")
        graph.update_file_type("missing.py", "model")
        assert graph.nodes["a.py"].file_type == "model"
        assert "missing.py" not in graph.nodes


class TestPathHelpers:
    def test_api_and_service_path_skip_parameters(self):
        graph = DependencyGraph()
        assert graph._path_to_api_file("/api/users/{id}") == "app/api/api_users.py"
        assert graph._path_to_service_file("/api/users/{id}") == "app/services/api_users_service.py"
        assert graph._path_to_api_file("/{id}") == ""
        assert graph._path_to_service_file("/{id}") == ""

    def test_camel_to_snake(self):
        graph = DependencyGraph()
        assert graph._camel_to_snake("UserProfile") == "user_profile"
        assert graph._camel_to_snake("HTTPServer") == "http_server"


class TestPersistence:
    def test_round_trip_dict_and_disk(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("a.py", file_type="model", priority=2, description="d")
        graph.add_file("b.py", file_type="api", priority=4)
        graph.add_dependency("b.py", "a.py")

        restored = DependencyGraph.from_dict(graph.to_dict())
        assert restored.nodes["a.py"].file_type == "model"
        assert restored.adjacency["b.py"] == {"a.py"}

        path = tmp_path / "graph.json"
        graph.save(str(path))
        loaded = DependencyGraph.load(str(path))
        assert loaded is not None
        assert set(loaded.nodes) == {"a.py", "b.py"}

    def test_load_missing_or_corrupt_file_returns_none(self, tmp_path):
        assert DependencyGraph.load(str(tmp_path / "absent.json")) is None
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert DependencyGraph.load(str(broken)) is None

    def test_to_dict_omits_empty_dependencies(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        assert graph.to_dict()["dependencies"] == {}


class TestDeduplicate:
    def test_higher_score_duplicate_wins_and_edges_redirect(self):
        graph = DependencyGraph()
        graph.add_file("models.py", file_type="model")
        graph.add_file("app/models/models.py", file_type="model")
        graph.add_file("consumer.py")
        graph.add_file("dep.py")
        graph.add_dependency("consumer.py", "models.py")
        graph.add_dependency("app/models/models.py", "dep.py")

        graph.deduplicate()

        assert "models.py" not in graph.nodes
        assert "app/models/models.py" in graph.nodes
        assert "app/models/models.py" in graph.adjacency["consumer.py"]
        assert "dep.py" in graph.adjacency["app/models/models.py"]

    def test_same_name_different_types_are_kept(self):
        graph = DependencyGraph()
        graph.add_file("models.py", file_type="model")
        graph.add_file("pkg/models.py", file_type="schema")
        graph.deduplicate()
        assert set(graph.nodes) == {"models.py", "pkg/models.py"}

    def test_package_init_files_are_not_deduplicated(self):
        graph = _python_graph()
        graph.add_file("a/__init__.py")
        graph.add_file("b/__init__.py")
        graph.deduplicate()
        assert set(graph.nodes) == {"a/__init__.py", "b/__init__.py"}

    def test_removed_node_out_edges_are_moved_to_winner(self):
        graph = DependencyGraph()
        graph.add_file("models.py", file_type="model")
        graph.add_file("app/models/models.py", file_type="model")
        graph.add_file("shared.py")
        graph.add_dependency("models.py", "shared.py")

        graph.deduplicate()

        assert "models.py" not in graph.nodes
        assert "shared.py" in graph.adjacency["app/models/models.py"]

    def test_unknown_and_double_unknown_duplicates_still_dedup(self):
        graph = DependencyGraph()
        graph.add_file("a/x.py", file_type="")
        graph.add_file("b/c/x.py", file_type="")
        graph.deduplicate()
        assert len(graph.nodes) == 1


class TestRefactorFile:
    def test_missing_old_path_returns_empty(self):
        assert DependencyGraph().refactor_file("ghost.py", [{"path": "x.py"}], {}) == []

    def test_edges_are_moved_to_new_files_with_mapping(self):
        graph = DependencyGraph()
        graph.add_file("old.py", file_type="service")
        graph.add_file("dep.py")
        graph.add_file("consumer.py")
        graph.add_dependency("old.py", "dep.py")
        graph.add_dependency("consumer.py", "old.py")

        new_paths = graph.refactor_file(
            "old.py",
            [{"path": "new.py", "file_type": "service"}],
            {"old.py": "new.py"},
        )

        assert new_paths == ["new.py"]
        assert "old.py" not in graph.nodes
        assert graph.adjacency["consumer.py"] == {"new.py"}
        assert graph.adjacency["new.py"] == {"dep.py"}

    def test_blank_new_paths_are_skipped(self):
        graph = DependencyGraph()
        graph.add_file("old.py")
        graph.add_file("consumer.py")
        graph.add_dependency("consumer.py", "old.py")
        assert graph.refactor_file("old.py", [{"path": ""}], {}) == []
        assert graph.adjacency["consumer.py"] == set()

    def test_dependent_removed_from_graph_is_skipped(self):
        graph = DependencyGraph()
        graph.add_file("old.py")
        graph.add_file("consumer.py")
        graph.add_dependency("consumer.py", "old.py")
        del graph.nodes["consumer.py"]

        assert graph.refactor_file("old.py", [{"path": "new.py"}], {}) == ["new.py"]

    def test_invalid_new_path_is_not_added(self):
        graph = DependencyGraph()
        graph.add_file("old.py")
        assert graph.refactor_file("old.py", [{"path": "bad path.py"}], {}) == []


class TestRemoveNode:
    def test_remove_cleans_edges_and_reports(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_dependency("b.py", "a.py")
        graph.unresolved_dependencies["a.py"].add("ghost.py")

        assert graph.remove_node("a.py") is True
        assert graph.remove_node("a.py") is False
        assert graph.adjacency["b.py"] == set()
        assert "a.py" not in graph.unresolved_dependencies


class TestInferHelpers:
    def test_priority_by_path_and_init(self):
        graph = DependencyGraph()
        assert graph._infer_file_priority("database.py") == 1
        assert graph._infer_file_priority("config.yaml") == 1
        assert graph._infer_file_priority("models.py") == 2
        assert graph._infer_file_priority("service.py") == 3
        assert graph._infer_file_priority("pkg/__init__.py") == 5

    def test_priority_init_with_adapter(self):
        graph = _python_graph()
        assert graph._infer_file_priority("pkg/__init__.py") == 5

    def test_description_rules_without_adapter(self):
        graph = DependencyGraph()
        assert graph._infer_file_description("database.py") == "数据库连接配置"
        assert graph._infer_file_description("config.py") == "配置文件"
        assert graph._infer_file_description("schema.py") == "数据模式定义"
        assert graph._infer_file_description("core.py") == "核心模块"
        assert graph._infer_file_description("misc.py") == "自动补充的模块文件"

    def test_description_rules_still_apply_with_adapter(self):
        graph = _python_graph()
        assert graph._infer_file_description("database.py") == "数据库连接配置"
        assert graph._infer_file_description("config.py") == "配置文件"
        assert graph._infer_file_description("schema.py") == "数据模式定义"
        assert graph._infer_file_description("core.py") == "核心模块"
        assert graph._infer_file_description("misc.py") == "自动补充的模块文件"
        assert graph._infer_file_description("pkg/__init__.py") == "pkg 包初始化文件"


class TestMissingFiles:
    def test_external_missing_file_is_skipped(self):
        graph = _python_graph()
        graph.add_file("main.py")
        graph.add_dependency("main.py", "fastapi.py")
        architecture = {"file_plan": [{"path": "main.py"}]}

        updated = graph.add_missing_files(architecture)

        assert {item["path"] for item in updated["file_plan"]} == {"main.py"}

    def test_no_missing_files_returns_same_architecture(self):
        graph = DependencyGraph()
        graph.add_file("main.py")
        architecture = {"file_plan": [{"path": "main.py"}]}
        assert graph.add_missing_files(architecture) is architecture

    def test_unresolved_reference_without_target_stays(self):
        graph = DependencyGraph()
        graph.add_file("main.py")
        graph.unresolved_dependencies["main.py"].add("ghost.py")
        graph._reprocess_unresolved_dependencies()
        assert graph.unresolved_dependencies["main.py"] == {"ghost.py"}

    def test_unresolved_reference_of_removed_dependent_is_dropped(self):
        graph = DependencyGraph()
        graph.unresolved_dependencies["gone.py"].add("ghost.py")
        graph._reprocess_unresolved_dependencies()
        assert "gone.py" not in graph.unresolved_dependencies


class TestProjectScanning:
    def test_python_imports_are_resolved(self, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg/__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pkg/models.py").write_text("class M: pass\n", encoding="utf-8")
        entry = tmp_path / "main.py"
        entry.write_text("from pkg.models import M\nimport pkg\n", encoding="utf-8")

        graph = DependencyGraph()
        deps = graph._parse_python_imports(entry, tmp_path)

        assert "pkg/models.py" in deps
        assert "pkg/__init__.py" in deps

    def test_python_import_parser_handles_unreadable_file(self, tmp_path):
        graph = DependencyGraph()
        assert graph._parse_python_imports(tmp_path / "nope.py", tmp_path) == []

    def test_js_import_parser_handles_unreadable_file(self, tmp_path):
        graph = DependencyGraph()
        assert graph._parse_js_requires(tmp_path / "nope.js", tmp_path) == []

    @pytest.mark.asyncio
    async def test_existing_project_report_counts(self, tmp_path):
        (tmp_path / "main.py").write_text("", encoding="utf-8")
        (tmp_path / "README.md").write_text("# 项目\n", encoding="utf-8")
        graph = DependencyGraph()

        result = await graph.build_from_existing_project(tmp_path)

        assert result["nodes"] == 2
        assert isinstance(result["order"], list)
        assert "shadow_dependencies" in result

    @pytest.mark.asyncio
    async def test_generic_file_content_failure_is_logged(self, tmp_path, monkeypatch):
        target = tmp_path / "script.txt"
        target.write_text("hello", encoding="utf-8")
        graph = DependencyGraph()

        def boom(self, path):
            raise OSError("unreadable")

        monkeypatch.setattr(
            "pathlib.Path.read_text", boom, raising=False
        )
        result = await graph.build_from_existing_project(tmp_path)
        assert result["nodes"] == 1


class TestExtractDependenciesFromContent:
    def test_python_content_matches_path_segments(self):
        graph = DependencyGraph()
        graph.add_file("app/models/user.py")
        graph.add_file("app/api/users.py")
        deps = graph.extract_dependencies_from_content(
            "app/api/users.py", "from app.models.user import User\n"
        )
        assert deps == ["app/models/user.py"]

    def test_js_relative_import(self):
        graph = DependencyGraph()
        graph.add_file("src/components/User.ts")
        graph.add_file("src/pages/Home.vue")
        deps = graph.extract_dependencies_from_content(
            "src/pages/Home.vue", 'import User from "../components/User";\n'
        )
        assert deps == ["src/components/User.ts"]

    def test_unknown_suffix_uses_generic_name_matching(self):
        graph = DependencyGraph()
        graph.add_file("src/main/java/Todo.java")
        graph.add_file("src/main/java/TodoController.java")
        deps = graph.extract_dependencies_from_content(
            "src/main/java/TodoController.java", "private Todo todo;"
        )
        assert deps == ["src/main/java/Todo.java"]

    def test_known_suffix_without_patterns_or_nodes(self):
        graph = DependencyGraph()
        assert graph.extract_dependencies_from_content("weird.xyz", "abc") == []

    def test_empty_content_returns_empty(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        assert graph.extract_dependencies_from_content("a.py", "") == []


class TestUpdateNodeDependencies:
    def test_replaces_dependencies_both_directions(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_file("c.py")
        graph.add_dependency("a.py", "b.py")
        graph.add_dependency("a.py", "old.py")
        graph.add_dependency("c.py", "a.py")

        graph.update_node_dependencies("a.py", ["b.py"])

        assert graph.adjacency["a.py"] == {"b.py"}
        assert graph.reverse_adjacency["a.py"] == {"c.py"}
        assert graph.nodes["a.py"].dependencies == ["b.py"]
        assert "a.py" not in graph.unresolved_dependencies


class TestContextPackage:
    def test_project_spec_is_injected_for_matching_type(self):
        graph = DependencyGraph()
        graph.add_file("models.py", file_type="model")
        spec = {
            "model": {
                "storage": {"type": "sqlite", "filename": "app.db"},
                "terminology": {"用户": "User"},
            }
        }
        package = graph.get_context_package_for_file("models.py", {}, project_spec=spec)
        assert "sqlite" in package["project_spec"]
        assert "app.db" in package["project_spec"]
        assert "用户=User" in package["project_spec"]

    def test_project_spec_without_storage_or_terminology_is_skipped(self):
        graph = DependencyGraph()
        graph.add_file("models.py", file_type="model")
        package = graph.get_context_package_for_file(
            "models.py", {}, project_spec={"model": {}}
        )
        assert "project_spec" not in package

    def test_core_dependency_reserves_majority_of_budget(self):
        graph = DependencyGraph()
        graph.add_file("main.py", priority=5)
        graph.add_file("core.py", priority=1)
        graph.add_file("other.py", priority=3)
        graph.add_dependency("main.py", "core.py")
        graph.add_dependency("main.py", "other.py")
        generated = {
            "core.py": "def core():\n    return 1\n",
            "other.py": "def other():\n    return 2\n",
        }

        package = graph.get_context_package_for_file(
            "main.py", generated, max_context_bytes=2000
        )

        assert len(package["dependencies"]) == 2
        assert all(item["path"] in generated for item in package["dependencies"])

    def test_context_renders_spec_and_dependency_sections(self):
        graph = DependencyGraph()
        graph.add_file("main.py", file_type="entry")
        graph.add_file("models.py", file_type="model")
        graph.add_dependency("main.py", "models.py")
        spec = {"entry": {"storage": {"type": "json"}}}
        context = graph.get_context_for_file(
            "main.py",
            {"models.py": "class User:\n    pass\n"},
            project_spec=spec,
        )
        assert "## 项目规范" in context
        assert "## 依赖文件: models.py" in context

    def test_context_without_dependencies_is_empty(self):
        graph = DependencyGraph()
        graph.add_file("main.py")
        assert graph.get_context_for_file("main.py", {}) == ""


class TestEnrich:
    def test_enrich_unknown_type_and_description(self, tmp_path):
        graph = _python_graph()
        graph.add_file("helper.py", file_type="")
        (tmp_path / "helper.py").write_text(
            '"""辅助工具模块。"""\n\ndef helper():\n    pass\n', encoding="utf-8"
        )

        changed = graph.enrich_from_source(tmp_path)

        assert changed is True
        assert graph.nodes["helper.py"].file_type == "utils"
        assert graph.nodes["helper.py"].description == "辅助工具模块。"

    def test_enrich_skips_existing_metadata_and_missing_files(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("keep.py", file_type="model", description="已有描述")
        (tmp_path / "keep.py").write_text("def f(): pass\n", encoding="utf-8")
        graph.add_file("gone.py")

        assert graph.enrich_from_source(tmp_path) is False

    def test_enrich_unknown_depended_only_by_entry_becomes_utils(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("entry.py", file_type="entry")
        graph.add_file("mystery.py", file_type="")
        graph.add_dependency("entry.py", "mystery.py")
        (tmp_path / "entry.py").write_text("", encoding="utf-8")
        (tmp_path / "mystery.py").write_text("", encoding="utf-8")

        assert graph.enrich_from_source(tmp_path) is True
        assert graph.nodes["mystery.py"].file_type == "utils"

    def test_enrich_and_save_writes_graph(self, tmp_path):
        graph = _python_graph()
        graph.add_file("helper.py", file_type="")
        (tmp_path / "helper.py").write_text("# 工具集\n", encoding="utf-8")

        assert graph.enrich_and_save(tmp_path) is True
        saved = json.loads((tmp_path / ".dep_graph.json").read_text(encoding="utf-8"))
        assert "helper.py" in saved["nodes"]

    def test_description_from_source_edge_cases(self, tmp_path):
        graph = DependencyGraph()

        empty = tmp_path / "empty.py"
        empty.write_text("", encoding="utf-8")
        assert graph._description_from_source(empty, "empty.py") == ""

        whitespace = tmp_path / "ws.py"
        whitespace.write_text("   \n", encoding="utf-8")
        assert graph._description_from_source(whitespace, "ws.py") == ""

        assert graph._description_from_source(tmp_path / "nope.py", "nope.py") == ""

    def test_description_from_comment_and_syntax_error(self, tmp_path):
        graph = DependencyGraph()
        comment = tmp_path / "comment.py"
        comment.write_text("# 业务逻辑入口\ndef broken(:\n", encoding="utf-8")
        assert graph._description_from_source(comment, "comment.py") == "业务逻辑入口"

        js = tmp_path / "app.js"
        js.write_text("// 前端入口\nexport const x = 1;\n", encoding="utf-8")
        assert graph._description_from_source(js, "app.js") == "前端入口"

    def test_python_module_docstring_returns_first_line(self):
        graph = DependencyGraph()
        assert graph._python_module_docstring('"""第一行。\n\n更多说明。"""\n') == "第一行。"
        assert graph._python_module_docstring("def broken(:\n") == ""

    def test_first_comment_line_variants(self):
        first = DependencyGraph._first_comment_line
        assert first("#!/usr/bin/env python\n# coding: utf-8\n# 真正的注释\n") == "真正的注释"
        assert first("//\n// 有效注释\n") == "有效注释"
        assert first("/* 块注释 */\n") == "块注释"
        assert first("code here\n# 后面的注释\n") == ""
        assert first("") == ""

    def test_exported_symbol_names_without_adapter_returns_empty(self):
        graph = DependencyGraph()
        assert graph._exported_symbol_names("def f(): pass\n") == []

    def test_exported_symbol_names_prefers_functions_and_classes(self):
        graph = _python_graph()
        names = graph._exported_symbol_names(
            "VALUE = 1\ndef helper():\n    pass\nclass Thing:\n    pass\n"
        )
        assert names[:2] == ["helper", "Thing"]

    def test_exported_symbol_names_swallows_adapter_errors(self, monkeypatch):
        graph = _python_graph()

        def boom(content):
            raise RuntimeError("boom")

        monkeypatch.setattr(graph.language_adapter, "extract_definitions", boom)
        assert graph._exported_symbol_names("x = 1") == []

    def test_enrich_unknown_type_uses_adapter_inference(self, tmp_path):
        graph = _python_graph()
        graph.add_file("app/models/user.py", file_type="")
        (tmp_path / "app/models").mkdir(parents=True)
        (tmp_path / "app/models/user.py").write_text("class User: pass\n", encoding="utf-8")

        assert graph.enrich_from_source(tmp_path) is True
        assert graph.nodes["app/models/user.py"].file_type == "model"

    def test_enrich_unknown_with_non_entry_dependents_stays_unknown(self, tmp_path):
        # 有语言适配器时未知扩展名保持 unknown，不会退化成 utils。
        graph = _python_graph()
        graph.add_file("service.py", file_type="service")
        graph.add_file("mystery.xyz", file_type="")
        graph.add_dependency("service.py", "mystery.xyz")
        (tmp_path / "service.py").write_text("", encoding="utf-8")
        (tmp_path / "mystery.xyz").write_text("", encoding="utf-8")

        assert graph.enrich_from_source(tmp_path) is False
        assert graph.nodes["mystery.xyz"].file_type == ""

    def test_enrich_unknown_without_dependents_stays_unknown(self):
        graph = _python_graph()
        graph.add_file("mystery.xyz", file_type="")
        assert graph._enrich_unknown_file_type("mystery.xyz", graph.nodes["mystery.xyz"]) is False

    def test_description_added_from_exported_symbols(self, tmp_path):
        graph = _python_graph()
        graph.add_file("helper.py", file_type="utils")
        target = tmp_path / "helper.py"
        target.write_text("def helper():\n    pass\n", encoding="utf-8")

        assert graph.enrich_from_source(tmp_path) is True
        assert graph.nodes["helper.py"].description == "定义 helper"

    def test_description_falls_back_to_inferred_name(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("core.py", file_type="core")
        (tmp_path / "core.py").write_text("x = 1\n", encoding="utf-8")

        assert graph.enrich_from_source(tmp_path) is True
        assert graph.nodes["core.py"].description == "核心模块"

    def test_enrich_empty_description_for_unsupported_suffix(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("data.bin")
        (tmp_path / "data.bin").write_bytes(b"\x00\x01")
        assert graph.enrich_from_source(tmp_path) is False

    def test_enrich_and_save_skips_write_when_unchanged(self, tmp_path):
        graph = DependencyGraph()
        graph.add_file("a.py", file_type="utils", description="已有")
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

        assert graph.enrich_and_save(tmp_path) is False
        assert not (tmp_path / ".dep_graph.json").exists()
