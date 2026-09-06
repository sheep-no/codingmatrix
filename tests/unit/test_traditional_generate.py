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
