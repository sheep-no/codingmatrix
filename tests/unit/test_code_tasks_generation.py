"""补测 app/tasks/code_tasks.py 的生成任务、路径工具与测试执行回退链路。"""

import asyncio
import subprocess
from pathlib import Path

import pytest

from app.tasks import code_tasks
from app.tasks.base import BaseTask
from app.tasks.exceptions import AgentTaskTimeoutError


class _FakeProgress:
    def __init__(self):
        self.events = []

    async def update(self, progress, message=""):
        self.events.append((progress, message))


@pytest.fixture
def progress(monkeypatch):
    fake = _FakeProgress()
    monkeypatch.setattr(BaseTask, "_get_progress_callback", lambda *a, **k: fake)
    return fake


class TestGenerateCode:
    def _run(self, **overrides):
        params = {
            "task_id": "t-gen",
            "prompt": "写个函数",
            "language": "python",
            "user_id": 1,
        }
        params.update(overrides)
        return code_tasks.generate_code.run(**params)

    def test_generates_without_search(self, monkeypatch, progress):
        seen = {}

        async def fake_api(*, model, prompt, stream=False):
            seen["prompt"] = prompt
            seen["model"] = model
            return {"choices": [{"message": {"content": "def f(): pass"}}]}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        result = self._run()

        assert result == {
            "code": "def f(): pass",
            "language": "python",
            "prompt": "写个函数",
        }
        assert seen["prompt"] == "写个函数"
        assert [p for p, _ in progress.events] == [20, 60, 100]

    def test_generates_with_search_context(self, monkeypatch, progress):
        seen = {}

        class _Searcher:
            async def search_and_format(self, prompt, count=3):
                seen["count"] = count
                return "检索结果"

        async def fake_api(*, model, prompt, stream=False):
            seen["prompt"] = prompt
            return {"choices": [{"message": {"content": "ok"}}]}

        monkeypatch.setattr("app.utils.web_search.FreeWebSearch", _Searcher)
        monkeypatch.setattr("app.utils.call_llm", fake_api)

        result = self._run(search_enabled=True)

        assert result["code"] == "ok"
        assert seen["count"] == 3
        assert "上下文信息:\n检索结果" in seen["prompt"]
        assert "用户需求:\n写个函数" in seen["prompt"]
        assert [p for p, _ in progress.events] == [20, 40, 60, 100]

    def test_missing_content_defaults_to_empty(self, monkeypatch, progress):
        async def fake_api(*, model, prompt, stream=False):
            return {}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        assert self._run()["code"] == ""

    def test_non_dict_result_defaults_to_empty(self, monkeypatch, progress):
        async def fake_api(*, model, prompt, stream=False):
            return "unexpected"

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        assert self._run()["code"] == ""

    def test_non_string_choice_content_defaults_to_empty(self, monkeypatch, progress):
        async def fake_api(*, model, prompt, stream=False):
            return {"choices": [{"message": {"content": None}}]}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        assert self._run()["code"] == ""

    def test_flat_content_is_passed_through(self, monkeypatch, progress):
        async def fake_api(*, model, prompt, stream=False):
            return {"content": "flat"}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        assert self._run()["code"] == "flat"

    def test_soft_time_limit_becomes_task_timeout(self, monkeypatch, progress):
        async def fake_api(*, model, prompt, stream=False):
            raise code_tasks.SoftTimeLimitExceeded()

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        with pytest.raises(AgentTaskTimeoutError):
            self._run()


class TestModifyWithTestErrorPaths:
    def _params(self):
        return {
            "task_id": "t1",
            "user_id": 1,
            "requirement": "改一下",
            "target_files": ["app/x.py"],
            "max_retry_loops": 1,
        }

    def test_soft_time_limit_becomes_task_timeout(self, monkeypatch):
        def fake_run(coro):
            coro.close()
            raise code_tasks.SoftTimeLimitExceeded()

        monkeypatch.setattr(code_tasks.asyncio, "run", fake_run)

        with pytest.raises(AgentTaskTimeoutError):
            code_tasks.modify_with_test.run(**self._params())

    def test_unexpected_error_is_logged_and_reraised(self, monkeypatch):
        def fake_run(coro):
            coro.close()
            raise RuntimeError("kaboom")

        monkeypatch.setattr(code_tasks.asyncio, "run", fake_run)

        with pytest.raises(RuntimeError, match="kaboom"):
            code_tasks.modify_with_test.run(**self._params())


class TestPathHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, ""),
            ("", ""),
            ("  app/x.py  ", "app/x.py"),
            ("./app/x.py", "app/x.py"),
            ("././app/x.py", "app/x.py"),
            ("app\\sub\\x.py", "app/sub/x.py"),
        ],
    )
    def test_normalize_repo_path(self, raw, expected):
        assert code_tasks._normalize_repo_path(raw) == expected

    def test_is_safe_target_path_rejects_empty(self):
        assert code_tasks._is_safe_target_path("") is False
        assert code_tasks._is_safe_target_path("./") is False

    def test_find_affected_files_returns_empty_without_input(self):
        assert code_tasks._find_affected_files({}, ["a.py"]) == []
        assert code_tasks._find_affected_files({"reverse_index": {}}, ["a.py"]) == []
        assert code_tasks._find_affected_files({"reverse_index": {"a.py": ["b.py"]}}, []) == []

    def test_find_affected_files_excludes_targets_and_dedupes(self):
        dep_graph = {
            "reverse_index": {
                "app/a.py": ["app/b.py", "app/c.py"],
                "app/c.py": ["app/b.py", "app/a.py"],
            }
        }

        result = code_tasks._find_affected_files(
            dep_graph, ["app/a.py", "./app/c.py"]
        )

        assert result == ["app/b.py"]

    def test_matches_test_pattern_handles_glob_and_basename(self):
        assert code_tasks._matches_test_pattern("app/*.py", "app/x.py") is True
        assert code_tasks._matches_test_pattern("x.py", "deep/dir/x.py") is True
        assert code_tasks._matches_test_pattern("x.py", "deep/dir/y.py") is False
        assert code_tasks._matches_test_pattern("", "x.py") is False
        assert code_tasks._matches_test_pattern("x.py", "") is False


class TestCollectGuardViolations:
    def test_existing_file_violations_are_collected(self, monkeypatch, tmp_path):
        target = tmp_path / "sample.py"
        target.write_text("x = 1\n", encoding="utf-8")

        class _Violation:
            def __init__(self):
                self.rule = "R1"

        captured = {}

        def fake_check(path, content):
            captured["path"] = path
            captured["content"] = content
            return [_Violation()]

        monkeypatch.setattr("app.utils.guard_contracts.check_file_against_contracts", fake_check)

        result = code_tasks._collect_guard_violations([str(target)])

        assert captured["content"] == "x = 1\n"
        assert result == [{"rule": "R1"}]

    def test_missing_file_is_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.utils.guard_contracts.check_file_against_contracts",
            lambda *a, **k: pytest.fail("不存在的文件不应被检查"),
        )

        assert code_tasks._collect_guard_violations([str(tmp_path / "nope.py")]) == []

    def test_none_target_files_returns_empty(self):
        assert code_tasks._collect_guard_violations(None) == []


