"""Branch coverage for the orchestration flows in orchestrator_files.FilesMixin."""

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from app.agent import code_patcher
from app.agent import orchestrator_files as of
from app.agent.code_patcher import CrossFilePatchResult, PatchResult
from app.agent.dependency_graph import DependencyGraph


class _Orchestrator(of.FilesMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.dependency_graph_obj = None
        self.cross_file_patcher = None
        self.feedback_learner = None
        self.cancel_event = None
        self._generated_contents = {}
        self.callback = None
        self.api_key_token = None
        self.require_approval = False
        self.enable_validation = False
        self.enable_review = False
        self.enable_error_recovery = False
        self.validator = None
        self.reviewer = None
        self.error_recovery = None
        self.api_contract_checker = None
        self.model_assignment = None
        self.progress = []

    def _select_engineer(self, _file_path):
        async def generate_file(*_args, **_kwargs):
            return "def main():\n    return 1\n"

        return types.SimpleNamespace(
            name="测试工程师",
            clear_edits=lambda: None,
            generate_file=generate_file,
        )

    def _select_model_for_file(self, _file_path):
        return "test-model"

    def _is_frontend_file(self, _file_path):
        return False

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))

    def _report_thinking(self, *_args, **_kwargs):
        return None

    def _report_file_event(self, *_args, **_kwargs):
        return None

    def _report_warning(self, **_kwargs):
        return None

    def _should_check_api_consistency(self, _file_path):
        return False

    async def _check_and_report_api_issues(self, _file_path, _content):
        return None

    async def _wait_for_approval(self, _file_path):
        return getattr(self, "approval_result", False)

    def _report_file_rejected(self, **_kwargs):
        self.rejected = _kwargs


def _success_result(path: str) -> dict:
    return {"path": path, "description": "d", "success": True, "size": 10}


