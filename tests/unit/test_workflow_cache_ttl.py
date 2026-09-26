"""工作流内存缓存 TTL 过期清理回归（WF1）。

`_workflows`/`_session_workflows` 为进程内存态字典，此前只有容量上限、无 TTL，
长跑进程内即使未超上限也会常驻。现按 `updated_at` 惰性清理过期条目：
- 已完成/未运行的工作流过 TTL 即删；
- `status == "running"` 的条目不删，避免误清正在执行的工作流；
- 缺时间戳或格式非法的条目不删，避免误伤。
"""

from datetime import datetime, timedelta

import pytest

from app.api.v1 import workflow as wf


@pytest.fixture
def isolated_caches():
    saved_workflows = dict(wf._workflows)
    saved_sessions = dict(wf._session_workflows)
    wf._workflows.clear()
    wf._session_workflows.clear()
    yield
    wf._workflows.clear()
    wf._workflows.update(saved_workflows)
    wf._session_workflows.clear()
    wf._session_workflows.update(saved_sessions)


def _stamp(seconds_ago: int) -> str:
    return (datetime.now() - timedelta(seconds=seconds_ago)).isoformat()


class TestPruneExpired:
    def test_expired_completed_workflow_removed(self, isolated_caches):
        wf._workflows["old"] = {
            "status": "completed",
            "updated_at": _stamp(wf._WORKFLOW_TTL_SECONDS + 60),
        }

        wf._prune_expired(
            wf._workflows, datetime.now(), wf._WORKFLOW_TTL_SECONDS, keep_running=True
        )

        assert "old" not in wf._workflows

    def test_fresh_workflow_kept(self, isolated_caches):
        wf._workflows["fresh"] = {"status": "completed", "updated_at": _stamp(60)}

        wf._prune_expired(
            wf._workflows, datetime.now(), wf._WORKFLOW_TTL_SECONDS, keep_running=True
        )

        assert "fresh" in wf._workflows

    def test_running_workflow_not_pruned(self, isolated_caches):
        wf._workflows["running"] = {
            "status": "running",
            "updated_at": _stamp(wf._WORKFLOW_TTL_SECONDS + 60),
        }

        wf._prune_expired(
            wf._workflows, datetime.now(), wf._WORKFLOW_TTL_SECONDS, keep_running=True
        )

        assert "running" in wf._workflows

    def test_missing_or_malformed_timestamp_not_pruned(self, isolated_caches):
        wf._workflows["no-ts"] = {"status": "completed"}
        wf._workflows["bad-ts"] = {"status": "completed", "updated_at": "not-a-date"}

        wf._prune_expired(
            wf._workflows, datetime.now(), wf._WORKFLOW_TTL_SECONDS, keep_running=True
        )

        assert set(wf._workflows) == {"no-ts", "bad-ts"}


class TestSessionWorkflowPrune:
    def test_remember_prunes_expired_sessions(self, isolated_caches):
        wf._session_workflows[("u1", "stale")] = {
            "updated_at": _stamp(wf._SESSION_WORKFLOW_TTL_SECONDS + 60),
        }

        wf._remember_session_workflow("u1", "fresh", {"updated_at": _stamp(0)})

        assert ("u1", "stale") not in wf._session_workflows
        assert ("u1", "fresh") in wf._session_workflows

    def test_remember_keeps_fresh_sessions(self, isolated_caches):
        wf._session_workflows[("u1", "recent")] = {"updated_at": _stamp(60)}

        wf._remember_session_workflow("u1", "fresh", {"updated_at": _stamp(0)})

        assert ("u1", "recent") in wf._session_workflows
        assert ("u1", "fresh") in wf._session_workflows