class TestGetRelatedTests:
    def test_missing_mapping_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(tmp_path / "none.yaml"))
        assert code_tasks._get_related_tests(["app/x.py"]) == []

    def test_mapping_and_global_tests_are_merged(self, monkeypatch, tmp_path):
        mapping_file = tmp_path / "map.yaml"
        mapping_file.write_text(
            "mapping:\n"
            "  'app/*.py':\n"
            "    - tests/unit/test_app.py\n"
            "global_tests:\n"
            "  - tests/smoke.py\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(mapping_file))

        assert code_tasks._get_related_tests(["app/x.py"]) == [
            "tests/smoke.py",
            "tests/unit/test_app.py",
        ]

    def test_malformed_yaml_returns_empty(self, monkeypatch, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("mapping: [unclosed", encoding="utf-8")
        monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(bad_file))

        assert code_tasks._get_related_tests(["app/x.py"]) == []


class TestRunTests:
    def test_empty_file_list_is_failure(self):
        result = asyncio.run(code_tasks._run_tests([]))
        assert result["success"] is False
        assert result["total"] == 0

    def test_isolated_runner_success_is_mapped(self, monkeypatch):
        class _Result:
            success = True
            logs = "all good"
            passed = 3
            failed = 0
            total_tests = 3

        class _Runner:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def run_tests(self, test_paths):
                self.test_paths = test_paths
                return _Result()

        monkeypatch.setattr("app.agent.test_runner.IsolatedTestRunner", _Runner)

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result["success"] is True
        assert result["stdout"] == "all good"
        assert result["returncode"] == 0
        assert result["error"] == ""
        assert result["total"] == 3

    def test_isolated_runner_failure_is_mapped(self, monkeypatch):
        class _Result:
            success = False
            logs = "boom"
            passed = 1
            failed = 2
            total_tests = 3

        class _Runner:
            def __init__(self, **kwargs):
                pass

            async def run_tests(self, test_paths):
                return _Result()

        monkeypatch.setattr("app.agent.test_runner.IsolatedTestRunner", _Runner)

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result["success"] is False
        assert result["returncode"] == 1
        assert result["error"] == "boom"
        assert result["failed"] == 2

    def test_runner_import_error_falls_back_to_subprocess(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "app.agent.test_runner":
                raise ImportError("unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        class _Proc:
            returncode = 0
            stdout = "ok output"
            stderr = ""

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(code_tasks.asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(code_tasks.subprocess, "run", lambda *a, **k: _Proc())

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result["success"] is True
        assert result["stdout"] == "ok output"

    def test_subprocess_timeout_is_reported(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def boom_import(name, *args, **kwargs):
            if name == "app.agent.test_runner":
                raise ImportError("unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", boom_import)

        async def fake_to_thread(func, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="pytest", timeout=120)

        monkeypatch.setattr(code_tasks.asyncio, "to_thread", fake_to_thread)

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result == {"success": False, "error": "测试超时 (120s)"}

    def test_subprocess_unexpected_error_is_reported(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def boom_import(name, *args, **kwargs):
            if name == "app.agent.test_runner":
                raise ImportError("unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", boom_import)

        async def fake_to_thread(func, *args, **kwargs):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(code_tasks.asyncio, "to_thread", fake_to_thread)

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result == {"success": False, "error": "kaboom"}

    def test_subprocess_failure_returns_stderr(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def boom_import(name, *args, **kwargs):
            if name == "app.agent.test_runner":
                raise ImportError("unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", boom_import)

        class _Proc:
            returncode = 1
            stdout = "out"
            stderr = "err"

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(code_tasks.asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(code_tasks.subprocess, "run", lambda *a, **k: _Proc())

        result = asyncio.run(code_tasks._run_tests(["tests/test_x.py"]))

        assert result["success"] is False
        assert result["error"] == "err"


class TestAgentHelpers:
    def test_agent_modify_builds_prompt(self, monkeypatch):
        seen = {}

        async def fake_api(*, model, prompt, stream=False):
            seen["prompt"] = prompt
            return {"content": "patched"}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        result = asyncio.run(
            code_tasks._agent_modify(
                requirement="加日志",
                target_files=["app/x.py"],
                affected_files=["app/y.py"],
                progress_cb=None,
            )
        )

        assert result == {"content": "patched", "status": "completed"}
        assert "需求: 加日志" in seen["prompt"]
        assert "app/y.py" in seen["prompt"]

    def test_agent_fix_uses_last_log_error(self, monkeypatch):
        seen = {}

        async def fake_api(*, model, prompt, stream=False):
            seen["prompt"] = prompt
            return {"content": "fixed"}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        result = asyncio.run(
            code_tasks._agent_fix_from_test_logs(
                test_logs=[{"error": "first"}, {"error": "last"}],
                original_result={},
                progress_cb=None,
            )
        )

        assert result == {"content": "fixed", "status": "fixed", "retry": 2}
        assert "last" in seen["prompt"]

    def test_agent_fix_defaults_to_unknown_error(self, monkeypatch):
        seen = {}

        async def fake_api(*, model, prompt, stream=False):
            seen["prompt"] = prompt
            return {"content": "fixed"}

        monkeypatch.setattr("app.utils.call_llm", fake_api)

        asyncio.run(
            code_tasks._agent_fix_from_test_logs(
                test_logs=[{}], original_result={}, progress_cb=None
            )
        )

        assert "未知错误" in seen["prompt"]
