"""补齐 devil_advocate_review 与响应解析的边界。"""

from unittest.mock import AsyncMock

import pytest

from app.agent.orchestrator_requirements import devil_advocate as module
from app.agent.orchestrator_requirements.data_models import AssociationItem


def _item(content="c", confidence=0.9, category="ui"):
    return AssociationItem(content=content, category=category, source="s", confidence=confidence)


@pytest.mark.asyncio
async def test_no_architect_returns_empty():
    assert await module.devil_advocate_review("req", [_item(), _item(), _item()]) == []


@pytest.mark.asyncio
async def test_too_few_items_returns_empty():
    assert await module.devil_advocate_review("req", [_item()], architect=object()) == []


@pytest.mark.asyncio
async def test_no_high_confidence_items_returns_empty():
    items = [_item(confidence=0.1) for _ in range(3)]

    assert await module.devil_advocate_review("req", items, architect=object()) == []


@pytest.mark.asyncio
async def test_llm_failure_returns_empty(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("app.utils.call_llm", boom)
    items = [_item() for _ in range(3)]

    assert await module.devil_advocate_review("req", items, architect=object()) == []


@pytest.mark.asyncio
async def test_success_filters_and_limits(monkeypatch):
    payload_items = []
    for index in range(15):
        payload_items.append(
            {
                "target_item": f"target-{index}",
                "challenge": f"challenge-{index}",
                "severity": "high",
                "suggestion": "fix",
            }
        )
    response = '{"challenges": ' + __import__("json").dumps(payload_items) + "}"

    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    items = [_item(content=f"c{i}") for i in range(20)]

    result = await module.devil_advocate_review("req", items, architect=object())

    assert len(result) == 10
    assert captured["model"] == module.DEVILS_ADVOCATE_MODEL
    assert "req" in captured["prompt"]


class TestParseDevilResponse:
    def test_valid_json_filters_incomplete(self):
        response = (
            '{"challenges": ['
            '{"target_item": "t", "challenge": "c"},'
            '{"target_item": "", "challenge": "c"},'
            '{"target_item": "t", "challenge": ""}'
            "]}"
        )

        result = module.parse_devil_response(response)

        assert result == [
            {"target_item": "t", "challenge": "c", "severity": "medium", "suggestion": ""}
        ]

    def test_invalid_json_returns_empty(self):
        assert module.parse_devil_response("{not json}") == []

    def test_no_json_object_returns_empty(self):
        assert module.parse_devil_response("nothing here") == []

    def test_missing_challenges_key(self):
        assert module.parse_devil_response('{"other": []}') == []

    def test_extra_text_around_object(self):
        result = module.parse_devil_response(
            'prefix {"challenges": [{"target_item": "t", "challenge": "c"}]} suffix'
        )

        assert result[0]["target_item"] == "t"
