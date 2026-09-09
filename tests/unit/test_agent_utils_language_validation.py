import asyncio

import pytest

from app.agent import utils


@pytest.mark.parametrize(
    ("label", "file_path"),
    (("app/main.py", "app/main.py"), ("File: src/app.ts", "src/app.ts")),
)
def test_strip_leading_file_label(label, file_path):
    content = f"{label}\nprint('ready')\n"

    assert utils.strip_leading_file_label(content, file_path) == "print('ready')\n"


def test_strip_leading_file_label_preserves_regular_first_line():
    content = "from pathlib import Path\n"

    assert utils.strip_leading_file_label(content, "app/main.py") == content


def test_extract_rejects_tool_call_json_before_persistence(tmp_path):
    content = '{"tool":"read_file","params":{"path":"app/models.py"}}'
    assert utils.is_placeholder_content(content, "app/models.py")[0] is True


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
