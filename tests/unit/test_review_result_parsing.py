"""
测试 multi_model_agent 的 Pydantic 强约束与降级检测。

覆盖：
- ReviewResult 字段类型强约束
- TaskStep 字段类型强约束
- ArchitectJsonParser + Pydantic 集成
- review_code / review_plan / decompose 在 LLM 响应异常时的行为
- review_plan 对 plan 中降级步骤的强制 high 逻辑
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.agent.multi_model_agent import (
    ReviewResult,
    TaskStep,
    _degrade_step,
    AIReviewer,
    TaskPlanner,
)
from app.agent.architect_json_parser import ArchitectJsonParser


def _llm_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class TestReviewResultPydantic:
    def test_standard(self):
        r = ReviewResult.model_validate({
            "approved": True,
            "issues": ["i1"],
            "suggestions": ["s1"],
            "risk_level": "low",
        })
        assert r.approved is True
        assert r.issues == ["i1"]
        assert r.risk_level == "low"

    def test_missing_approved_raises(self):
        with pytest.raises(ValidationError):
            ReviewResult.model_validate({"risk_level": "low"})

    def test_approved_string_rejected(self):
        with pytest.raises(ValidationError):
            ReviewResult.model_validate({"approved": "yes", "risk_level": "low"})

    def test_risk_level_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            ReviewResult.model_validate({"approved": True, "risk_level": "critical"})

    def test_risk_level_valid_values(self):
        for level in ("low", "medium", "high"):
            r = ReviewResult.model_validate({"approved": True, "risk_level": level})
            assert r.risk_level == level

    def test_issues_not_list_rejected(self):
        with pytest.raises(ValidationError):
            ReviewResult.model_validate({"approved": True, "issues": "not a list"})


class TestTaskStepPydantic:
    def test_standard(self):
        s = TaskStep.model_validate({
            "type": "ai_call",
            "description": "do x",
            "params": {"task": "x"},
        })
        assert s.degraded is False
        assert s.type == "ai_call"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            TaskStep.model_validate({"type": "explode", "description": "x", "params": {}})

    def test_degraded_step(self):
        s = TaskStep.model_validate({
            "type": "ai_call",
            "description": "降级",
            "params": {},
            "degraded": True,
        })
        assert s.degraded is True

    def test_model_dump_roundtrip(self):
        s = TaskStep.model_validate({"type": "ai_call", "description": "x", "params": {}})
        d = s.model_dump()
        assert d["type"] == "ai_call"
        assert d["degraded"] is False


class TestArchitectJsonParserIntegration:
    def _parse(self, text: str):
        return ArchitectJsonParser().safe_parse_json(text)

    def test_plain_json(self):
        parsed = self._parse('{"approved": true, "risk_level": "low"}')
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_markdown_code_block(self):
        text = '```json\n{"approved": true, "risk_level": "low"}\n```'
        parsed = self._parse(text)
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_thinking_tags(self):
        text = '<think>thinking</think>\n{"approved": true, "risk_level": "low"}'
        parsed = self._parse(text)
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_surrounding_text(self):
        text = '好的，审查结果：\n{"approved": true, "risk_level": "low"}\n以上。'
        parsed = self._parse(text)
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_garbage_raises_value_error(self):
        with pytest.raises(ValueError):
            self._parse("not json at all")

    def test_trailing_comma_repaired(self):
        parsed = self._parse('{"approved": true, "risk_level": "low",}')
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_single_quote_repaired(self):
        parsed = self._parse("{'approved': true, 'risk_level': 'low'}")
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_partial_json_repaired(self):
        parsed = self._parse('{"approved": true, "risk_level": "low"')
        r = ReviewResult.model_validate(parsed)
        assert r.approved is True

    def test_json_array(self):
        parsed = self._parse('[{"type": "ai_call", "description": "x", "params": {}}]')
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_partial_brace_nested(self):
        parsed = self._parse('{"a": 1, "b": {"c":')
        assert parsed == {"a": 1, "b": {"c": None}}

    def test_partial_brace_deeply_nested(self):
        parsed = self._parse('{"a": {"b": {"c":')
        assert parsed == {"a": {"b": {"c": None}}}

    def test_unclosed_string(self):
        parsed = self._parse('{"a": "unclosed')
        assert parsed == {"a": "unclosed"}

    def test_key_only_truncated(self):
        parsed = self._parse('{"a":')
        assert parsed == {"a": None}

    def test_array_partial_nested(self):
        parsed = self._parse('[1, 2, {"a":')
        assert parsed == [1, 2, {"a": None}]

    def test_json_repair_handles_js_comments(self):
        parsed = self._parse('{/* comment */ "a": 1}')
        assert parsed == {"a": 1}

    def test_json_repair_handles_unquoted_keys(self):
        parsed = self._parse('{a: 1, b: 2}')
        assert parsed == {"a": 1, "b": 2}

    def test_pure_garbage_raises(self):
        with pytest.raises(ValueError):
            self._parse("no json at all here")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            self._parse("")


class TestDegradeStep:
    def test_shape(self):
        s = _degrade_step("my task", "test reason")
        assert s["type"] == "ai_call"
        assert s["degraded"] is True
        assert "降级执行" in s["description"]
        assert "test reason" in s["description"]
        assert s["params"]["task"] == "my task"


class TestReviewCodeParsing:
    async def test_garbage_response_rejected(self):
        reviewer = AIReviewer()
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response("not json at all")
            result = await reviewer.review_code("some code")
        assert result.approved is False
        assert result.risk_level == "medium"
        assert "JSON" in result.issues[0] or "解析" in result.issues[0]

    async def test_wrong_type_approved_rejected(self):
        reviewer = AIReviewer()
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": "yes", "risk_level": "low"})
            )
            result = await reviewer.review_code("some code")
        assert result.approved is False
        assert result.risk_level == "medium"
        assert "schema" in result.issues[0]

    async def test_invalid_risk_level_rejected(self):
        reviewer = AIReviewer()
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": True, "risk_level": "critical"})
            )
            result = await reviewer.review_code("some code")
        assert result.approved is False
        assert result.risk_level == "medium"

    async def test_valid_response_passes(self):
        reviewer = AIReviewer()
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": True, "risk_level": "low", "issues": [], "suggestions": []})
            )
            result = await reviewer.review_code("some code")
        assert result.approved is True
        assert result.risk_level == "low"


class TestReviewPlanParsing:
    async def test_garbage_response_rejected_not_released(self):
        reviewer = AIReviewer()
        plan = [{"type": "ai_call", "description": "x", "params": {}}]
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response("totally not json")
            result = await reviewer.review_plan(plan)
        assert result.approved is False
        assert result.risk_level == "high"

    async def test_wrong_type_approved_rejected(self):
        reviewer = AIReviewer()
        plan = [{"type": "ai_call", "description": "x", "params": {}}]
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": "yes", "risk_level": "low"})
            )
            result = await reviewer.review_plan(plan)
        assert result.approved is False
        assert result.risk_level == "high"

    async def test_normal_plan_keeps_llm_decision(self):
        reviewer = AIReviewer()
        plan = [{"type": "ai_call", "description": "正常", "params": {}}]
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": True, "risk_level": "low", "issues": [], "suggestions": []})
            )
            result = await reviewer.review_plan(plan)
        assert result.approved is True
        assert result.risk_level == "low"

    async def test_plan_with_degraded_step_forces_high(self):
        reviewer = AIReviewer()
        plan = [{
            "type": "ai_call",
            "description": "降级执行（解析失败）",
            "params": {"task": "x"},
            "degraded": True,
        }]
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": True, "risk_level": "low", "issues": [], "suggestions": []})
            )
            result = await reviewer.review_plan(plan)
        assert result.approved is False
        assert result.risk_level == "high"
        assert any("降级" in i for i in result.issues)

    async def test_plan_with_degraded_step_llm_already_high_kept(self):
        reviewer = AIReviewer()
        plan = [{
            "type": "ai_call",
            "description": "降级执行",
            "params": {},
            "degraded": True,
        }]
        with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"approved": False, "risk_level": "high", "issues": ["plan too risky"], "suggestions": []})
            )
            result = await reviewer.review_plan(plan)
        assert result.approved is False
        assert result.risk_level == "high"


class TestDecomposeDegrade:
    async def test_garbage_response_degrades(self):
        planner = TaskPlanner()
        with patch("app.agent.task_planner.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response("not json at all")
            steps = await planner.decompose("my task")
        assert len(steps) == 1
        assert steps[0]["degraded"] is True
        assert "降级执行" in steps[0]["description"]
        assert steps[0]["params"]["task"] == "my task"

    async def test_schema_violation_degrades(self):
        planner = TaskPlanner()
        with patch("app.agent.task_planner.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps([{"type": "explode", "description": "x", "params": {}}])
            )
            steps = await planner.decompose("my task")
        assert len(steps) == 1
        assert steps[0]["degraded"] is True

    async def test_valid_response_passes(self):
        planner = TaskPlanner()
        with patch("app.agent.task_planner.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps([{"type": "ai_call", "description": "do x", "params": {"task": "x"}}])
            )
            steps = await planner.decompose("my task")
        assert len(steps) == 1
        assert steps[0]["degraded"] is False
        assert steps[0]["type"] == "ai_call"

    async def test_non_list_response_normalized(self):
        """单 dict 响应被规范化为单元素 list，不降级（业务上单步任务合法）"""
        planner = TaskPlanner()
        with patch("app.agent.task_planner.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(
                json.dumps({"type": "ai_call", "description": "x", "params": {}})
            )
            steps = await planner.decompose("my task")
        assert len(steps) == 1
        assert steps[0]["degraded"] is False
        assert steps[0]["type"] == "ai_call"
