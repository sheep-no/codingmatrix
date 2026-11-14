"""feature_extractor / aicloud_state_adapter / math_utils 缺口补测。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.orchestrator_generation import feature_extractor
from app.services import aicloud_state_adapter as adapter
from app.utils.math_utils import cosine_similarity


class _Manager:
    def __init__(self, result=None, extract_error=None, trigger_error=None):
        self.result = result or {"features": ["a"]}
        self.extract_error = extract_error
        self.trigger_error = trigger_error
        self.calls = []

    async def extract_and_save(self, requirement, files, domain=""):
        self.calls.append(("extract", requirement, files, domain))
        if self.extract_error:
            raise self.extract_error
        return self.result

    async def trigger_template_extraction(self, domain):
        self.calls.append(("trigger", domain))
        if self.trigger_error:
            raise self.trigger_error
        return True


@pytest.fixture
def manager(monkeypatch):
    holder = {}

    def factory():
        return holder["manager"]

    monkeypatch.setattr(
        "app.agent.project_metadata.ProjectMetadataManager", factory, raising=False
    )
    import app.agent.project_metadata as metadata

    monkeypatch.setattr(metadata, "ProjectMetadataManager", factory)
    holder["manager"] = _Manager()
    return holder


async def test_feature_extractor_filters_empty_files(manager):
    manager["manager"] = _Manager(result={"features": []})

    result = await feature_extractor.extract_and_save_feature_list(
        "req", {"a.py": "x = 1", "b.py": "", "": "ignored"}, domain="backend"
    )

    assert result == {"features": []}
    call = manager["manager"].calls[0]
    assert call == ("extract", "req", {"a.py": "x = 1"}, "backend")


async def test_feature_extractor_handles_none_files(manager):
    result = await feature_extractor.extract_and_save_feature_list("req", None)

    assert result == {"features": ["a"]}
    assert manager["manager"].calls[0][2] == {}


async def test_feature_extractor_swallows_trigger_failure(manager):
    manager["manager"] = _Manager(trigger_error=RuntimeError("template boom"))

    result = await feature_extractor.extract_and_save_feature_list("req", {"a.py": "x"})

    assert result == {"features": ["a"]}
    assert manager["manager"].calls[-1] == ("trigger", "")


async def test_feature_extractor_swallows_extract_failure(manager):
    manager["manager"] = _Manager(extract_error=RuntimeError("metadata boom"))

    assert await feature_extractor.extract_and_save_feature_list(
        "req", {"a.py": "x"}
    ) is None


async def test_ensure_session_falls_back_when_mapping_target_missing(monkeypatch):
    db = AsyncMock()
    mapping = SimpleNamespace(unified_id="gone")
    db.get.return_value = None
    new_session = SimpleNamespace(id="fresh")
    create = AsyncMock(return_value=new_session)
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=mapping))
    monkeypatch.setattr(adapter, "create_session", create)
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.ensure_session(db, 1, "legacy")

    assert result is new_session
    create.assert_awaited_once()


async def test_append_legacy_message_without_id_skips_mapping(monkeypatch):
    db = AsyncMock()
    session = SimpleNamespace(id="s-1")
    message = SimpleNamespace(id=5)
    monkeypatch.setattr(adapter, "ensure_session", AsyncMock(return_value=session))
    resolve = AsyncMock()
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", resolve)
    append = AsyncMock(return_value=message)
    monkeypatch.setattr(adapter, "append_message", append)
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.append_legacy_message(db, 1, "legacy", "user", "hello")

    assert result is message
    resolve.assert_not_awaited()
    upsert.assert_not_awaited()
    append.assert_awaited_once_with(
        db,
        "s-1",
        1,
        "user",
        "hello",
        metadata={
            "source": "aicloud",
            "legacy_session_id": "legacy",
            "legacy_message_id": None,
        },
    )


async def test_append_legacy_message_replays_when_id_mapping_target_missing(monkeypatch):
    db = AsyncMock()
    db.get.return_value = None
    session = SimpleNamespace(id="s-1")
    message = SimpleNamespace(id=9)
    monkeypatch.setattr(adapter, "ensure_session", AsyncMock(return_value=session))
    monkeypatch.setattr(
        adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="44")),
    )
    monkeypatch.setattr(adapter, "append_message", AsyncMock(return_value=message))
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.append_legacy_message(
        db, 1, "legacy", "assistant", "hi", legacy_message_id="44"
    )

    assert result is message
    upsert.assert_awaited_once()
    assert upsert.await_args.args[5:7] == ("message", "9")
    assert upsert.await_args.kwargs["source_table"] == "aicloud_messages"
    assert upsert.await_args.kwargs["metadata"] == {"session_id": "s-1"}


async def test_append_legacy_message_with_unmapped_id_appends_new(monkeypatch):
    db = AsyncMock()
    session = SimpleNamespace(id="s-1")
    message = SimpleNamespace(id=10)
    monkeypatch.setattr(adapter, "ensure_session", AsyncMock(return_value=session))
    monkeypatch.setattr(
        adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(adapter, "append_message", AsyncMock(return_value=message))
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.append_legacy_message(
        db, 1, "legacy", "user", "hi", legacy_message_id="99"
    )

    assert result is message
    upsert.assert_awaited_once()


def test_math_cosine_similarity_branches():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0