@pytest.fixture
def extract_passthrough(monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(of, "extract_engineer_content", extract_content)


@pytest.mark.asyncio
async def test_small_project_generation_success_drops_stash(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    stash_calls = []
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: stash_calls.append("push") or True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: stash_calls.append("drop") or True)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: stash_calls.append("pop") or True)

    async def generate(file_info, *_args, **_kwargs):
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_small_project(
        [{"path": "main.py", "description": "entry"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert stash_calls == ["push", "drop"]
    assert orchestrator.generated_files == [_success_result("main.py")]


@pytest.mark.asyncio
async def test_small_project_warns_when_stash_unavailable(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: False)

    async def generate(file_info, *_args, **_kwargs):
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_small_project(
        [{"path": "main.py", "description": "entry"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert any("增量备份不可用" in warning for warning in orchestrator.warnings)


@pytest.mark.asyncio
async def test_small_project_returns_early_when_cancelled(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.cancel_event = types.SimpleNamespace(is_set=lambda: True)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)

    await orchestrator._generate_files_small_project(
        [{"path": "main.py", "description": "entry"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_small_project_second_batch_cancelled(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    calls = {"n": 0}

    def is_set():
        calls["n"] += 1
        return calls["n"] > 1

    orchestrator.cancel_event = types.SimpleNamespace(is_set=is_set)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)
    plan = [{"path": f"f{i}.py", "description": "d"} for i in range(25)]

    await orchestrator._generate_files_small_project(
        plan, {"architecture": {"language": "python"}}, len(plan)
    )

    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_small_project_triages_cancelled_and_exception_results(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        if file_info["path"] == "cancel.py":
            raise asyncio.CancelledError()
        if file_info["path"] == "boom.py":
            raise ValueError("boom")
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)
    plan = [
        {"path": "cancel.py", "description": "d"},
        {"path": "boom.py", "description": "d"},
        {"path": "main.py", "description": "d"},
    ]

    with pytest.raises(RuntimeError, match="small project file generation failed"):
        await orchestrator._generate_files_small_project(
            plan, {"architecture": {"language": "python"}}, len(plan)
        )

    assert any("文件生成被取消: cancel.py" in error for error in orchestrator.errors)
    assert any("内部异常" in error for error in orchestrator.errors)


@pytest.mark.asyncio
async def test_small_project_rolls_back_new_files_on_failure(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: True)

    async def generate(*_args, **_kwargs):
        (tmp_path / "new.py").write_text("x", encoding="utf-8")
        return {"path": "new.py", "success": False}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    with pytest.raises(RuntimeError):
        await orchestrator._generate_files_small_project(
            [{"path": "new.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            1,
        )

    assert not (tmp_path / "new.py").exists()
    assert any("已回滚" in warning for warning in orchestrator.warnings)


@pytest.mark.asyncio
async def test_dep_layers_breaks_on_cancel_and_skips_unknown_files(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    graph = DependencyGraph()
    graph.add_file("main.py")
    orchestrator.dependency_graph_obj = graph
    orchestrator.cancel_event = types.SimpleNamespace(is_set=lambda: True)

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "unknown.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        graph,
    )

    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_dep_layers_skips_empty_layer(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["not-in-plan.py"]]

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_dep_layers_success_records_content_and_warns_when_no_stash(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["main.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: False)

    async def generate(file_info, *_args, **_kwargs):
        path = file_info["path"]
        (tmp_path / path).write_text("def main():\n    return 1\n", encoding="utf-8")
        return _success_result(path)

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert any("增量备份不可用" in warning for warning in orchestrator.warnings)
    assert orchestrator._generated_contents["main.py"].startswith("def main")


@pytest.mark.asyncio
async def test_dep_layers_triages_cancelled_and_exception_results(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["cancel.py", "boom.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        if file_info["path"] == "cancel.py":
            raise asyncio.CancelledError()
        raise ValueError("boom")

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    with pytest.raises(RuntimeError, match="dependency layer 1 file generation failed"):
        await orchestrator._generate_files_by_dep_layers(
            [{"path": "cancel.py", "description": "d"}, {"path": "boom.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            2,
            _Graph(),
        )

    assert any("文件生成被取消: cancel.py" in error for error in orchestrator.errors)
    assert any("内部异常" in error for error in orchestrator.errors)


@pytest.mark.asyncio
async def test_dep_layers_ignores_unreadable_generated_file(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["missing.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "missing.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert "missing.py" not in orchestrator._generated_contents


@pytest.mark.asyncio
async def test_single_file_uses_feedback_learner_prevention_prompt(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    captured = {}

    class _Learner:
        async def get_prevention_prompt(self, **_kwargs):
            return "avoid rm -rf"

    orchestrator.feedback_learner = _Learner()

    async def generate(file_path, _description, project_context, *_args, **_kwargs):
        captured["context"] = project_context
        return "def main():\n    return 1\n"

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert captured["context"]["prevention_hints"] == "avoid rm -rf"


@pytest.mark.asyncio
async def test_single_file_builds_dependency_context(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    calls = {}

    class _Graph:
        nodes = {"database.py": object()}

        def get_context_for_file(self, file_path, generated, model_context_length):
            calls["args"] = (file_path, generated, model_context_length)
            return "## 依赖文件: database.py\n```\ndef get_db():\n    pass\n```"

    orchestrator.dependency_graph_obj = _Graph()

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
        {"database.py": "def get_db():\n    pass\n"},
    )

    assert result["success"] is True
    assert calls["args"][0] == "main.py"


@pytest.mark.asyncio
async def test_single_file_awaits_coroutine_generation_twice(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    responses = iter([
        _async_value("def main():\n    return 1\n"),
        _async_value("def main():\n    return 1\n"),
    ])

    async def generate(*_args, **_kwargs):
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_single_file_recovers_invalid_content(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    recovered = []

    async def recover(file_path, description, project_context, reason, *_args, **_kwargs):
        recovered.append(reason)
        return "def main():\n    return 1\n"

    monkeypatch.setattr(orchestrator, "_recover_invalid_content_orchestator", recover)

    async def generate(*_args, **_kwargs):
        return '{"status": "completed"}'

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    monkeypatch.setattr(of, "extract_engineer_content", AsyncMock(return_value=None))

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert recovered


@pytest.mark.asyncio
async def test_single_file_static_repair_round_applies_repairs(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=AsyncMock(),
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    monkeypatch.setattr(orchestrator, "_select_model_for_file", lambda _p: "m")

    responses = iter([
        "from utils import missing_symbol\n\ndef run():\n    return missing_symbol()\n",
        "from utils import foo\n\ndef run():\n    return foo()\n",
    ])

    async def fake_generate(*_args, **_kwargs):
        return next(responses)

    engineer.generate_file = fake_generate
    generated = {"utils.py": "def foo():\n    return 1\n"}
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("utils.py")
    graph.add_dependency("main.py", "utils.py")
    orchestrator.dependency_graph_obj = graph

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        2,
        generated,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_import_repairs_trigger_second_validation(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=AsyncMock(return_value="def main():\n    return 1\n"),
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    monkeypatch.setattr(of, "extract_engineer_content", AsyncMock(return_value="def main():\n    return 1\n"))
    monkeypatch.setattr(
        of, "_repair_python_known_imports",
        lambda content, _errors: content + "\n# repaired\n",
    )
    monkeypatch.setattr(of, "_repair_python_project_symbol_imports", lambda content, *_a: content)
    monkeypatch.setattr(of, "_repair_python_project_call_keywords", lambda content, _e: content)
    monkeypatch.setattr(of, "_repair_python_schema_field_access", lambda content, _e: content)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert "# repaired" in (tmp_path / "main.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_single_file_repair_loop_stops_on_repeated_errors(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    responses = iter([
        "from utils import missing_symbol\n\ndef run():\n    return missing_symbol()\n",
        "from utils import missing_symbol\n\ndef run():\n    return missing_symbol()\n",
    ])

    async def fake_generate(*_args, **_kwargs):
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=fake_generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    with pytest.raises(RuntimeError, match="跨文件导入不一致"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            2,
            {"utils.py": "def foo():\n    return 1\n"},
        )


@pytest.mark.asyncio
async def test_single_file_correction_adds_dependency_export_hints(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    prompts = []
    responses = iter([
        "from utils import missing_symbol\n\ndef run():\n    return missing_symbol()\n",
        "from utils import foo\n\ndef run():\n    return foo()\n",
    ])

    async def fake_generate(_path, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=fake_generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("utils.py")
    graph.add_dependency("main.py", "utils.py")
    orchestrator.dependency_graph_obj = graph

    await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        2,
        {
            "utils.py": "def foo():\n    return 1\n",
            "README.md": "docs",
            "bad.py": "def (:",
        },
    )

    assert "已生成依赖真实公共符号清单" in prompts[1]
    assert "utils.py: foo" in prompts[1]


@pytest.mark.asyncio
async def test_single_file_correction_mentions_database_abstraction_violation(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    prompts = []
    responses = iter([
        "from sqlalchemy import Column\n\nclass Todo:\n    pass\n",
        "from sqlalchemy import Column\n\nclass Todo:\n    pass\n",
    ])

    async def fake_generate(_path, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=fake_generate,
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    architecture = {
        "language": "python",
        "file_plan": [
            {"path": "database.py", "file_type": "database"},
            {"path": "models.py", "file_type": "model"},
        ],
    }
    graph = DependencyGraph()
    graph.add_file("models.py")
    graph.add_file("database.py")
    graph.add_dependency("models.py", "database.py")
    orchestrator.dependency_graph_obj = graph

    with pytest.raises(RuntimeError):
        await orchestrator._generate_single_file(
            {"path": "models.py", "description": "models"},
            {"architecture": architecture},
            2,
            {"database.py": "import sqlite3\n\ndef connect():\n    return sqlite3.connect('x.db')\n"},
        )

    assert "违反数据库抽象统一约束" in prompts[1]


@pytest.mark.asyncio
async def test_single_file_rejected_by_approval_returns_failure(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.require_approval = True
    orchestrator.approval_result = False

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is False
    assert result["rejected_by_user"] is True
    assert any("文件被用户拒绝" in warning for warning in orchestrator.warnings)


@pytest.mark.asyncio
async def test_single_file_validation_failure_raises(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_validation = True

    async def fail_validate(**_kwargs):
        return False, "x"

    monkeypatch.setattr(orchestrator, "_validate_and_review_file", fail_validate)

    with pytest.raises(RuntimeError, match="file validation failed"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_single_file_write_failure_raises(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "write_file_atomic", lambda *_a, **_k: False)

    with pytest.raises(RuntimeError, match="文件落盘失败"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_single_file_persists_through_artifact_committer(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    event = types.SimpleNamespace(path="main.py")
    orchestrator.artifact_completion_events = []

    class _Committer:
        def commit(self, file_path, content, model_name):
            (tmp_path / file_path).write_text(content, encoding="utf-8")
            return types.SimpleNamespace(success=True, completion_event=event)

    orchestrator.artifact_committer = _Committer()

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert orchestrator.artifact_completion_events == [event]


@pytest.mark.asyncio
async def test_single_file_artifact_commit_failure_includes_diagnostic(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)

    class _Committer:
        def commit(self, *_args, **_kwargs):
            return types.SimpleNamespace(
                success=False,
                completion_event=None,
                diagnostic=types.SimpleNamespace(message="disk full"),
            )

    orchestrator.artifact_committer = _Committer()

    with pytest.raises(RuntimeError, match="disk full"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_single_file_committer_without_events_and_no_list(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)

    class _Committer:
        def commit(self, file_path, content, model_name):
            (tmp_path / file_path).write_text(content, encoding="utf-8")
            return types.SimpleNamespace(success=True, completion_event=None)

    orchestrator.artifact_committer = _Committer()

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_checks_api_consistency(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    checked = []

    class _Checker:
        pass

    orchestrator.api_contract_checker = _Checker()
    monkeypatch.setattr(orchestrator, "_should_check_api_consistency", lambda _p: True)

    async def check(file_path, content):
        checked.append(file_path)

    monkeypatch.setattr(orchestrator, "_check_and_report_api_issues", check)

    await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert checked == ["main.py"]


@pytest.mark.asyncio
async def test_single_file_records_feedback_fix_history(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    recorded = []

    class _Learner:
        async def get_prevention_prompt(self, **_kwargs):
            return ""

        def record_fix(self, **kwargs):
            recorded.append(kwargs)

    orchestrator.feedback_learner = _Learner()
    fix = types.SimpleNamespace(
        file_path=str(tmp_path / "main.py"),
        error_message="syntax",
        fix_applied=True,
    )
    orchestrator.error_recovery = types.SimpleNamespace(fix_history=[fix])

    await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert recorded and recorded[0]["success"] is True


@pytest.mark.asyncio
async def test_recover_invalid_content_json_and_markdown_prompts(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    prompts = []

    async def generate(_path, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return "def main():\n    return 1\n"

    engineer = types.SimpleNamespace(generate_file=generate)
    monkeypatch.setattr(of, "extract_engineer_content", AsyncMock(return_value="def main():\n    return 1\n"))

    json_recovered = await orchestrator._recover_invalid_content_orchestator(
        "main.py", "entry", {"architecture": {"language": "python"}}, "返回了 JSON 元数据", engineer
    )
    markdown_recovered = await orchestrator._recover_invalid_content_orchestator(
        "main.py", "entry", {"architecture": {"language": "python"}}, "返回了 Markdown 文档", engineer
    )
    generic_recovered = await orchestrator._recover_invalid_content_orchestator(
        "main.py", "entry", {"architecture": {"language": "python"}}, "其它原因", engineer
    )

    assert json_recovered and markdown_recovered and generic_recovered
    assert "JSON 元数据" in prompts[0]
    assert "Markdown 文档" in prompts[1]
    assert "其它原因" in prompts[2]


@pytest.mark.asyncio
async def test_recover_invalid_content_awaits_coroutine(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    async def generate(*_args, **_kwargs):
        return _async_value("def main():\n    return 1\n")

    engineer = types.SimpleNamespace(generate_file=generate)
    monkeypatch.setattr(of, "extract_engineer_content", AsyncMock(return_value="def main():\n    return 1\n"))

    recovered = await orchestrator._recover_invalid_content_orchestator(
        "main.py", "entry", {"architecture": {"language": "python"}}, "bad", engineer
    )

    assert recovered == "def main():\n    return 1\n"


@pytest.mark.asyncio
async def test_recover_invalid_content_returns_none_after_two_failures(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    async def generate(*_args, **_kwargs):
        return "def main():\n    return 1\n"

    engineer = types.SimpleNamespace(generate_file=generate)
    monkeypatch.setattr(of, "extract_engineer_content", AsyncMock(return_value=None))

    recovered = await orchestrator._recover_invalid_content_orchestator(
        "main.py", "entry", {"architecture": {"language": "python"}}, "bad", engineer
    )

    assert recovered is None


@pytest.mark.asyncio
async def test_patches_incremental_cross_file_success(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "main.py").write_text("main()\n", encoding="utf-8")
    patch_result = CrossFilePatchResult(
        primary_file="main.py",
        primary_result=PatchResult(
            success=True, file_path="main.py", original_content="",
            patched_content="", diff="", errors=[], warnings=[],
        ),
        dependency_chain={"main.py": ["helper.py"]},
    )

    async def generate_cross_file_patches(**_kwargs):
        return patch_result

    orchestrator.dependency_graph_obj = types.SimpleNamespace(
        get_affected_files=lambda _path: ["helper.py"]
    )
    orchestrator.cross_file_patcher = types.SimpleNamespace(
        generate_cross_file_patches=generate_cross_file_patches
    )

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "helper.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert any(entry.get("cross_file_changes") for entry in orchestrator.generated_files)


@pytest.mark.asyncio
async def test_patches_incremental_cross_file_failure_raises(tmp_path):
    orchestrator = _Orchestrator(tmp_path)

    async def generate_cross_file_patches(**_kwargs):
        return CrossFilePatchResult(
            primary_file="main.py",
            primary_result=PatchResult(
                success=False, file_path="main.py", original_content="",
                patched_content="", diff="", errors=["x"], warnings=[],
            ),
            failed_patches=["helper.py"],
        )

    orchestrator.dependency_graph_obj = types.SimpleNamespace(
        get_affected_files=lambda _path: ["helper.py"]
    )
    orchestrator.cross_file_patcher = types.SimpleNamespace(
        generate_cross_file_patches=generate_cross_file_patches
    )

    with pytest.raises(RuntimeError, match="cross-file patch failed"):
        await orchestrator._apply_patches_incremental(
            "change",
            [{"path": "helper.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_patches_incremental_missing_file_is_generated(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    async def generate(file_info, *_args, **_kwargs):
        return _success_result(file_info["path"])

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "helper.py", "description": "helper"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert orchestrator.generated_files == [_success_result("helper.py")]


@pytest.mark.asyncio
async def test_patches_incremental_applies_patch_to_existing_file(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    orchestrator._call_llm_for_patch = AsyncMock()

    async def apply_change(**_kwargs):
        return PatchResult(
            success=True,
            file_path="main.py",
            original_content="def main():\n    return 1\n",
            patched_content="def main():\n    return 2\n",
            diff="--- a\n+++ b\n-old\n+new\n",
            errors=[],
            warnings=[],
        )

    monkeypatch.setattr(of, "apply_incremental_change", apply_change)

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert orchestrator.generated_files[0]["mode"] == "patch"
    assert any(call[0][0] == "patch_applied" for call in orchestrator.progress)


@pytest.mark.asyncio
async def test_patches_incremental_patch_failure_raises(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "main.py").write_text("x\n", encoding="utf-8")
    orchestrator._call_llm_for_patch = AsyncMock()

    async def apply_change(**_kwargs):
        return PatchResult(
            success=False, file_path="main.py", original_content="x\n",
            patched_content="", diff="", errors=["bad patch"], warnings=[],
        )

    monkeypatch.setattr(of, "apply_incremental_change", apply_change)

    with pytest.raises(RuntimeError, match="bad patch"):
        await orchestrator._apply_patches_incremental(
            "change",
            [{"path": "main.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_patches_incremental_skips_files_handled_by_cross_file_patch(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.dependency_graph_obj = types.SimpleNamespace(
        get_affected_files=lambda _path: ["helper.py"]
    )

    async def generate_cross_file_patches(**_kwargs):
        return CrossFilePatchResult(
            primary_file="main.py",
            primary_result=PatchResult(
                success=True, file_path="main.py", original_content="",
                patched_content="", diff="", errors=[], warnings=[],
            ),
            dependency_chain={"main.py": ["helper.py"]},
        )

    orchestrator.cross_file_patcher = types.SimpleNamespace(
        generate_cross_file_patches=generate_cross_file_patches
    )

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "helper.py", "description": "h"}],
        {"architecture": {"language": "python"}},
        2,
    )


def test_select_engineer_routes_by_extension(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.frontend_engineer = "fe"
    orchestrator.backend_engineer = "be"

    assert of.FilesMixin._select_engineer(orchestrator, "src/App.vue") == "fe"
    assert of.FilesMixin._select_engineer(orchestrator, "index.html") == "fe"
    assert of.FilesMixin._select_engineer(orchestrator, "main.py") == "be"


def test_is_frontend_and_critical_helpers(tmp_path):
    orchestrator = _Orchestrator(tmp_path)

    assert of.FilesMixin._is_frontend_file(orchestrator, "src/App.vue") is True
    assert of.FilesMixin._is_frontend_file(orchestrator, "main.py") is False
    assert of.FilesMixin._is_critical_file(orchestrator, "src/main.py") is True
    assert of.FilesMixin._is_critical_file(orchestrator, "src/helper.py") is False


def test_normalize_file_path_handles_empty_input(tmp_path):
    orchestrator = _Orchestrator(tmp_path)

    assert orchestrator._normalize_file_path("") == ""


def test_select_model_for_file_routes_all_branches(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.model_assignment = types.SimpleNamespace(
        reviewer_model="reviewer",
        frontend_model="frontend",
        backend_model="backend",
    )

    select = of.FilesMixin._select_model_for_file
    assert select(orchestrator, "pom.xml") == "reviewer"
    assert select(orchestrator, "tests/test_api.py") == "reviewer"
    assert select(orchestrator, "src/App.vue") == "frontend"
    assert select(orchestrator, "main.py") == "backend"
    assert select(orchestrator, "README.md") == "frontend"


def test_friendly_error_all_branches(tmp_path):
    orchestrator = _Orchestrator(tmp_path)

    assert orchestrator._friendly_error("request timeout") == "请求超时，请稍后重试"
    assert orchestrator._friendly_error("unauthorized") == "API 认证失败，请检查 API Key 配置"
    assert orchestrator._friendly_error("forbidden") == "API 访问被拒绝，请检查权限"
    assert orchestrator._friendly_error("not found") == "API 端点不存在"
    assert orchestrator._friendly_error("connection reset") == "网络连接失败，请检查网络"
    assert orchestrator._friendly_error("json parse error") == "模型返回格式异常，请重试"
    assert orchestrator._friendly_error("x" * 150).endswith("...")


@pytest.mark.asyncio
async def test_validate_and_review_error_recovery_write_failure(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_error_recovery = True
    orchestrator.model_assignment = types.SimpleNamespace(backend_model="model")

    async def validate_and_fix(**_kwargs):
        return True, "def main():\n    return 1\n"

    orchestrator.error_recovery = types.SimpleNamespace(validate_and_fix=validate_and_fix)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(asyncio, "to_thread", boom)

    success, _content = await orchestrator._validate_and_review_file(
        "main.py", "def main():\n    return 1\n", "entry"
    )

    assert success is False


@pytest.mark.asyncio
async def test_validate_and_review_error_recovery_failure_sets_false(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_error_recovery = True
    orchestrator.model_assignment = types.SimpleNamespace(backend_model="model")

    async def validate_and_fix(**_kwargs):
        return False, "broken"

    orchestrator.error_recovery = types.SimpleNamespace(validate_and_fix=validate_and_fix)

    success, _content = await orchestrator._validate_and_review_file("main.py", "x", "entry")

    assert success is False


@pytest.mark.asyncio
async def test_validate_and_review_returns_on_cache_hit(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_validation = True
    cached = {"is_valid": True}
    orchestrator.validator = types.SimpleNamespace(
        get_cached_validation_by_key=lambda _key: cached,
    )

    success, content = await orchestrator._validate_and_review_file("main.py", "x", "entry")

    assert success is True
    assert any(call[0][0] == "validation_cache_hit" for call in orchestrator.progress)


@pytest.mark.asyncio
async def test_validate_and_review_validator_exception_sets_failure(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_validation = True

    async def validate_single_file(_path):
        raise ValueError("validator blew up")

    orchestrator.validator = types.SimpleNamespace(
        get_cached_validation_by_key=lambda _key: None,
        validate_single_file=validate_single_file,
    )

    success, _content = await orchestrator._validate_and_review_file("main.py", "x", "entry")

    assert success is False
