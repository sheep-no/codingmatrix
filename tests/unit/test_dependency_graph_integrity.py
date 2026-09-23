"""DependencyGraph 的完整性、引用解析与长链排序（DG3/DG4/DG8）。

回归的缺陷：
- add_dependency 对不在图中的依赖静默丢弃，导致 get_missing_files /
  validate_completeness / add_missing_files 全为死逻辑（DG3）；
- LLM 声明文件名式依赖（models.py）而非完整路径时边直接丢失（DG8）；
- _break_cycles 是纯递归 DFS，约 1000 层依赖链抛 RecursionError（DG4）。
"""

import pytest

from app.agent.dependency_graph import DependencyGraph


@pytest.fixture
def graph():
    return DependencyGraph()


class TestUnresolvedDependencies:
    def test_missing_project_file_is_reported(self, graph):
        graph.add_file("services/user_service.py")
        graph.add_dependency("services/user_service.py", "models/user.py")

        assert graph.get_missing_files() == ["models/user.py"]
        issues = graph.validate_completeness()
        assert len(issues) == 1
        assert issues[0]["type"] == "missing_dependency"
        assert issues[0]["file"] == "services/user_service.py"

    def test_external_package_is_not_reported_as_missing(self, graph):
        graph.add_file("main.py")
        graph.add_dependency("main.py", "fastapi")
        graph.add_dependency("main.py", "react")

        assert graph.get_missing_files() == []
        assert graph.validate_completeness() == []

    def test_update_node_dependencies_replaces_unresolved_refs(self, graph):
        graph.add_file("main.py")
        graph.add_dependency("main.py", "ghost.py")
        assert graph.get_missing_files() == ["ghost.py"]

        graph.add_file("utils.py")
        graph.update_node_dependencies("main.py", ["utils.py"])

        assert graph.get_missing_files() == []
        assert "utils.py" in graph.adjacency["main.py"]

    def test_removed_node_clears_unresolved_refs(self, graph):
        graph.add_file("main.py")
        graph.add_dependency("main.py", "ghost.py")

        graph.remove_node("main.py")

        assert graph.get_missing_files() == []

    def test_add_missing_files_rebuilds_edge(self, graph):
        graph.add_file("services/user_service.py")
        graph.add_dependency("services/user_service.py", "models/user.py")
        architecture = {
            "file_plan": [{"path": "services/user_service.py"}],
        }

        updated = graph.add_missing_files(architecture)

        assert "models/user.py" in {f["path"] for f in updated["file_plan"]}
        # 节点补齐后重新建边，不再重复报缺失
        assert "models/user.py" in graph.adjacency["services/user_service.py"]
        assert graph.get_missing_files() == []


class TestReferenceResolution:
    def test_filename_reference_resolves_to_unique_node(self, graph):
        graph.add_file("app/models/user.py")
        graph.add_dependency("app/services/user_service.py", "models/user.py")

        assert "app/models/user.py" in graph.adjacency["app/services/user_service.py"]
        assert graph.get_missing_files() == []

    def test_segment_reference_resolves_to_unique_node(self, graph):
        graph.add_file("app/models/user.py")
        graph.add_dependency("app/services/user_service.py", "models")

        assert "app/models/user.py" in graph.adjacency["app/services/user_service.py"]

    def test_ambiguous_filename_reference_is_not_guessed(self, graph):
        graph.add_file("a/models.py")
        graph.add_file("b/models.py")
        graph.add_dependency("app/services/user_service.py", "models.py")

        assert graph.adjacency["app/services/user_service.py"] == set()
        assert graph.get_missing_files() == ["models.py"]

    def test_exact_node_path_still_works(self, graph):
        graph.add_file("utils.py")
        graph.add_dependency("main.py", "utils.py")

        assert "utils.py" in graph.adjacency["main.py"]


class TestDeepChain:
    def test_long_chain_does_not_hit_recursion_limit(self, graph):
        depth = 1500
        for index in range(depth):
            graph.add_file(f"mod_{index}.py", priority=3)
        # 构造一条 1500 层的依赖链，旧递归 DFS 会 RecursionError
        for index in range(depth - 1):
            graph.add_dependency(f"mod_{index}.py", f"mod_{index + 1}.py")

        order = graph.get_generation_order()
        layers = graph.get_generation_layers()

        assert len(order) == depth
        assert sum(len(layer) for layer in layers) == depth
        # 链尾（无依赖）先生成
        assert order[0] == f"mod_{depth - 1}.py"

    def test_cycle_is_broken_iteratively(self, graph):
        graph.add_file("a.py")
        graph.add_file("b.py")
        # 直接构造环，绕过 add_dependency 的预防性环检测
        graph.adjacency["a.py"].add("b.py")
        graph.adjacency["b.py"].add("a.py")
        graph.reverse_adjacency["b.py"].add("a.py")
        graph.reverse_adjacency["a.py"].add("b.py")

        order = graph.get_generation_order()

        assert set(order) == {"a.py", "b.py"}
