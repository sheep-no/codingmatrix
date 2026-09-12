import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.orchestrator_generation.mixin import GenerationMixin


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "incremental,spec_first,expected",
    [
        (True, True, "incremental"),
        (True, False, "incremental"),
        (False, True, "spec_first"),
        (False, False, "traditional"),
    ],
)
async def test_generate_dispatches_incremental_before_spec_first(incremental, spec_first, expected):
    calls = []

    async def evaluate(requirement):
        calls.append("evaluate")
        return {"mode": "evaluate"}

    async def generate_incremental(requirement, callback=None):
        calls.append("incremental")
        return {"mode": "incremental"}

    async def generate_with_spec_first(requirement, callback=None):
        calls.append("spec_first")
        return {"mode": "spec_first"}

    async def generate_traditional(requirement):
        calls.append("traditional")
        return {"mode": "traditional"}

    agent = SimpleNamespace(
        evaluation_only=False,
        incremental=incremental,
        spec_first=spec_first,
        callback=None,
        evaluate=evaluate,
        generate_incremental=generate_incremental,
        generate_with_spec_first=generate_with_spec_first,
        _generate_traditional=generate_traditional,
    )

    result = await GenerationMixin.generate(agent, "fix snake collision")

    assert result["mode"] == expected
    assert calls == [expected]


@pytest.mark.asyncio
async def test_generate_keeps_evaluation_only_ahead_of_incremental():
    evaluate = AsyncMock(return_value={"mode": "evaluate"})
    generate_incremental = AsyncMock(return_value={"mode": "incremental"})
    agent = SimpleNamespace(
        evaluation_only=True,
        incremental=True,
        spec_first=True,
        callback=None,
        evaluate=evaluate,
        generate_incremental=generate_incremental,
    )

    result = await GenerationMixin.generate(agent, "score a project")

    assert result["mode"] == "evaluate"
    evaluate.assert_awaited_once()
    generate_incremental.assert_not_awaited()
