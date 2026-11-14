"""补齐 refinement_loop 的校验分派、Pydantic 判定与进度回调。"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.agent.refinement_loop import RefinementLoop, ValidationIssue
from app.agent.shared_context import SharedContext


@pytest.fixture
def loop():
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = SharedContext("requirement", Path(tmpdir))
        ctx.model_assignment = {"backend_model": "test-model"}
        yield RefinementLoop(ctx)


class TestValidationDispatch:
    @pytest.mark.asyncio
    async def test_json_syntax_error(self, loop):
        issues = await loop._validate_code("a.json", '{"a": }', "frontend")

        assert issues
        assert "JSON 语法错误" in issues[0].message
        assert issues[0].line

    @pytest.mark.asyncio
    async def test_valid_json_passes(self, loop):
        assert await loop._validate_code("a.json", '{"a": 1}', "frontend") == []

    @pytest.mark.asyncio
    async def test_unknown_extension_is_ignored(self, loop):
        assert await loop._validate_code("a.txt", "def broken(:", "backend") == []

    @pytest.mark.asyncio
    async def test_empty_vue_script_is_ignored(self, loop):
        assert await loop._validate_code("a.vue", "<template><div/></template>", "frontend") == []


class TestPydanticDetection:
    def test_syntax_error_returns_false(self):
        assert RefinementLoop._uses_pydantic_model("def broken(:") is False

    def test_plain_import(self):
        assert RefinementLoop._uses_pydantic_model("import pydantic\n") is True

    def test_unrelated_import(self):
        assert RefinementLoop._uses_pydantic_model("import os\nfrom json import dumps\n") is False

    def test_attribute_base(self):
        source = "class User(orm.BaseModel):\n    pass\n"

        assert RefinementLoop._uses_pydantic_model(source) is True

    def test_settings_name_base(self):
        assert RefinementLoop._uses_pydantic_model("class C(BaseSettings):\n    pass\n") is True

    def test_other_base_name(self):
        assert RefinementLoop._uses_pydantic_model("class C(object):\n    pass\n") is False


class TestSpecConsistencyBranches:
    @pytest.mark.asyncio
    async def test_api_file_without_openapi_spec(self, loop):
        assert await loop._validate_code("a.py", "router = 1\n", "api") == []

    @pytest.mark.asyncio
    async def test_model_file_without_types_code(self, loop):
        loop.context.save_spec("types", {"code": ""}, "m")

        assert await loop._validate_code("m.py", "x = 1\n", "model") == []

    @pytest.mark.asyncio
    async def test_api_file_skips_types_check(self, loop):
        loop.context.save_spec("types", {"code": "x"}, "m")

        assert await loop._validate_code("a.py", "x = 1\n", "api") == []


class TestErrorSummary:
    def test_empty_issues(self, loop):
        assert loop._build_error_summary([]) == "没有发现错误"

    def test_issue_without_suggestion_or_line(self, loop):
        issue = ValidationIssue(type="logic", severity="error", message="bad")

        summary = loop._build_error_summary([issue], "code")

        assert "logic" in summary
        assert "建议" not in summary
        assert "代码上下文" not in summary

    def test_line_outside_code_has_no_context(self, loop):
        issue = ValidationIssue(type="syntax", severity="error", message="bad", line=99)

        summary = loop._build_error_summary([issue], "a\nb")

        assert "代码上下文" not in summary

    def test_context_marks_error_line(self, loop):
        issue = ValidationIssue(
            type="syntax",
            severity="error",
            message="bad",
            line=2,
            suggestion="fix it",
        )

        summary = loop._build_error_summary([issue], "a\nb\nc")

        assert ">>>" in summary
        assert "建议: fix it" in summary


class TestRefineBranches:
    @pytest.mark.asyncio
    async def test_unchanged_fix_keeps_remaining_issues(self, loop, monkeypatch):
        from app.agent import refinement_loop as module

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": "def f(:\n"}}]}

        monkeypatch.setattr(module, "call_llm", fake_call_llm)

        result = await loop.refine(
            "bad.py", "backend", "d", "def f(:\n", model_name="test-model"
        )

        assert result.success is False
        assert result.remaining_issues

    @pytest.mark.asyncio
    async def test_llm_exception_consumes_attempt(self, loop, monkeypatch):
        from app.agent import refinement_loop as module

        calls = {"count": 0}

        async def fake_call_llm(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            return {"choices": [{"message": {"content": "def f():\n    return 1\n"}}]}

        monkeypatch.setattr(module, "call_llm", fake_call_llm)

        result = await loop.refine(
            "bad.py", "backend", "d", "def f(:\n", model_name="test-model"
        )

        assert result.success is True
        assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_zero_attempts_returns_fallback(self, loop):
        loop.MAX_ATTEMPTS = 0

        result = await loop.refine(
            "bad.py", "backend", "d", "def f(:\n", model_name="test-model"
        )

        assert result.success is False
        assert result.attempts == 0
        assert result.remaining_issues == []


class TestProgressCallback:
    def test_sync_callback(self, loop):
        received = []

        loop._report_progress("a.py", 1, received.append)

        assert '"type": "refinement_progress"' in received[0]

    @pytest.mark.asyncio
    async def test_async_callback_is_scheduled(self, loop):
        received = []

        async def callback(payload):
            received.append(payload)

        loop._report_progress("a.py", 2, callback)
        await asyncio.gather(*loop._pending_tasks)

        assert received

    def test_callback_exception_is_logged(self, loop, monkeypatch):
        from app.agent import refinement_loop as module

        errors = []
        monkeypatch.setattr(module.logger, "error", lambda *a, **k: errors.append(a))

        def boom(_payload):
            raise RuntimeError("callback failed")

        loop._report_progress("a.py", 1, boom)

        assert errors
