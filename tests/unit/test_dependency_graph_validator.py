from types import SimpleNamespace

from app.agent.dependency_graph_validator import DependencyGraphValidator


def _validator():
    async def boom(*_args, **_kwargs):
        raise AssertionError("LLM should not be called")

    return DependencyGraphValidator(llm_caller=boom)


def test_validate_static_accepts_connected_graph():
    graph = SimpleNamespace(
        nodes={"main.py": object(), "app/routers.py": object()},
        adjacency={"main.py": ["app/routers.py"]},
    )
    result = _validator().validate_static(
        graph,
        architecture={"file_plan": [{"path": "main.py", "imports": ["app/routers.py"]}]},
    )
    assert result.passed is True
    assert result.issues == []


def test_validate_static_rejects_missing_and_dotted_paths():
    graph = SimpleNamespace(
        nodes={"main.py": object(), "app.database.py": object()},
        adjacency={"main.py": ["missing.py"]},
    )
    result = _validator().validate_static(graph)
    types = {issue.issue_type for issue in result.issues}
    assert result.passed is False
    assert "missing_dependency" in types
    assert "invalid_path" in types


def test_validate_static_rejects_empty_graph():
    result = _validator().validate_static(SimpleNamespace(nodes={}, adjacency={}))
    assert result.passed is False
    assert result.issues[0].issue_type == "invalid_path"


def test_validate_static_accepts_module_style_imports():
    graph = SimpleNamespace(
        nodes={
            "src/main.py": object(),
            "src/config.py": object(),
            "src/database.py": object(),
            "src/routers/user_router.py": object(),
            "src/models/user_model.py": object(),
        },
        adjacency={"src/main.py": ["src/config.py", "src/database.py"]},
    )
    result = _validator().validate_static(
        graph,
        architecture={
            "file_plan": [
                {
                    "path": "src/main.py",
                    "imports": ["src.config", "src.database", "src.routers", "fastapi"],
                },
                {
                    "path": "src/models/user_model.py",
                    "imports": ["src/config"],
                },
            ]
        },
    )
    assert result.passed is True
    assert result.issues == []


def test_validate_static_still_rejects_missing_project_module():
    graph = SimpleNamespace(
        nodes={"src/main.py": object(), "src/config.py": object()},
        adjacency={"src/main.py": ["src/config.py"]},
    )
    result = _validator().validate_static(
        graph,
        architecture={
            "file_plan": [
                {"path": "src/main.py", "imports": ["src.missing_service"]},
            ]
        },
    )
    assert result.passed is False
    assert any(issue.issue_type == "missing_dependency" for issue in result.issues)
