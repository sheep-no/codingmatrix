"""双模型深度联想全分支回归。"""

from types import SimpleNamespace

import pytest

from app.agent.orchestrator_requirements import layer3_dual_model as l3
from app.agent.orchestrator_requirements.data_models import AssociationItem


def _item(content="c", category="functional", confidence=0.6):
    return AssociationItem(
        content=content,
        category=category,
        source="llm_association",
        confidence=confidence,
    )


class _CallLLM:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, model, prompt, system_prompt):
        self.calls.append(model)
        value = self.responses[model]
        if isinstance(value, Exception):
            raise value
        return value


def _patch_llm(monkeypatch, responses):
    fake = _CallLLM(responses)
    import app.utils as utils

    monkeypatch.setattr(utils, "call_llm", fake)
    return fake


def _patch_parse(monkeypatch, mapping):
    def _parse(response):
        value = mapping[response]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(l3, "parse_llm_response", _parse)


@pytest.mark.asyncio
async def test_returns_empty_without_architect():
    assert await l3.layer3_dual_model_deep("req", [], []) == []


@pytest.mark.asyncio
async def test_single_model_a_success(monkeypatch):
    item = _item()
    fake = _patch_llm(monkeypatch, {l3.DUAL_MODEL_A: "a", l3.DUAL_MODEL_B: "b"})
    _patch_parse(monkeypatch, {"a": [item], "b": []})
    result = await l3.layer3_dual_model_deep("req", [_item()], [_item()], architect=object())
    assert result == [item]
    assert item.source == "llm_association:single"
    assert item.dual_model_agreement == "single_model"
    assert fake.calls == [l3.DUAL_MODEL_A, l3.DUAL_MODEL_B]


@pytest.mark.asyncio
async def test_single_model_b_success(monkeypatch):
    item = _item()
    _patch_llm(monkeypatch, {l3.DUAL_MODEL_A: "a", l3.DUAL_MODEL_B: "b"})
    _patch_parse(monkeypatch, {"a": [], "b": [item]})
    result = await l3.layer3_dual_model_deep("req", [], [], architect=object())
    assert result == [item]
    assert item.dual_model_agreement == "single_model"


@pytest.mark.asyncio
async def test_model_a_exception_falls_to_b(monkeypatch):
    item = _item()
    _patch_llm(
        monkeypatch,
        {l3.DUAL_MODEL_A: RuntimeError("a down"), l3.DUAL_MODEL_B: "b"},
    )
    _patch_parse(monkeypatch, {"b": [item]})
    result = await l3.layer3_dual_model_deep("req", [], [], architect=object())
    assert result == [item]


@pytest.mark.asyncio
async def test_parse_failure_for_a_falls_to_b(monkeypatch):
    item = _item()
    _patch_llm(monkeypatch, {l3.DUAL_MODEL_A: "a", l3.DUAL_MODEL_B: "b"})
    _patch_parse(monkeypatch, {"a": ValueError("bad json"), "b": [item]})
    result = await l3.layer3_dual_model_deep("req", [], [], architect=object())
    assert result == [item]


@pytest.mark.asyncio
async def test_model_b_exception_uses_fallback(monkeypatch):
    item = _item()
    _patch_llm(
        monkeypatch,
        {
            l3.DUAL_MODEL_A: RuntimeError("a"),
            l3.DUAL_MODEL_B: RuntimeError("b"),
            l3.DUAL_MODEL_FALLBACK: "f",
        },
    )
    _patch_parse(monkeypatch, {"f": [item]})
    result = await l3.layer3_dual_model_deep("req", [], [], architect=object())
    assert result == [item]
    assert item.source == "llm_association:fallback"
    assert item.dual_model_agreement == "fallback"


@pytest.mark.asyncio
async def test_all_models_fail_returns_empty(monkeypatch):
    _patch_llm(
        monkeypatch,
        {
            l3.DUAL_MODEL_A: RuntimeError("a"),
            l3.DUAL_MODEL_B: RuntimeError("b"),
            l3.DUAL_MODEL_FALLBACK: RuntimeError("f"),
        },
    )
    assert await l3.layer3_dual_model_deep("req", [], [], architect=object()) == []


@pytest.mark.asyncio
async def test_fallback_returns_no_items(monkeypatch):
    _patch_llm(
        monkeypatch,
        {
            l3.DUAL_MODEL_A: "a",
            l3.DUAL_MODEL_B: "b",
            l3.DUAL_MODEL_FALLBACK: "f",
        },
    )
    _patch_parse(monkeypatch, {"a": [], "b": [], "f": []})
    assert await l3.layer3_dual_model_deep("req", [], [], architect=object()) == []


@pytest.mark.asyncio
async def test_both_models_merge(monkeypatch):
    shared_a = _item("shared", confidence=0.5)
    shared_b = _item("shared", confidence=0.8)
    unique = _item("unique", confidence=0.9)
    _patch_llm(monkeypatch, {l3.DUAL_MODEL_A: "a", l3.DUAL_MODEL_B: "b"})
    _patch_parse(monkeypatch, {"a": [shared_a], "b": [shared_b, unique]})
    result = await l3.layer3_dual_model_deep("req", [], [], architect=object())
    by_content = {item.content: item for item in result}
    assert by_content["shared"] is shared_b
    assert shared_b.confidence == pytest.approx(0.9)
    assert shared_b.dual_model_agreement == "both_agree"
    assert shared_b.source == "llm_association:dual"
    assert by_content["unique"].dual_model_agreement == "needs_confirmation"
    assert unique.confidence == pytest.approx(max(0.9 * 0.95, 0.5))


def test_merge_dual_model_results_duplicate_in_same_model():
    first = _item("dup", confidence=0.5)
    second = _item("dup", confidence=0.9)
    merged = l3.merge_dual_model_results([first, second], [])
    assert len(merged) == 1
    assert merged[0] is first
    assert merged[0].dual_model_agreement == "needs_confirmation"


def test_merge_confidence_capped_and_floored():
    a = _item("hi", confidence=0.9)
    b = _item("hi", confidence=0.9)
    merged = l3.merge_dual_model_results([a], [b])
    assert merged[0].confidence == pytest.approx(0.95)

    single = _item("low", confidence=0.1)
    merged_single = l3.merge_dual_model_results([single], [])
    assert merged_single[0].confidence == pytest.approx(0.5)


def test_merge_keeps_higher_confidence_and_marks_agreement():
    a = _item("same", confidence=0.3)
    b = _item("same", confidence=0.4)
    merged = l3.merge_dual_model_results([a], [b])
    assert merged == [b]
    assert b.confidence == pytest.approx(0.5)
    assert b.dual_model_agreement == "both_agree"


def test_merge_different_text_same_prefix_groups_by_category_and_prefix():
    a = _item("x" * 60, confidence=0.6)
    b = _item("x" * 60 + "tail", confidence=0.6)
    merged = l3.merge_dual_model_results([a], [b])
    assert len(merged) == 1
    assert merged[0].dual_model_agreement == "both_agree"
