"""DependencyGraphValidator 剩余分支补测。"""

from types import SimpleNamespace

from app.agent.dependency_graph_validator import (
    DependencyGraphValidator,
    _heuristic_file_candidates,
    _is_invalid_file_path,
    _looks_like_project_dependency,
    _package_prefix,
)


class _Resolver:
    """按需返回解析结果的假语言适配器。"""

    def __init__(self, resolved=(), raises=False):
        self._resolved = list(resolved)
        self._raises = raises

    def resolve_import_to_file(self, import_info, file_path=""):
        if self._raises:
            raise RuntimeError("adapter boom")
        return list(self._resolved)


def _graph(nodes, adjacency=None):
    return SimpleNamespace(nodes={path: object() for path in nodes}, adjacency=adjacency or {})


def test_architecture_iteration_skips_non_dict_and_empty_dependency():
    graph = _graph({"src/main.py"})
    result = DependencyGraphValidator().validate_static(
        graph,
        architecture={
            "file_plan": [
                "not-a-dict",
                {"path": "src/main.py", "imports": ["", None]},
            ]
        },
    )
    assert result.passed is True


def test_dependency_satisfied_treats_empty_dependency_as_satisfied():
    validator = DependencyGraphValidator()
    assert validator._dependency_satisfied("", {"src/main.py"}) is True


def test_dependency_satisfied_uses_language_adapter_candidates():
    validator = DependencyGraphValidator(language_adapter=_Resolver(["src/config.py"]))
    assert validator._dependency_satisfied("src.config", {"src/config.py"}, "src/main.py") is True


def test_dependency_satisfied_skips_blank_and_duplicate_candidates():
    resolver = _Resolver(["", "src/config", "src/config.py"])
    validator = DependencyGraphValidator(language_adapter=resolver)
    assert validator._dependency_satisfied("src.config", {"src/config.py"}) is True


def test_dependency_satisfied_dedupes_adapter_candidates():
    resolver = _Resolver(["src/dup.py", "src/dup.py"])
    validator = DependencyGraphValidator(language_adapter=resolver)
    assert validator._dependency_satisfied("src.missing", {"src/main.py"}) is False


def test_dependency_satisfied_swallows_adapter_failure():
    validator = DependencyGraphValidator(language_adapter=_Resolver(raises=True))
    assert validator._dependency_satisfied("src.missing", {"src/main.py"}) is False


def test_invalid_path_rejects_blank_absolute_and_parent_components():
    assert _is_invalid_file_path("") is True
    assert _is_invalid_file_path("   ") is True
    assert _is_invalid_file_path("/etc/passwd") is True
    assert _is_invalid_file_path("~/secret.py") is True
    assert _is_invalid_file_path("src/../secret.py") is True
    assert _is_invalid_file_path("src/config.py") is False
    assert _is_invalid_file_path("foo.bar.xyz") is False


def test_heuristic_candidates_for_blank_dependency_is_empty():
    assert _heuristic_file_candidates("") == []


def test_package_prefix_handles_init_and_non_file_paths():
    assert _package_prefix("src/__init__.py") == "src"
    assert _package_prefix("src/config.py") == "src/config"
    assert _package_prefix("src/assets/") == "src/assets"


def test_looks_like_project_dependency_without_roots_falls_back_to_suffix():
    nodes = {"main.py"}
    assert _looks_like_project_dependency("", nodes) is False
    assert _looks_like_project_dependency("pkg/module.py", nodes) is True
    assert _looks_like_project_dependency("requests", nodes) is False


def test_looks_like_project_dependency_matches_project_roots():
    nodes = {"src/main.py"}
    assert _looks_like_project_dependency("src.config", nodes) is True
    assert _looks_like_project_dependency("external.pkg", nodes) is False
