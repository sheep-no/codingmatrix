"""ErrorRecoveryLoop 分支补测：降级链、修复循环、错误上下文与测试日志修复。"""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import error_recovery as er_module
from app.agent.error_classifier import ErrorClassification
from app.agent.error_recovery import ErrorRecoveryLoop


class _Sem:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _loop(**kwargs):
    loop = ErrorRecoveryLoop(
        validator=kwargs.pop("validator", object()),
        reviewer=object(),
        **kwargs,
    )
    loop._semaphore = _Sem()
    return loop


def _classification(error_type="SyntaxError"):
    return ErrorClassification(
        error_type=error_type,
        error_subtype="sub",
        description="语法错误",
        suggested_fix_strategy="检查括号匹配",
        confidence=0.9,
    )


def _patch_classifier(monkeypatch, classification=None):
    async def fake_classify(*_args, **_kwargs):
        return classification or _classification()

    monkeypatch.setattr(er_module.error_classifier, "classify_error", fake_classify)


class TestFallbackChain:
    def test_user_preference_disabled_returns_empty(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            loop,
            "_get_user_fallback_preference",
            lambda: {"fallback_preference": "disabled"},
        )
        assert loop._load_fallback_chain() == []

    def test_user_preference_custom_chain_is_resolved(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            loop,
            "_get_user_fallback_preference",
            lambda: {"fallback_preference": "custom", "custom_fallback_chain": ["a", "b"]},
        )
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.resolve_model_key",
            lambda name: f"resolved-{name}",
        )
        assert loop._load_fallback_chain() == ["resolved-a", "resolved-b"]

    def test_custom_preference_without_chain_falls_through_to_config(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            loop,
            "_get_user_fallback_preference",
            lambda: {"fallback_preference": "custom", "custom_fallback_chain": []},
        )
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.load_agent_model_config",
            lambda: {"fallback_chains": {"error_recovery": ["c"]}},
        )
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.resolve_model_key",
            lambda name: f"resolved-{name}",
        )
        assert loop._load_fallback_chain() == ["resolved-c"]

    def test_config_without_chain_name_returns_empty(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(loop, "_get_user_fallback_preference", lambda: None)
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.load_agent_model_config",
            lambda: {"fallback_chains": {"other": ["x"]}},
        )
        assert loop._load_fallback_chain() == []

    def test_user_preference_lookup_returns_none_without_token(self):
        assert _loop(api_key_token=None)._get_user_fallback_preference() is None

    def test_user_preference_lookup_returns_manager_value(self, monkeypatch):
        class Manager:
            def get_fallback_preference_by_token(self, token):
                return {"fallback_preference": "disabled", "token": token}

        import app.services.apikey_manager as manager_module

        monkeypatch.setattr(manager_module, "get_apikey_manager", lambda: Manager())
        loop = _loop(api_key_token="tok")
        assert loop._get_user_fallback_preference()["token"] == "tok"

    def test_user_preference_lookup_swallows_errors(self, monkeypatch):
        import app.services.apikey_manager as manager_module

        monkeypatch.setattr(
            manager_module,
            "get_apikey_manager",
            lambda: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert _loop(api_key_token="tok")._get_user_fallback_preference() is None


class TestValidateAndFix:
    @pytest.mark.asyncio
    async def test_valid_content_returns_immediately(self, tmp_path):
        class Validator:
            async def validate_single_file(self, path):
                return {"is_valid": True}

        loop = _loop(validator=Validator())
        target = tmp_path / "main.py"
        target.write_text("print(1)\n", encoding="utf-8")

        ok, content = await loop.validate_and_fix(target, "print(1)\n", "desc", "m")
        assert ok is True
        assert content == "print(1)\n"

    @pytest.mark.asyncio
    async def test_invalid_content_enters_fix_loop(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                return {"is_valid": False, "syntax_errors": ["bad"]}

        loop = _loop(validator=Validator())
        target = tmp_path / "main.py"
        target.write_text("bad(\n", encoding="utf-8")

        async def fake_fix(**kwargs):
            return {"success": True, "fixed_content": "ok\n"}

        monkeypatch.setattr(loop, "_smart_fix_loop", fake_fix)
        ok, content = await loop.validate_and_fix(target, "bad(\n", "desc", "m")
        assert ok is True
        assert content == "ok\n"
        assert not (tmp_path / ".temp_main.py").exists()

    @pytest.mark.asyncio
    async def test_exception_is_wrapped_and_temp_file_removed(self, tmp_path):
        class Validator:
            async def validate_single_file(self, path):
                raise RuntimeError("validator exploded")

        loop = _loop(validator=Validator())
        target = tmp_path / "main.py"
        target.write_text("x\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="error recovery failed"):
            await loop.validate_and_fix(target, "x\n", "desc", "m")
        assert not (tmp_path / ".temp_main.py").exists()


class TestSmartFixLoop:
    @pytest.mark.asyncio
    async def test_cost_tracker_records_usage(self, tmp_path, monkeypatch):
        calls = []

        class Tracker:
            def add_usage(self, model, prompt_tokens, completion_tokens, cost_usd=0.0):
                calls.append((model, prompt_tokens, completion_tokens, cost_usd))

        loop = _loop(cost_tracker=Tracker())
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
        )

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": ""}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert calls and calls[0][0] == "m"

    @pytest.mark.asyncio
    async def test_fix_validation_error_with_strategy_records_failure(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                raise RuntimeError("validator down")

        loop = _loop(validator=Validator())
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: ("tmpl", "sid")
        )
        recorded = []
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "record_evaluation_result",
            lambda result: recorded.append(result),
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "fixed = 1\n"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert recorded[-1].success is False

    @pytest.mark.asyncio
    async def test_invalid_fix_with_strategy_records_failure(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                return {"is_valid": False, "syntax_errors": ["s"]}

        loop = _loop(validator=Validator())
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: ("tmpl", "sid")
        )
        recorded = []
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "record_evaluation_result",
            lambda result: recorded.append(result),
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "still bad\n"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert recorded[-2].success is False

    @pytest.mark.asyncio
    async def test_route_requiring_confirmation_skips_fix(self, tmp_path, monkeypatch):
        loop = _loop()
        _patch_classifier(monkeypatch, _classification("AssertionError"))

        result = await loop._smart_fix_loop(
            tmp_path / "main.py",
            "assert x\n",
            {"runtime_errors": ["AssertionError: 断言失败"]},
            "m",
        )
        assert result["success"] is False
        assert result["requires_confirmation"] is True
        assert result["repair_category"] == "test"

    @pytest.mark.asyncio
    async def test_budget_exhaustion_breaks_loop(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.repair_budget.total_limit = 0
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
        )

        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert result["budget_exhausted"] is True
        assert loop.fix_history[-1].attempts == 0

    @pytest.mark.asyncio
    async def test_cancel_event_stops_before_llm_call(self, tmp_path, monkeypatch):
        cancel = threading.Event()
        cancel.set()
        loop = _loop(cancel_event=cancel)
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
        )

        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert loop.fix_history[-1].attempts == 1

    @pytest.mark.asyncio
    async def test_empty_fix_response_continues_then_fails(self, tmp_path, monkeypatch):
        loop = _loop()
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: ("tmpl", "strategy-1")
        )
        recorded = []
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "record_evaluation_result",
            lambda result: recorded.append(result),
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": ""}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)

        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert loop.fix_history[-1].attempts == 3
        assert len(recorded) >= 3
        assert all(item.success is False for item in recorded)

    @pytest.mark.asyncio
    async def test_successful_fix_strips_fence_and_records_quality(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                return {"is_valid": True}

        loop = _loop(validator=Validator())
        loop.repair_budget.total_limit = 5
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: ("tmpl", "strategy-1")
        )
        recorded = []
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "record_evaluation_result",
            lambda result: recorded.append(result),
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "```python\nok = 1\n```"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        target = tmp_path / "main.py"

        result = await loop._smart_fix_loop(
            target, "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result == {"success": True, "fixed_content": "ok = 1"}
        assert loop.fix_history[-1].fix_applied is True
        assert recorded[0].success is True
        assert not list(tmp_path.glob(".temp_fix_*"))

    @pytest.mark.asyncio
    async def test_invalid_fix_collects_error_details_for_next_attempt(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                return {
                    "is_valid": False,
                    "syntax_errors": ["s"],
                    "import_errors": ["i"],
                    "runtime_errors": ["r"],
                    "api_errors": ["a"],
                    "frontend_errors": ["f"],
                }

        loop = _loop(validator=Validator())
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "still bad\n"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert loop.fix_history[-1].attempts == 1

    @pytest.mark.asyncio
    async def test_invalid_fix_without_details_uses_fallback_message(self, tmp_path, monkeypatch):
        class Validator:
            async def validate_single_file(self, path):
                return {"is_valid": False}

        loop = _loop(validator=Validator())
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
        )

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "still bad\n"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_llm_exception_is_swallowed_and_loop_ends(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator, "get_strategy_template", lambda _t: ("tmpl", "sid")
        )
        recorded = []
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "record_evaluation_result",
            lambda result: recorded.append(result),
        )

        async def boom(**_kwargs):
            raise RuntimeError("llm down")

        monkeypatch.setattr(er_module, "call_llm", boom)
        result = await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert result["success"] is False
        assert recorded[-1].success is False

    @pytest.mark.asyncio
    async def test_models_are_deduplicated_and_strategy_template_used(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m", "m2"]
        loop.repair_budget.total_limit = 1
        _patch_classifier(monkeypatch)
        monkeypatch.setattr(
            er_module.strategy_evaluator,
            "get_strategy_template",
            lambda _t: ("策略\n{error_context}", "sid"),
        )
        monkeypatch.setattr(er_module.strategy_evaluator, "record_evaluation_result", lambda _r: None)
        prompts = []

        async def fake_call_llm(**kwargs):
            prompts.append(kwargs["system_prompt"])
            return {"choices": [{"message": {"content": ""}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        await loop._smart_fix_loop(
            tmp_path / "main.py", "bad(\n", {"syntax_errors": ["bad"]}, "m"
        )
        assert "策略" in prompts[0]
        assert "{error_context}" in prompts[0]


class TestErrorContext:
    def test_unknown_errors_return_fallback_text(self):
        loop = _loop()
        assert loop._build_targeted_error_context({}, "", 0, _classification()) == (
            "## 错误类型\nSyntaxError: 语法错误\n**针对性修复建议**: 检查括号匹配"
        )

    def test_syntax_error_without_classification_hint(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"syntax_errors": ["line 1"]}, "", 0, _classification("ImportError")
        )
        assert "## 语法错误" in context
        assert "重点检查" not in context

    def test_syntax_error_adds_focus_hint(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"syntax_errors": ["line 1"]}, "", 0, _classification()
        )
        assert "括号匹配" in context

    def test_api_errors_without_known_hints_skip_suggestion_block(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"api_errors": ["random unrelated"]}, "", 0, _classification()
        )
        assert "## API 兼容性错误" in context
        assert "**修复建议**" not in context

    def test_frontend_errors_without_known_hints_skip_suggestion_block(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"frontend_errors": ["random unrelated"]}, "", 0, _classification()
        )
        assert "## 前端错误" in context
        assert "**修复建议**" not in context

    def test_runtime_errors_without_known_hints_skip_suggestion_block(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"runtime_errors": ["random unrelated"]}, "", 0, _classification()
        )
        assert "## 运行时错误" in context
        assert "**针对性修复建议**" not in context.split("## 运行时错误")[1]

    def test_dependency_error_adds_install_hint(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"dependency_errors": ["missing pkg"]}, "", 0, _classification()
        )
        assert "pip install" in context

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            ("passlib missing", "passlib.hash.bcrypt"),
            ("运行时导入失败: x", "检查导入路径"),
            ("属性错误", "API 是否与已安装版本兼容"),
            ("类型错误", "参数名和类型"),
        ],
    )
    def test_runtime_error_variants(self, error, expected):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"runtime_errors": [error]}, "", 0, _classification()
        )
        assert expected in context

    @pytest.mark.parametrize(
        ("error_type", "expected"),
        [
            ("NameError", "变量名拼写"),
            ("AttributeError", "确认对象类型"),
            ("TypeError", "参数数量和类型"),
        ],
    )
    def test_runtime_error_classification_specific_hints(self, error_type, expected):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"runtime_errors": ["属性错误"]}, "", 0, _classification(error_type)
        )
        assert expected in context

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            ("tokenUrl invalid", "token_url"),
            ("Middleware import", "CORSMiddleware"),
            ("MRO conflict", "SQLAlchemy"),
            ("exception_handler failed", "app.exception_handler"),
        ],
    )
    def test_api_error_variants(self, error, expected):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"api_errors": [error]}, "", 0, _classification()
        )
        assert expected in context

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            ("JS 语法错误", "JavaScript 语法"),
            ("HTML 结构错误", "标签是否正确闭合"),
            ("CSS 语法错误", "大括号匹配"),
        ],
    )
    def test_frontend_error_variants(self, error, expected):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"frontend_errors": [error]}, "", 0, _classification()
        )
        assert expected in context

    def test_cross_file_error_and_retry_note(self):
        loop = _loop()
        context = loop._build_targeted_error_context(
            {"cross_file_errors": ["mismatch"]}, "", 2, _classification()
        )
        assert "跨文件一致性错误" in context
        assert "此前已尝试修复 2 次" in context

    def test_template_without_placeholder_returns_base_context(self):
        loop = _loop()
        context = loop._build_targeted_error_context_with_template(
            {"syntax_errors": ["line 1"]}, "", 0, _classification(), "固定策略"
        )
        assert "固定策略" not in context
        assert "line 1" in context


