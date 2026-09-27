"""modify_with_test 重试循环与验证语义回归（TSK17/TSK18/TSK19 + 循环终止）。

- 循环终止：达到最大重试次数后必须退出，不得无限重复运行测试。
- TSK18：无关联测试时不得报告 success=True（无验证证据）。
- TSK19：success 反映最终一轮结果，而非历史所有轮次的与。
- TSK17：守护合约检查不得读取项目根目录之外的文件。
"""

from unittest.mock import AsyncMock

from app.tasks import code_tasks
from app.tasks.base import BaseTask


class _FakeProgress:
    async def update(self, progress, message=""):
        return None


def _prepare(monkeypatch, run_tests, test_files=("tests/test_x.py",), guard=None):
    monkeypatch.setattr(BaseTask, "_get_progress_callback", lambda *a, **k: _FakeProgress())
    monkeypatch.setattr(code_tasks, "_get_related_tests", lambda tf: list(test_files))
    monkeypatch.setattr(code_tasks, "_run_tests", run_tests)
    monkeypatch.setattr(
        code_tasks, "_agent_modify",
        AsyncMock(return_value={"content": "x", "status": "completed"}),
    )
    monkeypatch.setattr(
        code_tasks, "_agent_fix_from_test_logs",
        AsyncMock(return_value={"content": "y", "status": "fixed"}),
    )
    monkeypatch.setattr(code_tasks, "_collect_guard_violations", lambda tf: guard or [])


def _run(**overrides):
    params = {
        "task_id": "t1",
        "user_id": 1,
        "requirement": "改一下",
        "target_files": ["app/x.py"],
        "max_retry_loops": 1,
    }
    params.update(overrides)
    return code_tasks.modify_with_test.run(**params)


def test_loop_terminates_after_max_retries(monkeypatch):
    """持续失败时，运行测试的次数必须是 max_retries + 1，不得无限循环。"""
    calls = {"n": 0}

    async def fake_run_tests(files):
        calls["n"] += 1
        if calls["n"] > 2:
            raise AssertionError("_run_tests 被调用超过预期，重试循环未终止")
        return {"success": False, "error": "boom"}

    _prepare(monkeypatch, fake_run_tests)

    result = _run()

    assert result["success"] is False
    assert calls["n"] == 2
    assert result["retry_count"] == 1
    assert len(result["test_results"]) == 2


def test_success_reflects_final_round(monkeypatch):
    """TSK19：首轮失败、修复后末轮通过，应报告 success=True。"""
    results = iter([{"success": False, "error": "boom"}, {"success": True}])

    async def fake_run_tests(files):
        return next(results)

    _prepare(monkeypatch, fake_run_tests)

    result = _run()

    assert result["success"] is True
    assert len(result["test_results"]) == 2


def test_no_related_tests_is_not_success(monkeypatch):
    """TSK18：没有关联测试时无验证证据，不得声称成功。"""
    async def fail_if_called(files):
        raise AssertionError("无测试文件时不应调用 _run_tests")

    _prepare(monkeypatch, fail_if_called, test_files=())

    result = _run()

    assert result["success"] is False
    assert result["verification"] == "no_tests"
    assert result["test_results"] == []


def test_run_tests_empty_reports_failure():
    """TSK18：``_run_tests([])`` 不再返回 success=True。"""
    import asyncio

    assert asyncio.run(code_tasks._run_tests([]))["success"] is False


def test_is_safe_target_path_rejects_traversal():
    """TSK17：拒绝含目录穿越的相对路径，绝对路径与项目内相对路径放行。"""
    assert code_tasks._is_safe_target_path("../../etc/passwd") is False
    assert code_tasks._is_safe_target_path("app/../etc/passwd") is False
    assert code_tasks._is_safe_target_path("app/tasks/code_tasks.py") is True
    assert code_tasks._is_safe_target_path("/tmp/sample.py") is True


def test_collect_guard_violations_skips_out_of_root(monkeypatch):
    """TSK17：越界目标文件不进入守护合约读取。"""
    called = []

    def fake_check(path, content):
        called.append(path)
        return []

    monkeypatch.setattr("app.utils.guard_contracts.check_file_against_contracts", fake_check)

    code_tasks._collect_guard_violations(["../../etc/passwd"])

    assert called == []
