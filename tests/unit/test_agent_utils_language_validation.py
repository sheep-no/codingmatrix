import asyncio

import pytest

from app.agent import utils


@pytest.mark.asyncio
async def test_validate_language_with_llm_skips_timed_out_call(monkeypatch):
    call_cancelled = asyncio.Event()

    async def slow_llm_caller(_prompt):
        try:
            await asyncio.Event().wait()
        finally:
            call_cancelled.set()

    monkeypatch.setattr(utils, "LANGUAGE_VALIDATION_TIMEOUT_SECONDS", 0.01)

    is_valid, reason = await utils.validate_language_with_llm(
        file_path="main.py",
        content="def main():\n    return 'ready'\n",
        expected_language="Python",
        llm_caller=slow_llm_caller,
    )

    assert is_valid is True
    assert reason == ""
    assert call_cancelled.is_set()
