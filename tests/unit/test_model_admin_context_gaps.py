"""Coverage gaps for model admin API and model context service."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.v2 import model_admin
from app.main import app
from app.services import model_context_service as mcs
from app.services.unified_state_service import StateConflictError, StateNotFoundError
from app.utils.security import require_superadmin


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_superadmin():
    async def _mock():
        return {"sub": "1", "permission_level": "superadmin", "role": "admin"}

    app.dependency_overrides[require_superadmin] = _mock
    yield
    app.dependency_overrides.clear()


def _put(client, path, payload):
    return client.put(path, json=payload)


class TestAgentConfigEmptyAndFailure:
    def test_agent_config_creates_default_when_missing(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: None)
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)
        monkeypatch.setattr(model_admin, "reload_roles_config", lambda: None)
        monkeypatch.setattr(model_admin._LayeredModelRouterCompat, "reload_config", lambda: None)

        resp = _put(client, "/api/v2/models/agent-config", {
            "complexity": "SIMPLE",
            "role": "architect",
            "model_id": next(iter(model_admin.MODEL_ID_TO_KEY)),
        })

        assert resp.status_code == 200
        assert resp.json()["config"]["roles"]

    def test_agent_config_adds_missing_roles_key(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"version": "3.0"})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)
        monkeypatch.setattr(model_admin, "reload_roles_config", lambda: None)
        monkeypatch.setattr(model_admin._LayeredModelRouterCompat, "reload_config", lambda: None)

        resp = _put(client, "/api/v2/models/agent-config", {
            "complexity": "SIMPLE",
            "role": "architect",
            "model_id": next(iter(model_admin.MODEL_ID_TO_KEY)),
        })

        assert resp.status_code == 200
        assert "roles" in resp.json()["config"]

    def test_agent_config_save_failure_returns_500(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: False)

        resp = _put(client, "/api/v2/models/agent-config", {
            "complexity": "SIMPLE",
            "role": "architect",
            "model_id": next(iter(model_admin.MODEL_ID_TO_KEY)),
        })

        assert resp.status_code == 500


class TestFallbackChainFallbacks:
    def test_fallback_chain_creates_default_when_missing(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: None)
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)
        monkeypatch.setattr(model_admin, "reload_roles_config", lambda: None)
        monkeypatch.setattr(model_admin._LayeredModelRouterCompat, "reload_config", lambda: None)
        model_id = next(iter(model_admin.MODEL_ID_TO_KEY))

        resp = _put(client, "/api/v2/models/agent-config/fallback-chain", {
            "chain_name": "default",
            "models": [model_id],
        })

        assert resp.status_code == 200
        assert resp.json()["config"]["fallback_chain"] == [model_id]

    def test_fallback_chain_save_failure_returns_500(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: False)
        model_id = next(iter(model_admin.MODEL_ID_TO_KEY))

        resp = _put(client, "/api/v2/models/agent-config/fallback-chain", {
            "chain_name": "default",
            "models": [model_id],
        })

        assert resp.status_code == 500


class TestErrorTypeModelFallbacks:
    def test_error_type_creates_default_when_missing(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: None)
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)
        model_id = next(iter(model_admin.MODEL_ID_TO_KEY))

        resp = _put(client, "/api/v2/models/agent-config/error-type-model", {
            "error_type": "NameError",
            "model_id": model_id,
        })

        assert resp.status_code == 200
        assert resp.json()["config"]["error_type_models"] == {"NameError": model_id}

    def test_error_type_adds_missing_mapping_key(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)
        model_id = next(iter(model_admin.MODEL_ID_TO_KEY))

        resp = _put(client, "/api/v2/models/agent-config/error-type-model", {
            "error_type": "NameError",
            "model_id": model_id,
        })

        assert resp.status_code == 200
        assert resp.json()["config"]["error_type_models"] == {"NameError": model_id}

    def test_error_type_save_failure_returns_500(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: False)
        model_id = next(iter(model_admin.MODEL_ID_TO_KEY))

        resp = _put(client, "/api/v2/models/agent-config/error-type-model", {
            "error_type": "NameError",
            "model_id": model_id,
        })

        assert resp.status_code == 500


class TestContextLengthFallbacks:
    def test_update_length_creates_default_when_missing(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: None)
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)

        resp = _put(client, "/api/v2/models/context-length", {
            "model_key": "Qwen/Qwen3-8B",
            "context_length": 8192,
        })

        assert resp.status_code == 200
        assert resp.json()["context_length"] == 8192

    def test_update_length_adds_missing_mapping_key(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: True)

        resp = _put(client, "/api/v2/models/context-length", {
            "model_key": "Qwen/Qwen3-8B",
            "context_length": 8192,
        })

        assert resp.status_code == 200
        assert resp.json()["context_length"] == 8192

    def test_update_length_save_failure_returns_500(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(model_admin, "load_agent_model_config", lambda: {"roles": {}})
        monkeypatch.setattr(model_admin, "save_agent_model_config", lambda cfg: False)

        resp = _put(client, "/api/v2/models/context-length", {
            "model_key": "Qwen/Qwen3-8B",
            "context_length": 8192,
        })

        assert resp.status_code == 500

    def test_get_lengths_skips_zero_config_entry(self, client, mock_superadmin, monkeypatch):
        monkeypatch.setattr(
            model_admin,
            "load_agent_model_config",
            lambda: {"model_context_lengths": {"zero-model": 0}},
        )

        resp = client.get("/api/v2/models/context-lengths")

        assert resp.status_code == 200
        assert "zero-model" not in resp.json()["models"]


# ---------------------------------------------------------------------------
# model_context_service
# ---------------------------------------------------------------------------

def test_build_runtime_context_swallows_config_errors(monkeypatch):
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: (_ for _ in ()).throw(ValueError("bad")),
    )
    context = mcs.build_runtime_model_context()
    assert context["roles"] == {}
    assert context["assignments"] == {}


@pytest.mark.asyncio
async def test_get_snapshot_none_when_task_missing():
    class DB:
        async def scalar(self, query):
            return None

    assert await mcs.get_model_context_snapshot(DB(), 1, "s") is None
    assert await mcs.get_model_context(DB(), 1, "s") is None


@pytest.mark.asyncio
async def test_get_snapshot_none_when_checkpoint_missing():
    task = type("Task", (), {"task_id": "t"})()

    class DB:
        def __init__(self):
            self.calls = 0

        async def scalar(self, query):
            self.calls += 1
            return task if self.calls == 1 else None

    assert await mcs.get_model_context_snapshot(DB(), 1, "s") is None


@pytest.mark.asyncio
async def test_get_snapshot_none_when_context_not_dict():
    task = type("Task", (), {"task_id": "t"})()
    checkpoint = type(
        "Checkpoint", (), {"state_json": {"model_context": "bad"}, "revision": 1}
    )()

    class DB:
        def __init__(self):
            self.calls = 0

        async def scalar(self, query):
            self.calls += 1
            return task if self.calls == 1 else checkpoint

    assert await mcs.get_model_context_snapshot(DB(), 1, "s") is None


@pytest.mark.asyncio
async def test_save_context_requires_existing_session():
    class DB:
        async def scalar(self, query):
            return None

    with pytest.raises(StateNotFoundError):
        await mcs.save_model_context(DB(), 1, "missing", {})


class _Nested:
    async def __aenter__(self):
        raise IntegrityError("stmt", {}, Exception("dup"))

    async def __aexit__(self, *exc):
        return False


class _FakeDB:
    def __init__(self, recovered_task):
        self.recovered_task = recovered_task
        self.calls = 0
        self.added = []

    async def scalar(self, query):
        self.calls += 1
        if self.calls == 1:
            return object()
        if self.calls == 2:
            return None
        if self.calls == 3:
            return self.recovered_task
        return 7

    def begin_nested(self):
        return _Nested()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_save_context_recovers_from_integrity_error(monkeypatch):
    task = type("Task", (), {"task_id": "t", "id": 1})()
    db = _FakeDB(task)
    saved = {}

    async def fake_snapshot(*args, **kwargs):
        return None

    async def fake_save_checkpoint(*args, **kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(mcs, "get_model_context_snapshot", fake_snapshot)
    monkeypatch.setattr(mcs, "save_checkpoint", fake_save_checkpoint)

    snapshot = await mcs.save_model_context(db, 1, "s", {"current_model": "m"})

    assert snapshot.revision == 7
    assert saved["revision"] == 7


@pytest.mark.asyncio
async def test_save_context_integrity_error_without_task_conflicts(monkeypatch):
    db = _FakeDB(None)

    async def fake_snapshot(*args, **kwargs):
        return None

    monkeypatch.setattr(mcs, "get_model_context_snapshot", fake_snapshot)

    with pytest.raises(StateConflictError, match="创建冲突"):
        await mcs.save_model_context(db, 1, "s", {})
