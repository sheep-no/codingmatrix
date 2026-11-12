"""Workflow API 全分支回归。"""

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1 import workflow as wf
from app.schema.workflow import TaskGraph, TaskNode, TaskType, WorkflowRequest


@pytest.fixture(autouse=True)
def isolate_caches(monkeypatch):
    monkeypatch.setattr(wf, "_workflows", {})
    monkeypatch.setattr(wf, "_session_workflows", {})
    yield


class FakeDecomposer:
    graph = None
    error = None
    seen = None

    def __init__(self, *args, **kwargs):
        pass

    async def decompose(self, request):
        FakeDecomposer.seen = request
        if FakeDecomposer.error:
            raise FakeDecomposer.error
        return FakeDecomposer.graph


class FakeValidator:
    valid = True
    errors = []
    checked_semantics = None

    def validate(self, graph, check_semantics=False):
        FakeValidator.checked_semantics = check_semantics
        return FakeValidator.valid, list(FakeValidator.errors)


class NodeResult:
    def __init__(self, success=True, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error


class FakeExecutor:
    result = {"status": "completed", "summary": {"completed_nodes": 1}}
    error = None
    instances = []
    cancel_on_node = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.cancelled = False
        self.aggregator = MagicMock()
        self.aggregator.get_all_results.return_value = {}
        self.aggregator.get_workflow_summary.return_value = {"completed_nodes": 1}
        FakeExecutor.instances.append(self)

    async def execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
        if on_node_start:
            on_node_start("n1")
        if on_node_complete:
            on_node_complete("n1", NodeResult(data={"x": 1}))
        if on_node_skip:
            on_node_skip("n2")
        if FakeExecutor.error:
            raise FakeExecutor.error
        return FakeExecutor.result

    def cancel(self):
        self.cancelled = True

    def get_aggregator(self):
        return self.aggregator


@pytest.fixture
def runtime(monkeypatch):
    FakeDecomposer.graph = TaskGraph(
        workflow_id="wf1",
        nodes=[
            TaskNode(id="n1", type=TaskType.DATA_TRANSFORM),
            TaskNode(id="n2", type=TaskType.DATA_TRANSFORM),
        ],
    )
    FakeDecomposer.error = None
    FakeValidator.valid = True
    FakeValidator.errors = []
    FakeExecutor.result = {"status": "completed", "summary": {"completed_nodes": 1}}
    FakeExecutor.error = None
    FakeExecutor.instances = []
    monkeypatch.setattr(wf, "TaskDecomposer", FakeDecomposer)
    monkeypatch.setattr(wf, "GraphValidator", FakeValidator)
    monkeypatch.setattr(wf, "WorkflowExecutor", FakeExecutor)
    return runtime


def _db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


async def _collect(response):
    return [json.loads(chunk) async for chunk in response.body_iterator]


class TestHelpers:
    def test_prune_expired_removes_expired_keeps_running(self):
        now = datetime.now()
        old = (now - timedelta(seconds=100)).isoformat()
        store = {
            "old": {"updated_at": old},
            "running": {"updated_at": old, "status": "running"},
            "fresh": {"updated_at": now.isoformat()},
        }
        wf._prune_expired(store, now, 10, keep_running=True)
        assert set(store) == {"running", "fresh"}

    def test_remember_session_workflow_prunes_and_evicts(self, monkeypatch):
        now = datetime.now()
        old = (now - timedelta(seconds=100)).isoformat()
        monkeypatch.setattr(wf, "_MAX_SESSION_WORKFLOWS", 2)
        wf._session_workflows["stale"] = {
            "updated_at": (now - timedelta(days=2)).isoformat()
        }
        wf._session_workflows["bad"] = {"updated_at": old}
        wf._session_workflows[("u", "a")] = {"updated_at": "1"}
        wf._session_workflows[("u", "b")] = {"updated_at": "2"}
        wf._remember_session_workflow("u", "c", {"updated_at": now.isoformat()})
        assert "stale" not in wf._session_workflows
        assert "bad" in wf._session_workflows
        assert ("u", "a") not in wf._session_workflows
        assert ("u", "c") in wf._session_workflows

    def test_is_expired_without_timestamp(self):
        assert wf._is_expired({}, datetime.now(), 10) is False

    def test_is_expired_malformed(self):
        assert wf._is_expired({"updated_at": "bad"}, datetime.now(), 10) is False

    def test_is_expired_true(self):
        stamp = (datetime.now() - timedelta(seconds=100)).isoformat()
        assert wf._is_expired({"updated_at": stamp}, datetime.now(), 10) is True

    @pytest.mark.asyncio
    async def test_drain_event_queue(self):
        queue = asyncio.Queue()
        queue.put_nowait("a")
        queue.put_nowait("b")
        assert [e async for e in wf._drain_event_queue(queue, timeout=0.001)] == ["a", "b"]


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_success_events(self, runtime):
        FakeDecomposer.graph.workflow_id = "wf-success"
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do it", session_id=None),
                {"sub": "u1"},
                _db(),
            )
        )
        names = [e["event"] for e in events]
        assert names[0] == "workflow_started"
        assert "task_graph_generated" in names
        assert "node_started" in names
        assert "node_completed" in names
        assert "node_skipped" in names
        assert names[-1] == "workflow_completed"
        assert events[-1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_export_event(self, runtime):
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do", export_workflow=True),
                {"user_id": "u1"},
                _db(),
            )
        )
        exported = [e for e in events if e["event"] == "workflow_exported"]
        assert exported and "export_data" in exported[0]

    @pytest.mark.asyncio
    async def test_invalid_graph(self, runtime):
        FakeValidator.valid = False
        FakeValidator.errors = ["cycle"]
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["event"] == "workflow_error"
        assert "cycle" in events[-1]["message"]

    @pytest.mark.asyncio
    async def test_decomposer_error(self, runtime):
        FakeDecomposer.error = wf.TaskDecomposerError("bad")
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["error"] == "decomposition_failed"

    @pytest.mark.asyncio
    async def test_executor_exception_sets_failed(self, runtime):
        FakeExecutor.error = RuntimeError("boom")
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["error"] == "execution_failed"

    @pytest.mark.asyncio
    async def test_continuation_uses_previous_request(self, runtime):
        wf._session_workflows[("u1", "s1")] = {
            "request": "old request",
            "workflow_id": "old-id",
            "updated_at": datetime.now().isoformat(),
        }
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="new", session_id="s1"),
                {"sub": "u1"},
                _db(),
            )
        )
        assert events[0]["is_continuation"] is True
        assert any(e["event"] == "continuation_context" for e in events)
        assert "old request" in FakeDecomposer.seen
        assert ("u1", "s1") in wf._session_workflows

    @pytest.mark.asyncio
    async def test_history_save_error_is_logged(self, runtime, monkeypatch):
        messages = []
        monkeypatch.setattr(wf.logger, "error", messages.append)
        db = _db()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, db
            )
        )
        assert events[-1]["event"] == "workflow_completed"
        assert any("保存工作流历史记录失败" in m for m in messages)

    @pytest.mark.asyncio
    async def test_cache_limit_evicts_oldest(self, runtime, monkeypatch):
        monkeypatch.setattr(wf, "_MAX_WORKFLOWS", 1)
        wf._workflows["existing"] = {"updated_at": datetime.now().isoformat()}
        await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert "existing" not in wf._workflows

    @pytest.mark.asyncio
    async def test_node_complete_with_error_and_no_data(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
            on_node_complete("n1", NodeResult(success=False, error="bad"))
            return {"status": "failed", "summary": {}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        completed = [e for e in events if e["event"] == "node_completed"][0]
        assert completed["success"] is False
        assert completed["error"] == "bad"
        assert "data" not in completed

    @pytest.mark.asyncio
    async def test_stream_close_cancels_executor_and_record(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
            await asyncio.sleep(30)

        async def _drain(queue, timeout=0.05):
            yield json.dumps({"event": "tick"}) + "\n"

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        monkeypatch.setattr(wf, "_drain_event_queue", _drain)
        response = await wf.execute_workflow(
            WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
        )
        stream = response.body_iterator
        await anext(stream)
        await anext(stream)
        await anext(stream)
        workflow_id = next(iter(wf._workflows))
        await stream.aclose()
        await asyncio.sleep(0.01)
        assert FakeExecutor.instances[0].cancelled is True
        assert wf._workflows[workflow_id]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_slow_executor_polls_and_final_drain(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
            await asyncio.sleep(0.06)
            on_node_start("n1")
            await asyncio.sleep(0.10)
            on_node_complete("n1", NodeResult(data={"x": 1}))
            return {"status": "completed", "summary": {"completed_nodes": 1}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["event"] == "workflow_completed"
        assert any(e["event"] == "node_started" for e in events)
        assert any(e["event"] == "node_completed" for e in events)

    @pytest.mark.asyncio
    async def test_record_terminal_skips_replaced_executor(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
            wf._workflows[self.kwargs["task_graph"].workflow_id]["executor"] = None
            return {"status": "completed", "summary": {}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["event"] == "workflow_completed"

    @pytest.mark.asyncio
    async def test_executor_none_result_goes_to_error_branch(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None, on_node_skip=None):
            return None

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        events = await _collect(
            await wf.execute_workflow(
                WorkflowRequest(natural_language_request="do"), {"sub": "u1"}, _db()
            )
        )
        assert events[-1]["event"] == "workflow_error"


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with pytest.raises(wf.HTTPException) as exc:
            await wf.get_workflow_status("missing", {"sub": "u1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        wf._workflows["w"] = {"user_id": "other", "task_graph": TaskGraph(workflow_id="w")}
        with pytest.raises(wf.HTTPException) as exc:
            await wf.get_workflow_status("w", {"sub": "u1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_without_executor(self):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph, "status": "imported"}
        result = await wf.get_workflow_status("w", {"sub": "u1"})
        assert result["summary"] is None
        assert result["task_graph"]["nodes"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_with_executor_and_results(self):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        aggregator = MagicMock()
        aggregator.get_all_results.return_value = {
            "n1": SimpleNamespace(success=True, data={"d": 1}, error=None)
        }
        aggregator.get_workflow_summary.return_value = {"completed_nodes": 1}
        executor = MagicMock()
        executor.get_aggregator.return_value = aggregator
        wf._workflows["w"] = {
            "user_id": "u1",
            "task_graph": graph,
            "executor": executor,
            "status": "running",
        }
        result = await wf.get_workflow_status("w", {"user_id": "u1"})
        node = result["task_graph"]["nodes"][0]
        assert node["status"] == "completed"
        assert node["result"] == {"d": 1}
        assert result["summary"] == {"completed_nodes": 1}


class TestImportExport:
    @pytest.mark.asyncio
    async def test_import_invalid(self, runtime):
        FakeValidator.valid = False
        FakeValidator.errors = ["bad"]
        graph = TaskGraph(workflow_id="w", nodes=[])
        with pytest.raises(wf.HTTPException) as exc:
            await wf.import_workflow(graph, {"sub": "u1"})
        assert exc.value.status_code == 400
        assert FakeValidator.checked_semantics is True

    @pytest.mark.asyncio
    async def test_import_success(self, runtime):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        result = await wf.import_workflow(graph, {"sub": "u1"})
        assert result["status"] == "imported"
        assert wf._workflows["w"]["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_export_not_found(self):
        with pytest.raises(wf.HTTPException) as exc:
            await wf.export_workflow("missing", {"sub": "u1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_export_wrong_user(self):
        wf._workflows["w"] = {"user_id": "other", "task_graph": TaskGraph(workflow_id="w")}
        with pytest.raises(wf.HTTPException) as exc:
            await wf.export_workflow("w", {"sub": "u1"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_export_model_dump(self):
        graph = TaskGraph(workflow_id="w", nodes=[])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        result = await wf.export_workflow("w", {"sub": "u1"})
        assert result["export_data"]["workflow_id"] == "w"

    @pytest.mark.asyncio
    async def test_export_fallback_shape(self):
        node = SimpleNamespace(
            id="n1", type=SimpleNamespace(value="data_transform"), params={}, depends_on=[]
        )
        graph = SimpleNamespace(
            workflow_id="w", version="1.0", nodes=[node], timeout=10, exportable=True
        )
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        result = await wf.export_workflow("w", {"sub": "u1"})
        assert result["export_data"]["nodes"][0]["id"] == "n1"
        assert result["export_data"]["timeout"] == 10

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        with pytest.raises(wf.HTTPException) as exc:
            await wf.delete_workflow("missing", {"sub": "u1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_wrong_user(self):
        wf._workflows["w"] = {"user_id": "other"}
        with pytest.raises(wf.HTTPException) as exc:
            await wf.delete_workflow("w", {"sub": "u1"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_success(self):
        wf._workflows["w"] = {"user_id": "u1"}
        result = await wf.delete_workflow("w", {"sub": "u1"})
        assert result["status"] == "deleted"
        assert "w" not in wf._workflows


class TestExecuteImported:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with pytest.raises(wf.HTTPException) as exc:
            await wf.execute_imported_workflow("missing", {"sub": "u1"}, _db())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        wf._workflows["w"] = {"user_id": "other"}
        with pytest.raises(wf.HTTPException) as exc:
            await wf.execute_imported_workflow("w", {"sub": "u1"}, _db())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self, runtime):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(
            await wf.execute_imported_workflow("w", {"sub": "u1"}, _db())
        )
        assert events[-1]["event"] == "workflow_completed"
        assert events[-1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_history_save_error(self, runtime, monkeypatch):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        db = _db()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))
        messages = []
        monkeypatch.setattr(wf.logger, "error", messages.append)
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, db))
        assert events[-1]["event"] == "workflow_completed"
        assert any("保存工作流历史记录失败" in m for m in messages)

    @pytest.mark.asyncio
    async def test_executor_error(self, runtime):
        FakeExecutor.error = RuntimeError("boom")
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["error"] == "execution_failed"

    @pytest.mark.asyncio
    async def test_node_result_with_data_and_error(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None):
            on_node_complete("n1", NodeResult(success=False, data={"d": 1}, error="e"))
            return {"status": "failed", "summary": {}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        completed = [e for e in events if e["event"] == "node_completed"][0]
        assert completed["data"] == {"d": 1}
        assert completed["error"] == "e"

    @pytest.mark.asyncio
    async def test_stream_close_cancels_executor_and_marks_cancelled(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None):
            await asyncio.sleep(30)

        async def _drain(queue, timeout=0.05):
            yield json.dumps({"event": "tick"}) + "\n"

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        monkeypatch.setattr(wf, "_drain_event_queue", _drain)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        response = await wf.execute_imported_workflow("w", {"sub": "u1"}, _db())
        stream = response.body_iterator
        await anext(stream)
        await anext(stream)
        await anext(stream)
        await stream.aclose()
        await asyncio.sleep(0.01)
        assert FakeExecutor.instances[-1].cancelled is True
        assert wf._workflows["w"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_record_terminal_marks_failed(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["error"] == "execution_failed"
        assert wf._workflows["w"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_record_removed_mid_execution_is_tolerated(self, runtime, monkeypatch):
        original_init = FakeExecutor.__init__

        def _init(self, **kwargs):
            original_init(self, **kwargs)
            wf._workflows.pop(kwargs["task_graph"].workflow_id, None)

        monkeypatch.setattr(FakeExecutor, "__init__", _init)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["event"] == "workflow_completed"
        assert "w" not in wf._workflows

    @pytest.mark.asyncio
    async def test_record_terminal_sets_status(self, runtime):
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        FakeExecutor.result = {"status": "completed", "summary": {}}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["event"] == "workflow_completed"
        assert wf._workflows["w"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_node_result_without_data(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None):
            on_node_complete("n1", NodeResult(success=False, error="bad"))
            return {"status": "failed", "summary": {}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        completed = [e for e in events if e["event"] == "node_completed"][0]
        assert completed["error"] == "bad"
        assert "data" not in completed

    @pytest.mark.asyncio
    async def test_slow_executor_polls_and_final_drain(self, runtime, monkeypatch):
        async def _execute(self, on_node_start=None, on_node_complete=None):
            await asyncio.sleep(0.06)
            on_node_start("n1")
            await asyncio.sleep(0.10)
            on_node_complete("n1", NodeResult(data={"x": 1}))
            return {"status": "completed", "summary": {}}

        monkeypatch.setattr(FakeExecutor, "execute", _execute)
        graph = TaskGraph(workflow_id="w", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["event"] == "workflow_completed"
        assert any(e["event"] == "node_started" for e in events)

    @pytest.mark.asyncio
    async def test_fallback_graph_dump(self, runtime):
        node = SimpleNamespace(
            id="n1", type=SimpleNamespace(value="data_transform"), params={}, depends_on=[]
        )
        graph = SimpleNamespace(
            workflow_id="w", nodes=[node], timeout=10
        )
        wf._workflows["w"] = {"user_id": "u1", "task_graph": graph}
        events = await _collect(await wf.execute_imported_workflow("w", {"sub": "u1"}, _db()))
        assert events[-1]["event"] == "workflow_completed"


class TestHistory:
    @pytest.mark.asyncio
    async def test_list_history(self):
        record = SimpleNamespace(to_dict=lambda: {"workflow_id": "w"})
        result = MagicMock()
        result.scalars.return_value.all.return_value = [record]
        total = MagicMock()
        total.scalar.return_value = 1
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[total, result])
        response = await wf.get_workflow_history({"sub": "u1"}, db, page=1, page_size=20)
        assert response["total"] == 1
        assert response["items"] == [{"workflow_id": "w"}]

    @pytest.mark.asyncio
    async def test_list_history_zero_total(self):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        total = MagicMock()
        total.scalar.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[total, result])
        response = await wf.get_workflow_history({"sub": "u1"}, db, page=1, page_size=20)
        assert response["total"] == 0

    @pytest.mark.asyncio
    async def test_history_detail(self):
        record = SimpleNamespace(to_dict=lambda: {"workflow_id": "w"})
        result = MagicMock()
        result.scalar_one_or_none.return_value = record
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        assert await wf.get_workflow_history_detail("w", {"sub": "u1"}, db) == {"workflow_id": "w"}

    @pytest.mark.asyncio
    async def test_history_detail_missing(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        with pytest.raises(wf.HTTPException) as exc:
            await wf.get_workflow_history_detail("w", {"sub": "u1"}, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_history(self):
        record = SimpleNamespace()
        result = MagicMock()
        result.scalar_one_or_none.return_value = record
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        response = await wf.delete_workflow_history("w", {"sub": "u1"}, db)
        assert response["status"] == "deleted"
        db.delete.assert_awaited_once_with(record)

    @pytest.mark.asyncio
    async def test_delete_history_missing(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        with pytest.raises(wf.HTTPException) as exc:
            await wf.delete_workflow_history("w", {"sub": "u1"}, db)
        assert exc.value.status_code == 404