class TestSelectFixModel:
    def test_config_mapping_recommended_model_is_used(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.load_agent_model_config",
            lambda: {"error_type_models": {"SyntaxError": "rec"}},
        )
        monkeypatch.setattr("app.agent.dynamic_model_router.resolve_model_key", lambda m: m)
        assert loop._select_fix_model_by_error_type("SyntaxError", ["a", "rec"], 0) == "rec"

    def test_unavailable_recommendation_falls_back_to_attempt_index(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.load_agent_model_config",
            lambda: {"error_type_models": {"SyntaxError": "rec"}},
        )
        monkeypatch.setattr("app.agent.dynamic_model_router.resolve_model_key", lambda m: m)
        assert loop._select_fix_model_by_error_type("SyntaxError", ["a", "b"], 3) == "b"

    def test_empty_model_list_raises(self, monkeypatch):
        loop = _loop()
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.load_agent_model_config", lambda: {}
        )
        with pytest.raises(RuntimeError, match="no models"):
            loop._select_fix_model_by_error_type("SyntaxError", [], 0)


class _Result:
    def __init__(self, success, failed=None, logs=""):
        self.success = success
        self.failed_tests = failed or []
        self.logs = logs


class _Runner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def run_tests(self):
        self.calls += 1
        return self.results.pop(0)


