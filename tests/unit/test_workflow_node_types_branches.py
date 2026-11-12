"""Branch coverage for the LLM, conditional and HTTP workflow nodes."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from app.utils.workflow.node_types import (
    conditional as conditional_module,
    http_request as http_module,
    llm_call as llm_module,
)
from app.utils.workflow.node_types.base import NodeResult, TaskNodeBase
from app.utils.workflow.node_types.conditional import ConditionalNode
from app.utils.workflow.node_types.http_request import HTTPRequestNode
from app.utils.workflow.node_types.llm_call import LLMCallNode


class TestBaseNode:
    def test_repr_contains_node_id_and_type(self):
        node = ConditionalNode("c1", {})
        assert "ConditionalNode" in repr(node)
        assert "c1" in repr(node)

    def test_default_required_and_optional_params(self):
        class Minimal(TaskNodeBase):
            async def execute(self, context):
                return NodeResult.success_result(None)

            def validate_params(self):
                return []

        node = Minimal("m", {})
        assert node.get_required_params() == []
        assert node.get_optional_params() == {}

    def test_error_result_default_metadata(self):
        result = NodeResult.error_result("boom")
        assert result.success is False
        assert result.metadata == {}

    def test_default_metadata_created_when_none(self):
        result = NodeResult(success=True)
        assert result.metadata == {}


class TestLLMCallNode:
    def test_validate_prompt_missing(self):
        assert "Missing required parameter: prompt" in LLMCallNode("n", {}).validate_params()

    def test_validate_prompt_wrong_type(self):
        assert "Parameter 'prompt' must be a string" in LLMCallNode(
            "n", {"prompt": 1}
        ).validate_params()

    def test_validate_prompt_empty(self):
        assert "Parameter 'prompt' cannot be empty" in LLMCallNode(
            "n", {"prompt": "   "}
        ).validate_params()

    def test_validate_temperature_type_and_range(self):
        assert "Parameter 'temperature' must be a number" in LLMCallNode(
            "n", {"prompt": "x", "temperature": "hot"}
        ).validate_params()
        assert "Parameter 'temperature' must be between 0 and 2" in LLMCallNode(
            "n", {"prompt": "x", "temperature": 3}
        ).validate_params()

    def test_validate_max_tokens_type_and_range(self):
        assert "Parameter 'max_tokens' must be an integer" in LLMCallNode(
            "n", {"prompt": "x", "max_tokens": "many"}
        ).validate_params()
        assert "Parameter 'max_tokens' must be between 1 and 8192" in LLMCallNode(
            "n", {"prompt": "x", "max_tokens": 0}
        ).validate_params()
        assert "Parameter 'max_tokens' must be between 1 and 8192" in LLMCallNode(
            "n", {"prompt": "x", "max_tokens": 9000}
        ).validate_params()

    def test_optional_params_defaults(self):
        params = LLMCallNode("n", {"prompt": "x"}).get_optional_params()
        assert params["output_variable"] == "llm_result"
        assert params["max_tokens"] == 2048

    async def test_execute_success_with_string_response(self, monkeypatch):
        calls = {}

        async def fake_call_llm(**kwargs):
            calls.update(kwargs)
            return "hello"

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode(
            "n",
            {"prompt": "hi", "system_prompt": "sys", "temperature": 0.2, "max_tokens": 10},
        ).execute({})

        assert result.success is True
        assert result.data["content"] == "hello"
        assert calls["prompt"] == "sys\n\nhi"
        assert calls["temperature"] == 0.2

    async def test_execute_none_response_errors(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            return None

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.success is False
        assert "empty response" in result.error

    async def test_execute_object_with_choices(self, monkeypatch):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="obj"))]
        )

        async def fake_call_llm(**_kwargs):
            return response

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.data["content"] == "obj"

    async def test_execute_openai_dict_extracts_message(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "dict-content"}}]}

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.data["content"] == "dict-content"

    async def test_execute_dict_with_non_dict_choice_falls_through(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            return {"choices": ["bad"], "content": "fallback"}

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.data["content"] == "fallback"

    async def test_execute_dict_with_text_fallback(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            return {"text": "text-field"}

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.data["content"] == "text-field"

    async def test_execute_unknown_dict_serialized(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            return {"other": 1}

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert json.loads(result.data["content"]) == {"other": 1}

    @pytest.mark.parametrize(
        "prompt",
        [
            "summarize {{input}}",
            "summarize {{ input }}",
            "summarize {input}",
        ],
    )
    async def test_input_variable_replaces_placeholders(self, monkeypatch, prompt):
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        await LLMCallNode(
            "n", {"prompt": prompt, "input_variable": "input"}
        ).execute({"input": {"a": 1}})

        assert captured["prompt"].startswith("summarize")
        assert '"a": 1' in captured["prompt"]
        assert "{{input}}" not in captured["prompt"]

    async def test_input_variable_appended_when_no_placeholder(self, monkeypatch):
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        await LLMCallNode(
            "n", {"prompt": "go", "input_variable": "input"}
        ).execute({"input": [1, 2]})

        assert captured["prompt"].startswith("go\n\n")
        assert "1" in captured["prompt"] and "2" in captured["prompt"]

    async def test_input_variable_missing_from_context_is_ignored(self, monkeypatch):
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)

        await LLMCallNode(
            "n", {"prompt": "prompt {input}", "input_variable": "input"}
        ).execute({})

        assert captured["prompt"] == "prompt {input}"

    async def test_execute_failure_returns_error_result(self, monkeypatch):
        async def fake_call_llm(**_kwargs):
            raise RuntimeError("down")

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)
        fake_logger = MagicMock()
        monkeypatch.setattr(llm_module, "logger", fake_logger)

        result = await LLMCallNode("n", {"prompt": "hi"}).execute({})

        assert result.success is False
        assert "LLM call failed: down" in result.error
        assert fake_logger.error.called


class TestConditionalValidation:
    def test_requires_expression_or_variable(self):
        assert "Either 'expression' or 'variable' must be provided" in ConditionalNode(
            "c", {}
        ).validate_params()

    def test_rejects_unknown_variable_operator(self):
        errors = ConditionalNode("c", {"variable": "v", "operator": "~"}).validate_params()
        assert any("Unsupported operator" in e for e in errors)

    def test_true_and_false_branch_must_be_lists(self):
        errors = ConditionalNode(
            "c", {"variable": "v", "true_branch": "a", "false_branch": "b"}
        ).validate_params()
        assert "Parameter 'true_branch' must be a list" in errors
        assert "Parameter 'false_branch' must be a list" in errors

    def test_optional_defaults(self):
        params = ConditionalNode("c", {}).get_optional_params()
        assert params["operator"] == "=="
        assert params["true_branch"] == []


class TestConditionalExecute:
    @pytest.mark.parametrize(
        ("op", "var", "compare", "expected"),
        [
            ("==", 1, "1", True),
            ("!=", 1, "2", True),
            (">", 5, "3", True),
            (">=", 3, "3", True),
            ("<", 1, "2", True),
            ("<=", 2, "2", True),
            ("in", "a", "abc", True),
            ("not_in", "z", "abc", True),
            ("contains", "abc", "b", True),
            ("is_empty", "", None, True),
            ("is_not_empty", "x", None, True),
            ("starts_with", "abc", "a", True),
            ("ends_with", "abc", "c", True),
        ],
    )
    async def test_variable_operators(self, op, var, compare, expected):
        result = await ConditionalNode(
            "c",
            {
                "variable": "v",
                "operator": op,
                "value": compare,
                "true_branch": ["t"],
                "false_branch": ["f"],
            },
        ).execute({"v": var})

        assert result.success is True
        assert result.data["condition_result"] is expected
        assert result.data["branch_path"] == (["t"] if expected else ["f"])

    async def test_unknown_operator_at_execute_time(self):
        result = await ConditionalNode(
            "c", {"variable": "v", "operator": "nope"}
        ).execute({"v": 1})

        assert result.success is False
        assert "Unsupported operator" in result.error

    async def test_no_condition_returns_error(self):
        result = await ConditionalNode("c", {}).execute({})
        assert result.success is False
        assert result.error == "No condition specified"

    async def test_expression_mode(self):
        result = await ConditionalNode(
            "c", {"expression": "{count} > 3", "true_branch": ["t"]}
        ).execute({"count": 5})

        assert result.data["condition_result"] is True
        assert result.data["branch_path"] == ["t"]

    async def test_expression_evaluation_error_is_wrapped(self):
        result = await ConditionalNode(
            "c", {"expression": "import os"}
        ).execute({})

        assert result.success is False
        assert "Forbidden keyword" in result.error

    async def test_unexpected_exception_is_wrapped(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("kaboom")

        node = ConditionalNode("c", {"expression": "1 == 1"})
        monkeypatch.setattr(node, "_evaluate_expression", boom)

        result = await node.execute({})

        assert result.success is False
        assert "Conditional evaluation failed: kaboom" in result.error


class TestCoerceValue:
    def test_none_short_circuits(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value(None, "x") == "x"
        assert node._coerce_value("x", None) is None

    def test_int_float_bool_convert(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value(1, "5") == 5
        assert node._coerce_value(1.5, "2.5") == 2.5
        assert node._coerce_value(True, "yes") is True
        assert node._coerce_value(True, "no") is False

    def test_list_from_json(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value([1], "[2, 3]") == [2, 3]

    def test_conversion_error_keeps_original(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value(1, "not-a-number") == "not-a-number"
        assert node._coerce_value([1], "not-json") == "not-json"

    def test_non_string_compare_for_list_keeps_value(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value([1], 5) == 5

    def test_string_variable_keeps_compare_value(self):
        node = ConditionalNode("c", {})
        assert node._coerce_value("x", 5) == 5


class TestSafeEval:
    def test_allows_arithmetic_and_booleans(self):
        node = ConditionalNode("c", {})
        assert node._safe_eval("(1 + 2 * 3) > 5 and not False") is True

    def test_rejects_function_calls(self):
        node = ConditionalNode("c", {})
        with pytest.raises(ValueError):
            node._safe_eval("len('x')")

    def test_rejects_attribute_access(self):
        node = ConditionalNode("c", {})
        with pytest.raises(ValueError):
            node._safe_eval("x.y")

    def test_rejects_syntax_errors(self):
        node = ConditionalNode("c", {})
        with pytest.raises(Exception):
            node._safe_eval("1 +")


class _Response:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = httpx.Headers(headers or {})

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("bad", "doc", 0)
        return self._payload


class _Client:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, **kwargs):
        self.calls.append(kwargs)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _patch_http_client(monkeypatch, responses, safe_url=True):
    client = _Client(responses)
    monkeypatch.setattr(http_module.httpx, "AsyncClient", lambda *a, **k: client)
    monkeypatch.setattr(
        HTTPRequestNode, "_check_ssrf", lambda self, url, strict=False: None
    )
    return client


class TestHttpValidation:
    def test_missing_url(self):
        assert "Missing required parameter: url" in HTTPRequestNode("h", {}).validate_params()

    def test_url_wrong_type(self):
        assert "Parameter 'url' must be a string" in HTTPRequestNode(
            "h", {"url": 1}
        ).validate_params()

    def test_url_scheme_rejected(self):
        assert "Parameter 'url' must start with http:// or https://" in HTTPRequestNode(
            "h", {"url": "ftp://x"}
        ).validate_params()

    def test_ssrf_error_reported(self, monkeypatch):
        monkeypatch.setattr(
            HTTPRequestNode, "_check_ssrf", lambda self, url, strict=False: "blocked"
        )
        assert HTTPRequestNode("h", {"url": "http://x"}).validate_params() == ["blocked"]

    def test_unsupported_method(self):
        assert "Unsupported HTTP method: TRACE" in HTTPRequestNode(
            "h", {"url": "http://x", "method": "trace"}
        ).validate_params()

    def test_timeout_type_and_range(self):
        assert "Parameter 'timeout' must be a number" in HTTPRequestNode(
            "h", {"url": "http://x", "timeout": "slow"}
        ).validate_params()
        assert "Parameter 'timeout' must be between 1 and 120" in HTTPRequestNode(
            "h", {"url": "http://x", "timeout": 0}
        ).validate_params()
        assert "Parameter 'timeout' must be between 1 and 120" in HTTPRequestNode(
            "h", {"url": "http://x", "timeout": 121}
        ).validate_params()

    def test_ssrf_check_logs_warning(self, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(http_module, "logger", fake_logger)
        monkeypatch.setattr(http_module, "check_outbound_url", lambda url, **kw: "denied")

        assert HTTPRequestNode("h", {})._check_ssrf("http://x") == "denied"
        assert fake_logger.warning.called


class TestHttpExecute:
    async def test_success_json_response_filters_sensitive_headers(self, monkeypatch):
        client = _patch_http_client(
            monkeypatch,
            [
                _Response(
                    status_code=200,
                    payload={"ok": True},
                    headers={
                        "Content-Type": "application/json",
                        "Set-Cookie": "secret",
                        "Authorization": "secret",
                    },
                )
            ],
        )

        result = await HTTPRequestNode(
            "h", {"url": "http://example.test/api", "output_variable": "out"}
        ).execute({"v": 1})

        assert result.success is True
        assert result.data["status_code"] == 200
        assert result.data["data"] == {"ok": True}
        assert result.data["headers"] == {"content-type": "application/json"}
        assert client.calls[0]["url"] == "http://example.test/api"

    async def test_non_json_response_falls_back_to_text(self, monkeypatch):
        _patch_http_client(
            monkeypatch, [_Response(status_code=200, payload=None, text="plain")]
        )

        result = await HTTPRequestNode("h", {"url": "http://x"}).execute({})

        assert result.data["data"] == "plain"

    async def test_non_2xx_response_is_error(self, monkeypatch):
        _patch_http_client(
            monkeypatch, [_Response(status_code=404, payload={"error": "gone"})]
        )

        result = await HTTPRequestNode("h", {"url": "http://x"}).execute({})

        assert result.success is False
        assert "HTTP 404" in result.error
        assert result.metadata["status_code"] == 404

    async def test_ssrf_recheck_rejects_after_variable_substitution(self, monkeypatch):
        monkeypatch.setattr(
            HTTPRequestNode, "_check_ssrf", lambda self, url, strict=False: "internal"
        )

        result = await HTTPRequestNode(
            "h", {"url": "http://{host}"}
        ).execute({"host": "127.0.0.1"})

        assert result.success is False
        assert "URL 安全校验未通过" in result.error

    async def test_body_and_params_variables_replaced(self, monkeypatch):
        client = _patch_http_client(monkeypatch, [_Response(payload={})])

        await HTTPRequestNode(
            "h",
            {
                "url": "http://x/{v}",
                "method": "post",
                "body": {"k": "{v}"},
                "params": {"p": "{v}"},
            },
        ).execute({"v": "1"})

        call = client.calls[0]
        assert call["method"] == "POST"
        assert call["url"] == "http://x/1"
        assert call["json"] == {"k": "{v}"}
        assert call["params"] == {"p": "1"}

    async def test_string_body_goes_to_content(self, monkeypatch):
        client = _patch_http_client(monkeypatch, [_Response(payload={})])

        await HTTPRequestNode(
            "h", {"url": "http://x", "method": "POST", "body": "text-{v}"}
        ).execute({"v": "1"})

        assert client.calls[0]["content"] == "text-1"
        assert client.calls[0]["json"] is None

    async def test_timeout_returns_error(self, monkeypatch):
        _patch_http_client(
            monkeypatch, [httpx.ReadTimeout("slow")]
        )

        result = await HTTPRequestNode("h", {"url": "http://x", "timeout": 5}).execute({})

        assert result.success is False
        assert "timeout after 5s" in result.error

    async def test_unexpected_error_returns_error(self, monkeypatch):
        _patch_http_client(monkeypatch, [RuntimeError("explode")])

        result = await HTTPRequestNode("h", {"url": "http://x"}).execute({})

        assert result.success is False
        assert "HTTP request failed: explode" in result.error

    async def test_redirects_followed_up_to_target(self, monkeypatch):
        client = _patch_http_client(
            monkeypatch,
            [
                _Response(status_code=302, headers={"location": "/next"}),
                _Response(status_code=200, payload={"done": True}),
            ],
        )

        result = await HTTPRequestNode("h", {"url": "http://example.test/start"}).execute({})

        assert result.success is True
        assert client.calls[1]["url"] == "http://example.test/next"

    async def test_redirect_without_location_returns_response(self, monkeypatch):
        _patch_http_client(monkeypatch, [_Response(status_code=302, payload={})])

        result = await HTTPRequestNode("h", {"url": "http://example.test/start"}).execute({})

        assert result.success is False
        assert result.data is None
        assert result.metadata["status_code"] == 302

    async def test_redirect_target_rejected(self, monkeypatch):
        call_count = {"n": 0}

        def check(self, url, strict=False):
            call_count["n"] += 1
            # Allow the initial URL, reject the redirect target.
            return None if call_count["n"] == 1 else "blocked"

        monkeypatch.setattr(HTTPRequestNode, "_check_ssrf", check)
        monkeypatch.setattr(
            http_module.httpx,
            "AsyncClient",
            lambda *a, **k: _Client(
                [_Response(status_code=302, headers={"location": "http://internal.test"})]
            ),
        )

        result = await HTTPRequestNode("h", {"url": "http://public.test"}).execute({})

        assert result.success is False
        assert "重定向目标被拒绝" in result.error

    async def test_303_downgrades_to_get_and_drops_body(self, monkeypatch):
        client = _patch_http_client(
            monkeypatch,
            [
                _Response(status_code=303, headers={"location": "/next"}),
                _Response(payload={}),
            ],
        )

        await HTTPRequestNode(
            "h",
            {"url": "http://example.test/start", "method": "POST", "body": "text"},
        ).execute({})

        second = client.calls[1]
        assert second["method"] == "GET"
        assert "content" not in second
        assert "json" not in second

    async def test_301_post_downgrades_to_get(self, monkeypatch):
        client = _patch_http_client(
            monkeypatch,
            [
                _Response(status_code=301, headers={"location": "/next"}),
                _Response(payload={}),
            ],
        )

        await HTTPRequestNode(
            "h",
            {"url": "http://example.test/start", "method": "POST", "body": {"a": 1}},
        ).execute({})

        assert client.calls[1]["method"] == "GET"
        assert "json" not in client.calls[1]

    async def test_307_post_is_preserved(self, monkeypatch):
        client = _patch_http_client(
            monkeypatch,
            [
                _Response(status_code=307, headers={"location": "/next"}),
                _Response(payload={}),
            ],
        )

        await HTTPRequestNode(
            "h", {"url": "http://example.test/start", "method": "POST", "body": {"a": 1}}
        ).execute({})

        assert client.calls[1]["method"] == "POST"
        assert client.calls[1]["json"] == {"a": 1}

    async def test_too_many_redirects_returns_error(self, monkeypatch):
        responses = [
            _Response(status_code=302, headers={"location": "/next"})
            for _ in range(6)
        ]
        _patch_http_client(monkeypatch, responses)

        result = await HTTPRequestNode("h", {"url": "http://example.test"}).execute({})

        assert result.success is False
        assert "重定向次数超过上限" in result.error


class TestReplaceVariables:
    def test_non_string_input_passthrough(self):
        assert HTTPRequestNode("h", {})._replace_variables(5, {}) == 5

    def test_string_value_substitution(self):
        assert HTTPRequestNode("h", {})._replace_variables(
            "a={a}", {"a": 1}
        ) == "a=1"

    def test_container_value_serialized(self):
        assert HTTPRequestNode("h", {})._replace_variables(
            "a={a}", {"a": [1, 2]}
        ) == "a=[1, 2]"

    def test_missing_placeholder_untouched(self):
        assert HTTPRequestNode("h", {})._replace_variables("x", {"a": 1}) == "x"


class TestRemainingNodeBranches:
    def test_conditional_required_and_optional_params(self):
        node = ConditionalNode("c", {})
        assert node.get_required_params() == []
        assert "expression" in node.get_optional_params()

    def test_conditional_validate_accepts_list_branches(self):
        node = ConditionalNode(
            "c",
            {"variable": "x", "true_branch": [], "false_branch": []},
        )
        assert node.validate_params() == []

    async def test_conditional_expression_skips_non_scalar_context(self):
        result = await ConditionalNode(
            "c", {"expression": "{b} == True"}
        ).execute({"a": {"nested": 1}, "b": True})
        assert result.success is True
        assert result.data["condition_result"] is True

    async def test_conditional_expression_eval_failure_wrapped(self):
        result = await ConditionalNode(
            "c", {"expression": "{a} > 3"}
        ).execute({"a": "text"})
        assert result.success is False
        assert "Expression evaluation failed" in result.error

    def test_llm_required_and_optional_params(self):
        node = LLMCallNode("n", {"prompt": "x"})
        assert node.get_required_params() == ["prompt"]
        assert node.get_optional_params()["model"]

    def test_llm_validate_valid_temperature_and_max_tokens(self):
        node = LLMCallNode("n", {"prompt": "x", "temperature": 0.5, "max_tokens": 10})
        assert node.validate_params() == []

    async def test_llm_scalar_input_substituted(self, monkeypatch):
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)
        await LLMCallNode(
            "n", {"prompt": "v={input}", "input_variable": "v"}
        ).execute({"v": 42})
        assert captured["prompt"] == "v=42"

    def test_http_required_and_optional_params(self):
        node = HTTPRequestNode("h", {"url": "http://example.test"})
        assert node.get_required_params() == ["url"]
        assert node.get_optional_params()["method"] == "GET"

    def test_http_validate_unsupported_method_and_valid_timeout(self):
        node = HTTPRequestNode(
            "h", {"url": "http://example.test", "method": "TRACE", "timeout": 10}
        )
        assert any("Unsupported HTTP method" in e for e in node.validate_params())

    def test_http_validate_supported_method(self):
        node = HTTPRequestNode("h", {"url": "http://example.test", "method": "post"})
        assert node.validate_params() == []

    def test_base_abstract_defaults_reachable_via_super(self):
        class Concrete(TaskNodeBase):
            async def execute(self, context):
                return await super().execute(context)

            def validate_params(self):
                return super().validate_params()

        node = Concrete("x", {})
        assert asyncio.run(node.execute({})) is None
        assert node.validate_params() is None
