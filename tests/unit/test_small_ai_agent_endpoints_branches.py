"""Branch coverage for small ai_agent endpoint modules."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import (
    association_endpoints,
    knowledge_endpoints,
    model_context_endpoints,
    performance_endpoints,
)
from app.api.v1.ai_agent.schemas import (
    AgentModelContextUpdate,
    KnowledgeRequest,
    RequirementAssociationRequest,
)
from app.services.unified_state_service import StateConflictError


def _entry(**overrides):
    values = {
        "id": "k1",
        "content": "c",
        "knowledge_key": "key",
        "category": "general",
        "importance": 0.5,
        "usage_count": 1,
        "created_at": None,
        "tags": ["t"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_add_knowledge_success(monkeypatch):
    service = SimpleNamespace(add_knowledge=AsyncMock(return_value=_entry()))
    monkeypatch.setattr(knowledge_endpoints, "AgentMemoryService", lambda db: service)

    response = await knowledge_endpoints.add_knowledge(
        KnowledgeRequest(content="c"), {"sub": "u1"}, object()
    )

    assert response.id == "k1"
    assert response.created_at is None
    service.add_knowledge.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_knowledge_missing_user():
    with pytest.raises(HTTPException) as exc:
        await knowledge_endpoints.add_knowledge(
            KnowledgeRequest(content="c"), {}, object()
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_list_knowledge_converts_entries(monkeypatch):
    service = SimpleNamespace(
        get_user_knowledge=AsyncMock(return_value=[_entry()])
    )
    monkeypatch.setattr(knowledge_endpoints, "AgentMemoryService", lambda db: service)

    response = await knowledge_endpoints.list_knowledge("general", 50, {"sub": "u1"}, object())

    assert response[0].id == "k1"
    assert response[0].created_at is None


@pytest.mark.asyncio
async def test_list_knowledge_missing_user():
    with pytest.raises(HTTPException) as exc:
        await knowledge_endpoints.list_knowledge(None, 50, {}, object())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_search_knowledge_converts_entries(monkeypatch):
    service = SimpleNamespace(
        search_knowledge=AsyncMock(return_value=[_entry()])
    )
    monkeypatch.setattr(knowledge_endpoints, "AgentMemoryService", lambda db: service)

    response = await knowledge_endpoints.search_knowledge("c", None, 10, {"sub": "u1"}, object())

    assert response[0].knowledge_key == "key"


@pytest.mark.asyncio
async def test_search_knowledge_missing_user():
    with pytest.raises(HTTPException) as exc:
        await knowledge_endpoints.search_knowledge("c", None, 10, {}, object())
    assert exc.value.status_code == 401


def _metrics(**overrides):
    values = {
        "avg_time_ms": 10.0,
        "min_time_ms": float("inf"),
        "max_time_ms": 20.0,
        "total_calls": 3,
        "cache_hit_rate": 0.5,
        "alerts": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_performance_metrics_and_trends(monkeypatch):
    collector = SimpleNamespace(
        export_metrics=MagicMock(return_value={"m": 1}),
        thresholds={"t": 1},
        get_all_metrics=MagicMock(return_value={"mod": _metrics()}),
    )
    monkeypatch.setattr(performance_endpoints, "metrics_collector", collector)

    metrics = await performance_endpoints.get_performance_metrics({"sub": "u1"})
    trends = await performance_endpoints.get_performance_trends({})

    assert metrics["metrics"] == {"m": 1}
    assert metrics["thresholds"] == {"t": 1}
    assert trends["trends"]["mod"]["min_time_ms"] == 0
    assert trends["trends"]["mod"]["max_time_ms"] == 20.0


@pytest.mark.asyncio
async def test_performance_export_success(monkeypatch):
    collector = SimpleNamespace(save_metrics=MagicMock())
    monkeypatch.setattr(performance_endpoints, "metrics_collector", collector)

    response = await performance_endpoints.export_performance_metrics({"sub": "u1"})

    assert response["success"] is True


@pytest.mark.asyncio
async def test_performance_export_failure(monkeypatch):
    collector = SimpleNamespace(save_metrics=MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(performance_endpoints, "metrics_collector", collector)

    response = await performance_endpoints.export_performance_metrics({})

    assert response["success"] is False
    assert "boom" in response["message"]


@pytest.mark.asyncio
async def test_association_skipped_branch():
    response = await association_endpoints.requirement_association(
        RequirementAssociationRequest(requirement="r", skip_association=True), {"sub": "u1"}
    )
    assert response.skipped is True


@pytest.mark.asyncio
async def test_association_auto_complexity_and_items(monkeypatch):
    monkeypatch.setattr(
        "app.agent.complexity.ComplexityAnalyzer",
        lambda: SimpleNamespace(analyze=lambda req: SimpleNamespace(level=SimpleNamespace(value="medium"))),
    )

    item = SimpleNamespace(
        content="i",
        category="cat",
        source="src",
        confidence=0.9,
        sub_category="sub",
        impact="high",
        dual_model_agreement="agree",
        devil_review="none",
    )
    result = SimpleNamespace(
        skipped=False,
        skip_reason="ignored",
        domain_matched="bank",
        domains_matched=["bank"],
        items=[item],
        enhanced_requirement="enhanced",
        devil_review_items=[],
        elapsed_seconds=0.1,
    )

    class _Mixin:
        def __init__(self):
            self.callback = None

        async def _generate_requirement_associations(self, requirement, level):
            return result

        def _classify_items_for_display(self, items):
            return {"cat": {"shown": [items[0].content], "collapsed": []}}

    monkeypatch.setattr(
        "app.agent.orchestrator_requirements.RequirementAssociationMixin", _Mixin
    )

    response = await association_endpoints.requirement_association(
        RequirementAssociationRequest(requirement="r"), {"sub": "u1"}
    )

    assert response.domain_matched == "bank"
    assert response.items[0]["content"] == "i"
    assert response.classified_items == {"cat": {"shown": ["i"], "collapsed": []}}
    assert response.skip_reason is None


@pytest.mark.asyncio
async def test_association_skipped_result_and_empty_items(monkeypatch):
    monkeypatch.setattr(
        "app.agent.complexity.ComplexityAnalyzer",
        lambda: SimpleNamespace(analyze=lambda req: SimpleNamespace(level=SimpleNamespace(value="small"))),
    )
    result = SimpleNamespace(
        skipped=True,
        skip_reason="no match",
        domain_matched="",
        domains_matched=[],
        items=[],
        enhanced_requirement="",
        devil_review_items=[],
        elapsed_seconds=0.0,
    )

    class _Mixin:
        def __init__(self):
            self.callback = None

        async def _generate_requirement_associations(self, requirement, level):
            return result

        def _classify_items_for_display(self, items):
            raise AssertionError("should not classify empty items")

    monkeypatch.setattr(
        "app.agent.orchestrator_requirements.RequirementAssociationMixin", _Mixin
    )

    response = await association_endpoints.requirement_association(
        RequirementAssociationRequest(requirement="r", complexity_level="small"), {"sub": "u1"}
    )

    assert response.skipped is True
    assert response.skip_reason == "no match"
    assert response.classified_items == {}


@pytest.mark.asyncio
async def test_association_stats(monkeypatch):
    tracker = SimpleNamespace(
        get_feedback_stats=MagicMock(return_value={"total": 1}),
        get_rejection_reason_stats=MagicMock(return_value={"r": 1}),
    )
    monkeypatch.setattr(
        "app.agent.orchestrator_requirements.AssociationFeedbackTracker", lambda: tracker
    )

    response = await association_endpoints.requirement_association_stats({"sub": "u1"})

    assert response == {
        "feedback_stats": {"total": 1},
        "rejection_reason_stats": {"r": 1},
    }


@pytest.mark.asyncio
async def test_model_context_read_found(monkeypatch):
    monkeypatch.setattr(
        model_context_endpoints,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="u")),
    )
    monkeypatch.setattr(
        model_context_endpoints,
        "get_model_context_snapshot",
        AsyncMock(return_value=SimpleNamespace(revision=2, context={"a": 1})),
    )

    response = await model_context_endpoints.read_agent_model_context(
        "s1", {"sub": "1"}, object()
    )

    assert response.found is True
    assert response.revision == 2


@pytest.mark.asyncio
async def test_model_context_read_missing_mapping(monkeypatch):
    monkeypatch.setattr(
        model_context_endpoints, "resolve_compatibility_mapping", AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc:
        await model_context_endpoints.read_agent_model_context("s1", {"sub": "1"}, object())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_model_context_read_no_snapshot(monkeypatch):
    monkeypatch.setattr(
        model_context_endpoints,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="u")),
    )
    monkeypatch.setattr(
        model_context_endpoints, "get_model_context_snapshot", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        model_context_endpoints, "build_runtime_model_context", lambda: {"runtime": True}
    )

    response = await model_context_endpoints.read_agent_model_context(
        "s1", {"sub": "1"}, object()
    )

    assert response.found is False
    assert response.context == {"runtime": True}


@pytest.mark.asyncio
async def test_model_context_update_success(monkeypatch):
    monkeypatch.setattr(
        model_context_endpoints, "verify_session_ownership", AsyncMock()
    )
    monkeypatch.setattr(
        model_context_endpoints,
        "ensure_project_session",
        AsyncMock(return_value=SimpleNamespace(id="sid")),
    )
    monkeypatch.setattr(
        model_context_endpoints,
        "save_model_context",
        AsyncMock(return_value=SimpleNamespace(revision=3, context={"b": 2})),
    )
    db = SimpleNamespace(commit=AsyncMock())

    response = await model_context_endpoints.update_agent_model_context(
        "s1",
        AgentModelContextUpdate(expected_revision=1, current_model="m"),
        {"sub": "1"},
        db,
    )

    assert response.revision == 3
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_context_update_conflict(monkeypatch):
    monkeypatch.setattr(
        model_context_endpoints, "verify_session_ownership", AsyncMock()
    )
    monkeypatch.setattr(
        model_context_endpoints,
        "ensure_project_session",
        AsyncMock(return_value=SimpleNamespace(id="sid")),
    )
    monkeypatch.setattr(
        model_context_endpoints,
        "save_model_context",
        AsyncMock(side_effect=StateConflictError("conflict")),
    )
    db = SimpleNamespace(commit=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await model_context_endpoints.update_agent_model_context(
            "s1",
            AgentModelContextUpdate(expected_revision=1),
            {"sub": "1"},
            db,
        )
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()