class TestFixFromTestLogs:
    @pytest.mark.asyncio
    async def test_no_failed_tests_short_circuits(self, tmp_path):
        loop = _loop()
        result = await loop.fix_from_test_logs(_Runner([]), [], "log", tmp_path)
        assert result == {"success": True, "message": "没有失败的测试"}

    @pytest.mark.asyncio
    async def test_empty_fallback_chain_returns_failure_summary(self, tmp_path):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = []
        result = await loop.fix_from_test_logs(_Runner([]), ["t"], "log", tmp_path)
        assert result["success"] is False
        assert result["failures"] == ["t"]

    @pytest.mark.asyncio
    async def test_fixes_are_applied_and_tests_pass(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        target = tmp_path / "app" / "service.py"
        target.parent.mkdir(parents=True)
        target.write_text("old = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "app/service.py", "content": "def new_value():\n    return 2\n"}
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        runner = _Runner([_Result(True)])
        result = await loop.fix_from_test_logs(runner, ["test_x"], "log", tmp_path)
        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "def new_value():\n    return 2\n"
        assert loop.fix_history[-1].fix_applied is True

    @pytest.mark.asyncio
    async def test_path_traversal_is_skipped(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        outside = tmp_path.parent / "outside_r17.py"
        outside.write_text("safe = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "../outside_r17.py", "content": "hacked = 1\n"}
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert outside.read_text(encoding="utf-8") == "safe = 1\n"
        assert loop.fix_history == []

    @pytest.mark.asyncio
    async def test_invalid_content_and_missing_fields_are_skipped(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        target = tmp_path / "app.py"
        target.write_text("old = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"content": "orphan = 1\n"},
                    {"file_path": "app.py", "content": ""},
                    {"file_path": "app.py", "content": '{"status": "ok"}'},
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "old = 1\n"

    @pytest.mark.asyncio
    async def test_non_list_response_is_wrapped(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        target = tmp_path / "app.py"
        target.write_text("old = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            payload = {"file_path": "app.py", "content": "def new_value():\n    return 2\n"}
            return {"choices": [{"message": {"content": "```json\n" + json.dumps(payload) + "\n```"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "def new_value():\n    return 2\n"

    @pytest.mark.asyncio
    async def test_write_failure_is_skipped(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        target = tmp_path / "app.py"
        target.write_text("old = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "app.py", "content": "def new_value():\n    return 2\n"}
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        import app.agent.utils as utils_module

        monkeypatch.setattr(utils_module, "write_file_atomic", lambda *_a, **_k: False)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert loop.fix_history == []

    @pytest.mark.asyncio
    async def test_fenced_content_is_unwrapped_before_write(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        target = tmp_path / "app.py"
        target.write_text("old = 1\n", encoding="utf-8")

        async def fake_call_llm(**_kwargs):
            code = "```python\ndef new_value():\n    return 2\n```"
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "app.py", "content": code}
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "def new_value():\n    return 2"

    @pytest.mark.asyncio
    async def test_missing_target_file_is_skipped(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]

        async def fake_call_llm(**_kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "missing.py", "content": "def new_value():\n    return 2\n"}
                ])}}],
            }

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        result = await loop.fix_from_test_logs(_Runner([_Result(True)]), ["t"], "log", tmp_path)
        assert result["success"] is True
        assert loop.fix_history == []

    @pytest.mark.asyncio
    async def test_failed_rerun_updates_logs_and_retries(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]
        prompts = []

        async def fake_call_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return {"choices": [{"message": {"content": "[]"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        runner = _Runner([
            _Result(False, failed=["t2"], logs="second log"),
            _Result(True),
        ])
        result = await loop.fix_from_test_logs(runner, ["t1"], "first log", tmp_path)
        assert result["success"] is True
        assert runner.calls == 2
        assert "second log" in prompts[1]
        assert "t2" in prompts[1]

    @pytest.mark.asyncio
    async def test_llm_exception_is_swallowed_and_loop_ends(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]

        async def boom(**_kwargs):
            raise RuntimeError("llm down")

        monkeypatch.setattr(er_module, "call_llm", boom)
        result = await loop.fix_from_test_logs(_Runner([]), ["t"], "log", tmp_path)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_all_attempts_fail_without_fixes(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "[]"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        runner = _Runner([_Result(False, failed=["t"], logs="log")] * 3)
        result = await loop.fix_from_test_logs(runner, ["t"], "log", tmp_path)
        assert result["success"] is False
        assert runner.calls == 3

    @pytest.mark.asyncio
    async def test_empty_failures_after_first_round_break(self, tmp_path, monkeypatch):
        loop = _loop()
        loop.MODEL_FALLBACK_CHAIN = ["m"]

        async def fake_call_llm(**_kwargs):
            return {"choices": [{"message": {"content": "[]"}}]}

        monkeypatch.setattr(er_module, "call_llm", fake_call_llm)
        runner = _Runner([_Result(False, failed=[], logs="log")])
        result = await loop.fix_from_test_logs(runner, ["t"], "log", tmp_path)
        assert result["success"] is False
        assert runner.calls == 1
