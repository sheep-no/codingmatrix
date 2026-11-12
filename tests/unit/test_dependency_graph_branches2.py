"""DependencyGraph 第二轮分支补测：覆盖上下文预算、契约图、重建与持久化边界。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.adapters.python import PythonLanguageAdapter
from app.agent.dependency_graph import DependencyGraph


class _Adapter(PythonLanguageAdapter):
    def __init__(self, *, infer="unknown", resolve=(), signatures=None, raise_defs=False):
        self._infer = infer
        self._resolve = list(resolve)
        self._signatures = signatures
        self._raise_defs = raise_defs
        self.file_plan_data = None

    def infer_file_type(self, path):
        return self._infer

    def resolve_import_to_file(self, import_info, file_path=""):
        return list(self._resolve)

    def extract_signatures(self, content, path):
        return self._signatures

    def extract_definitions(self, content):
        if self._raise_defs:
            raise RuntimeError("boom")
        return {
            "hidden": SimpleNamespace(is_exported=False, symbol_type="function"),
            "CONST": SimpleNamespace(is_exported=True, symbol_type="variable"),
        }

    def set_file_plan_data(self, file_plan):
        self.file_plan_data = file_plan


def test_transitive_dependents_skips_origin_cycle():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.reverse_adjacency["a.py"].add("a.py")
    assert graph._get_transitive_dependents("a.py") == []


def test_build_from_architecture_without_file_plan_sets_adapter_data():
    adapter = _Adapter(infer="utils")
    graph = DependencyGraph(language_adapter=adapter)
    graph.build_from_architecture({})
    assert adapter.file_plan_data == []


def test_build_from_architecture_failure_after_cleanup_clears_plan(monkeypatch):
    from app.agent import dependency_graph as module
    from app.agent.generation_plan import GenerationPlan

    calls = {"count": 0}
    original = GenerationPlan.from_architecture

    def flaky(cls, architecture, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise ValueError("unfreezable")
        return original.__func__(cls, architecture, **kwargs)

    monkeypatch.setattr(GenerationPlan, "from_architecture", classmethod(flaky))
    graph = DependencyGraph()
    graph.build_from_architecture({"file_plan": [{"path": "a.py", "file_type": "model"}]})
    assert graph.generation_plan is None
    assert "a.py" in graph.nodes


def test_utils_declared_type_survives_unknown_inference():
    graph = DependencyGraph(language_adapter=_Adapter(infer="unknown"))
    graph.build_from_architecture(
        {"file_plan": [{"path": "mystery.xyz", "file_type": "utils"}]}
    )
    assert graph.nodes["mystery.xyz"].file_type == "utils"


def test_non_list_dependency_and_import_fields_are_ignored(monkeypatch):
    graph = DependencyGraph()
    monkeypatch.setattr(graph, "_auto_add_dependencies", lambda *a, **k: None)
    # 让计划冻结失败，保留原始 file_plan（字符串字段）以覆盖类型守卫。
    from app.agent.generation_plan import GenerationPlan

    monkeypatch.setattr(
        GenerationPlan, "from_architecture",
        classmethod(lambda cls, architecture, **kwargs: (_ for _ in ()).throw(ValueError("legacy"))),
    )
    graph.build_from_architecture(
        {
            "file_plan": [
                {"path": "a.py", "file_type": "utils"},
                {
                    "path": "b.py", "file_type": "utils",
                    "dependencies": "a.py", "imports": "a",
                },
                {"path": "c.py", "file_type": "utils", "dependencies": []},
            ]
        }
    )
    assert graph.adjacency["b.py"] == set()


def test_database_plan_ignores_non_list_imports_and_empty_import_entries(monkeypatch):
    graph = DependencyGraph()
    monkeypatch.setattr(graph, "_auto_add_dependencies", lambda *a, **k: None)
    from app.agent.generation_plan import GenerationPlan

    monkeypatch.setattr(
        GenerationPlan, "from_architecture",
        classmethod(lambda cls, architecture, **kwargs: (_ for _ in ()).throw(ValueError("legacy"))),
    )
    graph.build_from_architecture(
        {
            "file_plan": [
                {"path": "app/db.py", "file_type": "database", "imports": "app/models.py"},
                {"path": "app/models.py", "file_type": "model"},
                {"path": "app/other.py", "file_type": "utils", "imports": ["", "app/other.py"]},
            ]
        }
    )
    assert graph.adjacency["app/db.py"] == set()


def test_contract_graph_reuses_existing_layer_edges():
    def plan():
        return [
            {
                "path": "app/db.py", "file_type": "database",
                "dependencies": ["app/models.py"],
                "contract": {"required_imports": []},
            },
            {"path": "app/models.py", "file_type": "model"},
            {"path": "app/schemas.py", "file_type": "schema"},
            {"path": "app/repository.py", "file_type": "repository"},
            {"path": "app/entry.py", "file_type": "entry"},
        ]

    graph = DependencyGraph()
    for entry in plan():
        graph.add_file(entry["path"], file_type=entry["file_type"])
    graph.add_dependency("app/entry.py", "app/repository.py")
    graph.add_dependency("app/db.py", "app/models.py")
    graph.add_dependency("app/schemas.py", "app/models.py")
    graph.add_dependency("app/repository.py", "app/schemas.py")

    graph.build_from_architecture({"file_plan": plan()})

    assert "app/repository.py" in graph.adjacency["app/entry.py"]
    assert "app/models.py" not in graph.adjacency["app/db.py"]
    assert "app/models.py" not in graph.nodes["app/db.py"].dependencies
    assert "app/models.py" in graph.adjacency["app/schemas.py"]
    assert "app/schemas.py" in graph.adjacency["app/repository.py"]


def test_contract_graph_cleans_database_edge_seeded_before_build():
    graph = DependencyGraph()
    graph.add_file("app/db.py", file_type="database")
    graph.add_file("app/models.py", file_type="model")
    graph.add_dependency("app/db.py", "app/models.py")

    graph.build_from_architecture(
        {
            "file_plan": [
                {
                    "path": "app/models.py", "file_type": "model",
                    "contract": {"required_imports": []},
                },
                {"path": "app/entry.py", "file_type": "entry"},
            ]
        }
    )

    assert "app/models.py" not in graph.adjacency["app/db.py"]
    assert graph.nodes["app/db.py"].dependencies == []


def test_build_from_specs_skips_empty_service_path(monkeypatch):
    graph = DependencyGraph()
    monkeypatch.setattr(graph, "_path_to_service_file", lambda path: "")
    graph.build_from_specs({"openapi": {"paths": {"/items": {}}, "components": {}}})
    assert "app/api/items.py" in graph.nodes


def test_break_cycles_removes_dependency_list_entry():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    for source, target in (("a.py", "b.py"), ("b.py", "a.py")):
        graph.adjacency[source].add(target)
        graph.reverse_adjacency[target].add(source)
        graph.nodes[source].dependencies.append(target)

    graph.get_generation_order()

    remaining = set(graph.nodes["a.py"].dependencies) | set(graph.nodes["b.py"].dependencies)
    assert remaining == {"b.py"} or remaining == {"a.py"}


def test_generation_layers_ignores_missing_adjacency_dependency():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.adjacency["a.py"].add("ghost.py")
    assert graph.get_generation_layers() == [["a.py"]]


def test_context_package_skips_spec_without_storage_or_terminology():
    graph = DependencyGraph()
    graph.add_file("models.py", file_type="model")
    package = graph.get_context_package_for_file(
        "models.py", {}, project_spec={"model": {"misc": "value"}}
    )
    assert "project_spec" not in package


def test_dependency_summary_skips_nodes_without_dependencies():
    graph = DependencyGraph()
    graph.add_file("lonely.py")
    graph.adjacency["lonely.py"]
    assert graph.get_dependency_summary() == {}


def test_self_and_empty_explicit_dependencies_are_skipped():
    graph = DependencyGraph()
    graph.build_from_architecture(
        {
            "file_plan": [
                {"path": "a.py", "file_type": "model", "dependencies": ["", "a.py"]},
            ]
        }
    )
    assert graph.adjacency["a.py"] == set()


def _contract_architecture():
    return {
        "file_plan": [
            {
                "path": "app/db.py", "file_type": "database",
                "contract": {"required_imports": ["external"]},
            },
            {"path": "app/models.py", "file_type": "model"},
            {"path": "app/schemas.py", "file_type": "schema"},
            {"path": "app/repository.py", "file_type": "repository"},
            {"path": "app/entry.py", "file_type": "entry"},
            {"path": "tests/test_app.py", "file_type": "test"},
        ]
    }


def test_contract_driven_graph_normalises_layering():
    graph = DependencyGraph()
    architecture = _contract_architecture()
    graph.build_from_architecture(architecture)

    # entry 消费 repository，schema 依赖 model，repository 依赖 schema。
    assert "app/repository.py" in graph.adjacency["app/entry.py"]
    assert "app/models.py" in graph.adjacency["app/schemas.py"]
    assert "app/schemas.py" in graph.adjacency["app/repository.py"]
    assert "app/db.py" in graph.adjacency["app/models.py"]
    assert "app/models.py" not in graph.adjacency["app/db.py"]


def test_contract_driven_graph_is_idempotent():
    graph = DependencyGraph()
    architecture = _contract_architecture()
    graph.build_from_architecture(architecture)
    first = {path: set(deps) for path, deps in graph.adjacency.items()}
    graph._auto_add_dependencies(set(), use_legacy_rules=True)
    assert {path: set(deps) for path, deps in graph.adjacency.items()}
    assert first["app/entry.py"] <= graph.adjacency["app/entry.py"]


def test_contract_driven_graph_removes_database_to_model_edge():
    graph = DependencyGraph()
    graph.build_from_architecture(
        {
            "file_plan": [
                {
                    "path": "app/db.py", "file_type": "database",
                    "dependencies": ["app/models.py"],
                },
                {"path": "app/models.py", "file_type": "model"},
            ]
        }
    )

    assert "app/models.py" not in graph.adjacency["app/db.py"]
    assert "app/models.py" not in graph.nodes["app/db.py"].dependencies
    assert "app/db.py" in graph.adjacency["app/models.py"]


def test_deduplicate_skips_missing_dependents_and_out_edges():
    graph = DependencyGraph()
    graph.add_file("models.py", file_type="model")
    graph.add_file("pkg/models.py", file_type="model")
    graph.reverse_adjacency["models.py"].add("ghost.py")
    graph.adjacency["models.py"].add("ghost.py")
    graph.reverse_adjacency["pkg/models.py"].add("ghost.py")
    graph.adjacency["pkg/models.py"].add("ghost.py")
    graph.deduplicate()
    assert set(graph.nodes) == {"pkg/models.py"}


def test_refactor_mapping_missing_targets_and_skipped_keys():
    graph = DependencyGraph()
    graph.add_file("old.py", file_type="service")
    graph.add_file("dep.py")
    graph.add_file("consumer.py")
    graph.add_dependency("old.py", "dep.py")
    graph.add_dependency("consumer.py", "old.py")

    new_paths = graph.refactor_file(
        "old.py",
        [{"path": "new.py", "file_type": "service"}],
        {"old.py": "ghost.py", "unrelated": "dep.py", "dep.py": "missing.py"},
    )

    assert new_paths == ["new.py"]
    assert graph.adjacency["consumer.py"] == {"new.py"}
    assert graph.adjacency["new.py"] == set()


def test_remove_node_with_partial_bookkeeping():
    graph = DependencyGraph()
    graph.adjacency["ghost.py"].add("x.py")
    graph._remove_node("ghost.py")
    assert "ghost.py" not in graph.adjacency

    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.reverse_adjacency["a.py"].add("missing.py")
    graph._remove_node("a.py")
    assert "a.py" not in graph.nodes


def test_is_external_plan_path_rejects_blank_with_adapter():
    graph = DependencyGraph(language_adapter=_Adapter())
    assert graph._is_external_plan_path("/") is False


def test_import_to_file_path_resolves_candidate_and_basename():
    graph = DependencyGraph(language_adapter=_Adapter(resolve=["app/models.py"]))
    graph.add_file("app/models.py")
    assert graph._import_to_file_path("anything") == "app/models.py"

    graph = DependencyGraph(language_adapter=_Adapter(resolve=["missing.py"]))
    graph.add_file("flattened/models.py")
    assert graph._import_to_file_path("app.models") == "flattened/models.py"


def test_import_to_file_path_without_adapter_resolves_init_and_module():
    graph = DependencyGraph()
    graph.add_file("pkg/__init__.py")
    assert graph._import_to_file_path("pkg") == "pkg/__init__.py"

    graph = DependencyGraph()
    graph.add_file("pkg/models.py")
    assert graph._import_to_file_path("pkg.models") == "pkg/models.py"
    assert graph._import_to_file_path("pkg.missing") is None


def test_build_from_specs_skips_parameter_only_paths():
    graph = DependencyGraph()
    graph.build_from_specs({"openapi": {"paths": {"/{id}": {}}, "components": {}}})
    assert graph.nodes == {}


def test_build_from_specs_adds_service_for_api_path():
    graph = DependencyGraph()
    graph.build_from_specs({"openapi": {"paths": {"/items": {}}, "components": {}}})
    assert "app/services/items_service.py" in graph.nodes
    assert "app/services/items_service.py" in graph.adjacency["app/api/items.py"]


def test_auto_add_dependencies_replaces_reverse_edge_and_skips_self():
    graph = DependencyGraph()
    graph.add_file("service.py", file_type="service")
    graph.add_file("models.py", file_type="model")
    graph.add_dependency("models.py", "service.py")

    graph._auto_add_dependencies(set())

    assert "models.py" in graph.adjacency["service.py"]
    assert "service.py" not in graph.adjacency["models.py"]


def test_auto_add_dependencies_refuses_cycle():
    graph = DependencyGraph()
    graph.add_file("service.py", file_type="service")
    graph.add_file("models.py", file_type="model")
    graph.add_file("utils.py", file_type="utils")
    graph.add_dependency("models.py", "utils.py")
    graph.add_dependency("utils.py", "service.py")

    graph._auto_add_dependencies(set())

    assert "models.py" not in graph.adjacency["service.py"]


def test_generation_order_handles_missing_dependencies_and_cycles(monkeypatch):
    graph = DependencyGraph()
    graph.add_file("a.py", priority=1)
    graph.adjacency["a.py"].add("ghost.py")
    graph.reverse_adjacency["a.py"].add("ghost.py")
    graph.add_file("b.py", priority=2)
    graph.add_dependency("b.py", "a.py")

    assert graph.get_generation_order() == ["a.py", "b.py"]

    graph.adjacency["a.py"].add("b.py")
    graph.reverse_adjacency["b.py"].add("a.py")
    monkeypatch.setattr(graph, "_break_cycles", lambda: None)
    order = graph.get_generation_order()
    assert set(order) == {"a.py", "b.py"}


def test_break_cycles_ignores_missing_neighbors_and_partial_edges():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.adjacency["a.py"].update({"b.py", "ghost.py"})
    graph.reverse_adjacency["b.py"].add("a.py")
    graph.adjacency["b.py"].add("a.py")
    graph.reverse_adjacency["a.py"].add("b.py")
    graph._break_cycles()
    assert set(graph.nodes) == {"a.py", "b.py"}


def test_generation_layers_ignores_missing_dependents():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.add_dependency("b.py", "a.py")
    graph.reverse_adjacency["a.py"].add("ghost.py")
    assert graph.get_generation_layers() == [["a.py"], ["b.py"]]


def test_context_package_handles_unknown_dependency_and_budget_exhaustion():
    graph = DependencyGraph()
    graph.add_file("main.py", priority=5)
    graph.generation_plan = None
    generated = {"ghost.py": "def ghost():\n    pass\n" * 200}
    package = graph.get_context_package_for_file("main.py", generated, max_context_bytes=300)
    assert package["dependencies"] == []

    graph.add_file("dep.py", priority=5)
    graph.adjacency["main.py"].add("dep.py")
    generated = {"dep.py": "def dep():\n    pass\n" * 400}
    package = graph.get_context_package_for_file("main.py", generated, max_context_bytes=300)
    assert package["dependencies"][0]["truncated"] is True


def test_context_package_renders_terminology_without_storage():
    graph = DependencyGraph()
    graph.add_file("models.py", file_type="model")
    package = graph.get_context_package_for_file(
        "models.py", {}, project_spec={"model": {"terminology": {"用户": "User"}}}
    )
    assert "术语表: 用户=User" in package["project_spec"]
    assert "存储方式" not in package["project_spec"]


def test_context_package_uses_adapter_signatures():
    adapter = _Adapter(signatures="def custom(): ...")
    graph = DependencyGraph(language_adapter=adapter)
    graph.add_file("main.py")
    graph.add_file("dep.py")
    graph.add_dependency("main.py", "dep.py")
    package = graph.get_context_package_for_file(
        "main.py", {"dep.py": "def dep(): ...\n"}, max_context_bytes=5000
    )
    assert package["dependencies"][0]["signatures"] == "def custom(): ..."


def test_context_renders_sections_with_empty_parts():
    graph = DependencyGraph()
    graph.add_file("main.py", file_type="entry")
    graph.add_file("dep.py", file_type="model")
    graph.add_dependency("main.py", "dep.py")
    context = graph.get_context_for_file(
        "main.py",
        {"dep.py": ""},
        project_spec={"entry": {"storage": {"type": "json"}, "terminology": {}}},
    )
    assert "## 项目规范" in context
    assert "suffix" not in context

    package = graph.get_context_package_for_file(
        "main.py", {"dep.py": ""}, max_context_bytes=2000
    )
    assert package["dependencies"][0]["signatures"] == ""


def test_dependency_summary_lists_non_empty_edges():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.add_dependency("b.py", "a.py")
    assert graph.get_dependency_summary() == {"b.py": ["a.py"]}


def test_build_graph_skips_empty_generic_content_and_collects_generic(tmp_path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / "main.java").write_text("class Main { Todo todo; }", encoding="utf-8")
    (tmp_path / "Todo.java").write_text("class Todo {}", encoding="utf-8")
    graph = DependencyGraph()
    result = graph._build_graph_from_project(tmp_path)
    assert result["nodes"] == 3


def test_enrich_unknown_to_utils_and_read_errors(tmp_path):
    graph = DependencyGraph()
    graph.add_file("entry.py", file_type="entry")
    graph.add_file("mystery.xyz", file_type="")
    graph.add_dependency("entry.py", "mystery.xyz")
    (tmp_path / "entry.py").write_text("", encoding="utf-8")
    (tmp_path / "mystery.xyz").write_text("", encoding="utf-8")
    assert graph.enrich_from_source(tmp_path) is True
    assert graph.nodes["mystery.xyz"].file_type == "utils"

    graph = DependencyGraph()
    graph.add_file("big.py", file_type="model")
    (tmp_path / "big.py").write_text("# " + "x" * (graph._MAX_ENRICH_BYTES + 10), encoding="utf-8")
    assert graph._description_from_source(tmp_path / "big.py", "big.py") == "x" * 200


def test_enrich_unknown_with_adapter_falls_back_to_entry_dependents(tmp_path):
    graph = DependencyGraph(language_adapter=_Adapter(infer="unknown"))
    graph.add_file("entry.py", file_type="entry")
    graph.add_file("mystery.xyz", file_type="")
    graph.add_dependency("entry.py", "mystery.xyz")
    (tmp_path / "entry.py").write_text("", encoding="utf-8")
    (tmp_path / "mystery.xyz").write_text("", encoding="utf-8")

    assert graph.enrich_from_source(tmp_path) is True
    assert graph.nodes["mystery.xyz"].file_type == "utils"


def test_description_from_source_skips_unreadable_file(tmp_path, monkeypatch):
    target = tmp_path / "file.py"
    target.write_text("x = 1\n", encoding="utf-8")
    graph = DependencyGraph()

    def boom(*args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_text", boom)
    assert graph._description_from_source(target, "file.py") == ""


def test_exported_symbol_names_skips_non_exported():
    graph = DependencyGraph(language_adapter=_Adapter())
    assert graph._exported_symbol_names("CONST = 1") == ["CONST"]


def test_first_comment_line_handles_empty_comment_bodies():
    first = DependencyGraph._first_comment_line
    assert first("#\n# value\n") == "value"
    assert first("//\n// value\n") == "value"
    assert first("/*\n*/\ncode\n") == ""
    assert first("\n\n") == ""


def test_resolve_js_import_aliases_and_escapes(tmp_path):
    graph = DependencyGraph()
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "src" / "components" / "User.ts").write_text("export {}\n", encoding="utf-8")
    file_path = tmp_path / "src" / "pages" / "Home.vue"
    file_path.parent.mkdir()

    assert graph._resolve_js_import("@/components/User", file_path, tmp_path) == "src/components/User.ts"
    assert graph._resolve_js_import("../../outside", file_path, tmp_path) is None
    assert graph._resolve_js_import("../../../outside", file_path, tmp_path) is None
    assert graph._resolve_js_import("missing/Thing", file_path, tmp_path) is None


def test_update_node_dependencies_for_missing_node():
    graph = DependencyGraph()
    graph.add_file("dep.py")
    graph.update_node_dependencies("ghost.py", ["dep.py"])
    assert graph.adjacency["ghost.py"] == {"dep.py"}


def test_validate_and_missing_files_report_unknown_deps():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.adjacency["a.py"].add("ghost.py")
    graph.unresolved_dependencies["a.py"].add("shadow.py")
    issues = graph.validate_completeness()
    assert {issue["type"] for issue in issues} == {"missing_dependency"}
    assert set(graph.get_missing_files()) == {"ghost.py", "shadow.py"}

    healthy = DependencyGraph()
    healthy.add_file("a.py")
    healthy.add_file("b.py")
    healthy.add_dependency("a.py", "b.py")
    assert healthy.validate_completeness() == []


def test_add_missing_files_skips_already_planned():
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.unresolved_dependencies["main.py"].add("extra.py")
    architecture = {"file_plan": [{"path": "extra.py"}]}
    updated = graph.add_missing_files(architecture)
    assert [item["path"] for item in updated["file_plan"]] == ["extra.py"]
    assert "extra.py" not in graph.nodes


def test_reprocess_drops_removed_dependent_and_existing_edges():
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.add_dependency("a.py", "b.py")
    graph.unresolved_dependencies["a.py"].add("b.py")
    graph.unresolved_dependencies["ghost.py"].add("a.py")
    graph._reprocess_unresolved_dependencies()
    assert "a.py" not in graph.unresolved_dependencies
    assert "ghost.py" not in graph.unresolved_dependencies
    assert graph.nodes["a.py"].dependencies == ["b.py"]


def test_file_priority_falls_back_to_three():
    graph = DependencyGraph()
    assert graph._infer_file_priority("main.py") == 3


def test_infer_file_priority_adapter_without_init_suffix():
    graph = DependencyGraph(language_adapter=_Adapter())
    assert graph._infer_file_priority("main.py") == 3


def test_would_create_cycle_skips_revisited_nodes():
    graph = DependencyGraph()
    for path in ("a.py", "b.py", "c.py"):
        graph.add_file(path)
    graph.adjacency["b.py"].update({"c.py", "d.py"})
    graph.adjacency["c.py"].add("b.py")
    graph.nodes["a.py"]  # keep node
    # b -> c -> b 的环在 visited 命中处返回 False，不会误判 a 依赖 b 成环。
    assert graph._would_create_cycle("d.py", "b.py") is False


def test_break_cycles_removes_edge_and_cleans_dependencies():
    graph = DependencyGraph()
    for path in ("a.py", "b.py"):
        graph.add_file(path)
    graph.add_dependency("b.py", "a.py")
    graph.adjacency["a.py"].add("b.py")
    graph.reverse_adjacency["b.py"].add("a.py")

    graph._break_cycles()

    assert not ({"b.py"} <= graph.adjacency["a.py"] and {"a.py"} <= graph.adjacency["b.py"])


def test_generation_layers_falls_back_when_no_zero_indegree():
    graph = DependencyGraph()
    for path in ("a.py", "b.py"):
        graph.add_file(path)
    graph._break_cycles = lambda: None
    graph.adjacency["a.py"].add("b.py")
    graph.adjacency["b.py"].add("a.py")
    graph.reverse_adjacency["a.py"].add("b.py")
    graph.reverse_adjacency["b.py"].add("a.py")

    layers = graph.get_generation_layers()

    assert sorted(path for layer in layers for path in layer) == ["a.py", "b.py"]


def test_refactor_skips_new_node_removed_by_validation(monkeypatch):
    graph = DependencyGraph()
    graph.add_file("old.py", file_type="service")
    graph.add_file("dep.py")
    graph.add_dependency("old.py", "dep.py")

    original_add = graph.add_file

    def add_without_target(path, **kwargs):
        if path == "new.py":
            return
        original_add(path, **kwargs)

    monkeypatch.setattr(graph, "add_file", add_without_target)
    assert graph.refactor_file("old.py", [{"path": "new.py"}], {}) == []


def test_build_from_architecture_skips_blank_paths_in_second_pass():
    graph = DependencyGraph()
    graph.build_from_architecture(
        {"file_plan": [{"path": "a.py", "file_type": "utils"}, {"path": ""}]}
    )
    assert set(graph.nodes) == {"a.py"}


def test_build_graph_records_generic_dependencies(tmp_path):
    (tmp_path / "Todo.java").write_text("class Todo {}", encoding="utf-8")
    (tmp_path / "Controller.java").write_text("class Controller { Todo t; }", encoding="utf-8")
    graph = DependencyGraph()
    result = graph._build_graph_from_project(tmp_path)
    assert "Todo.java" in graph.adjacency["Controller.java"]
    assert result["edges"] >= 1
