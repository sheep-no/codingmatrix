"""project_tasks.generate_project 执行链与超时映射补测。"""

import types

import pytest

from app.tasks import project_tasks
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


def _install_agent(monkeypatch, *, behavior=None):
    captured = {}

    class _Agent:
        async def generate_project(self, **kwargs):
            captured.update(kwargs)
            if behavior is not None:
                return behavior(kwargs)
            return {"files": {"main.py": "print('hi')"}}

    module = types.ModuleType("app.api.v1.AiProjectCode")
    module.ProjectGeneratorAgent = _Agent
    monkeypatch.setitem(__import__("sys").modules, "app.api.v1.AiProjectCode", module)
    return captured


def test_generate_project_runs_agent_and_reports_progress(monkeypatch, progress):
    captured = _install_agent(monkeypatch)

    result = project_tasks.generate_project.run(
        task_id="t-1", requirement="build app", user_id=3
    )

    assert result == {"files": {"main.py": "print('hi')"}}
    assert captured == {
        "requirement": "build app",
        "task_id": "t-1",
        "user_id": 3,
        "progress_callback": progress.update,
    }
    assert [value for value, _ in progress.events] == [10, 30, 100]


def test_generate_project_maps_soft_time_limit(monkeypatch):
    def fake_run(coro):
        coro.close()
        raise project_tasks.SoftTimeLimitExceeded()

    monkeypatch.setattr(project_tasks.asyncio, "run", fake_run)

    with pytest.raises(AgentTaskTimeoutError):
        project_tasks.generate_project.run(
            task_id="t-2", requirement="x", user_id=1
        )


def test_generate_project_reraises_other_errors(monkeypatch):
    def fake_run(coro):
        coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(project_tasks.asyncio, "run", fake_run)

    with pytest.raises(RuntimeError, match="boom"):
        project_tasks.generate_project.run(
            task_id="t-3", requirement="x", user_id=1
        )
