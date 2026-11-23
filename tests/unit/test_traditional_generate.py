import pytest

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


def test_strict_file_set_drops_unplanned_package_init():
    """冻结文件集生效时不得补出计划外的 src/__init__.py。"""
    from app.agent.orchestrator_generation.traditional_generate import (
        _filter_planned_integrity_fixes,
    )

    fixes = {"src/__init__.py": "", "main.py": "print('x')"}
    architecture = {
        "strict_file_paths": ["src/greeting.py", "main.py", "LICENSE", "MANIFEST.in", "README.md"],
    }

    assert _filter_planned_integrity_fixes(fixes, architecture) == {"main.py": "print('x')"}


def test_non_strict_plan_keeps_package_init_fix():
    """没有冻结契约时保留既有的包入口补充行为。"""
    from app.agent.orchestrator_generation.traditional_generate import (
        _filter_planned_integrity_fixes,
    )

    fixes = {"src/__init__.py": ""}
    architecture = {"file_plan": [{"path": "src/greeting.py", "file_type": "backend"}]}
    assert _filter_planned_integrity_fixes(fixes, architecture) == fixes
    assert _filter_planned_integrity_fixes(fixes, None) == fixes


@pytest.mark.asyncio
async def test_traditional_completeness_treats_empty_content_as_incomplete(tmp_path):
    from app.agent.orchestrator_generation.traditional_generate import (
        TraditionalGenerateMixin,
    )

    mixin = object.__new__(TraditionalGenerateMixin)
    completeness = await mixin._validate_project_completeness_traditional(
        [{"path": "main.py"}],
        {"main.py": "   \n"},
    )

    assert "main.py" in completeness["empty_files"]
    assert completeness["is_complete"] is False


@pytest.mark.asyncio
async def test_traditional_completeness_accepts_package_entry_and_short_files():
    from app.agent.orchestrator_generation.traditional_generate import (
        TraditionalGenerateMixin,
    )

    mixin = object.__new__(TraditionalGenerateMixin)
    completeness = await mixin._validate_project_completeness_traditional(
        [{"path": "app/__init__.py"}, {"path": "requirements.txt"}],
        {"app/__init__.py": "", "requirements.txt": "flask\n"},
    )

    assert completeness["empty_files"] == []
    assert completeness["is_complete"] is True


@pytest.mark.asyncio
async def test_traditional_completeness_still_flags_invalid_short_code():
    from app.agent.orchestrator_generation.traditional_generate import (
        TraditionalGenerateMixin,
    )

    mixin = object.__new__(TraditionalGenerateMixin)
    completeness = await mixin._validate_project_completeness_traditional(
        [{"path": "app/main.py"}],
        {"app/main.py": "pass"},
    )

    assert [f for f, _ in completeness["invalid_files"]] == ["app/main.py"]
    assert completeness["is_complete"] is False


def test_integrity_fixes_are_visible_to_subsequent_validation(tmp_path):
    """TG8: 补充的包入口文件必须同步进验证视图，否则沙箱/完整性检查看不到。"""
    from app.agent.orchestrator_generation.traditional_generate import (
        TraditionalGenerateMixin,
    )

    mixin = object.__new__(TraditionalGenerateMixin)
    mixin.output_dir = tmp_path
    mixin.generated_files = []

    generated_files = {"main.py": "print('hi')"}
    mixin._apply_integrity_fixes({"src/__init__.py": ""}, generated_files)

    assert generated_files["src/__init__.py"] == ""
    assert (tmp_path / "src" / "__init__.py").read_text(encoding="utf-8") == ""
    assert mixin.generated_files == [{
        "path": "src/__init__.py",
        "description": "自动补充的包初始化文件",
        "success": True,
        "size": 0,
    }]


@pytest.mark.asyncio
async def test_small_project_cancelled_error_diagnostics_and_rollback(tmp_path):
    """小项目路径：CancelledError（BaseException）须分诊为取消，不落 truthy 分支调 .get()。"""
    import asyncio as _asyncio

    from app.agent.orchestrator_files import FilesMixin

    mixin = object.__new__(FilesMixin)
    mixin.output_dir = tmp_path
    mixin.errors = []
    mixin.warnings = []
    mixin.generated_files = []
    mixin.cancel_event = None

    async def _gen(file_info, *_args, **_kwargs):
        if file_info["path"] == "b.py":
            raise _asyncio.CancelledError("检测到取消信号")
        return {"path": file_info["path"], "description": "ok", "success": True}

    mixin._generate_single_file = _gen
    mixin._friendly_error = lambda s: s

    plan = [{"path": "a.py"}, {"path": "b.py"}]
    (tmp_path / "a.py").write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError) as exc_info:
        await mixin._generate_files_small_project(plan, {}, 2)

    message = str(exc_info.value)
    assert "文件生成被取消: b.py" in message
    assert any("增量备份不可用" in w for w in mixin.warnings)
    assert mixin.generated_files == []
