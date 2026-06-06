"""
SSE 透传事件类型集合测试

修复：orchestrate_endpoints.py 的 SSE 事件类型过滤器
之前漏了 7 个事件类型（test_results/validation_results/cost_update/
performance_metrics/warning/file_rejected/step_detail），导致前端
对应 UI 永远收不到数据（被错误包装成 progress）。

本测试验证 PASSTHROUGH_SSE_EVENTS 集合的完整性和正确性。
"""
import pytest

from app.api.v1.ai_agent.orchestrate_endpoints import PASSTHROUGH_SSE_EVENTS


class TestPassthroughSseEvents:
    """SSE 透传事件类型集合测试"""

    def test_collection_is_frozenset(self):
        """验证类型是 FrozenSet（不可变）"""
        assert isinstance(PASSTHROUGH_SSE_EVENTS, frozenset)

    def test_progress_class_events_included(self):
        """进度类事件必须透传（前端 useAgentStreaming switch case）"""
        progress_events = {"thinking", "model_info", "file", "file_diff"}
        missing = progress_events - PASSTHROUGH_SSE_EVENTS
        assert not missing, f"进度类事件缺失透传: {missing}"

    def test_realtime_stats_events_included(self):
        """实时统计/结果事件必须透传（修复核心 bug）"""
        stats_events = {
            "test_results",
            "validation_results",
            "cost_update",
            "performance_metrics",
        }
        missing = stats_events - PASSTHROUGH_SSE_EVENTS
        assert not missing, f"实时统计事件缺失透传: {missing}"

    def test_warning_step_events_included(self):
        """警告/步骤类事件必须透传（让前端 handler 活起来）"""
        warning_events = {"warning", "file_rejected", "step_detail"}
        missing = warning_events - PASSTHROUGH_SSE_EVENTS
        assert not missing, f"警告/步骤事件缺失透传: {missing}"

    def test_react_events_included(self):
        """ReAct 反思事件必须透传"""
        react_events = {"react_tool_call", "react_tool_result", "react_generating"}
        missing = react_events - PASSTHROUGH_SSE_EVENTS
        assert not missing, f"ReAct 事件缺失透传: {missing}"

    def test_critical_decisions_not_in_passthrough(self):
        """critical_decisions 走专用 emit 路径（orchestrate_endpoints.py:431），
        不会进过滤器，所以不在透传集合中"""
        assert "critical_decisions" not in PASSTHROUGH_SSE_EVENTS

    def test_pause_for_approval_not_in_passthrough(self):
        """pause_for_approval 走专用 emit 路径（orchestrate_endpoints.py:388），
        不通过 stream_callback，所以不在透传集合中"""
        assert "pause_for_approval" not in PASSTHROUGH_SSE_EVENTS

    def test_progress_not_in_passthrough(self):
        """progress 事件本身应该被包装（不是透传）"""
        assert "progress" not in PASSTHROUGH_SSE_EVENTS

    def test_log_not_in_passthrough(self):
        """log 事件走专用 fallback（orchestrate_endpoints.py:455），
        不通过过滤器"""
        assert "log" not in PASSTHROUGH_SSE_EVENTS

    def test_done_not_in_passthrough(self):
        """done 事件走专用 emit 路径（orchestrate_endpoints.py:488）"""
        assert "done" not in PASSTHROUGH_SSE_EVENTS

    def test_error_not_in_passthrough(self):
        """error 事件走专用 emit 路径（orchestrate_endpoints.py:493, 542）"""
        assert "error" not in PASSTHROUGH_SSE_EVENTS

    def test_expected_total_count(self):
        """14 个事件（4 进度 + 4 统计 + 3 警告 + 3 ReAct）"""
        # 4 进度 + 4 实时统计 + 3 警告/步骤 + 3 ReAct = 14
        assert len(PASSTHROUGH_SSE_EVENTS) == 14, (
            f"期望 14 个透传事件，实际 {len(PASSTHROUGH_SSE_EVENTS)}: "
            f"{sorted(PASSTHROUGH_SSE_EVENTS)}"
        )

    def test_no_empty_or_invalid_types(self):
        """不允许空字符串或非字符串"""
        assert "" not in PASSTHROUGH_SSE_EVENTS
        for event_type in PASSTHROUGH_SSE_EVENTS:
            assert isinstance(event_type, str), f"非字符串事件类型: {event_type!r}"
            assert event_type, f"空事件类型"
            assert event_type == event_type.strip(), f"事件类型有空白: {event_type!r}"


class TestSseFilterBehavior:
    """测试 SSE 过滤器行为（模拟 orchestrate_endpoints.py:449-453）"""

    @pytest.fixture
    def filter_func(self):
        """返回过滤器判定函数（与 orchestrate_endpoints.py:449-453 行为一致）"""
        def _is_passthrough(progress_data: dict) -> bool:
            msg_type = progress_data.get("type", "")
            return msg_type in PASSTHROUGH_SSE_EVENTS
        return _is_passthrough

    def test_thinking_data_passes_through(self, filter_func):
        assert filter_func({"type": "thinking", "message": "test"}) is True

    def test_test_results_passes_through(self, filter_func):
        assert filter_func({"type": "test_results", "passed": 5}) is True

    def test_cost_update_passes_through(self, filter_func):
        assert filter_func({"type": "cost_update", "total_tokens": 1000}) is True

    def test_warning_passes_through(self, filter_func):
        assert filter_func({"type": "warning", "message": "test"}) is True

    def test_unknown_type_gets_wrapped(self, filter_func):
        assert filter_func({"type": "unknown_event", "data": "x"}) is False

    def test_missing_type_gets_wrapped(self, filter_func):
        assert filter_func({"data": "no type field"}) is False

    def test_empty_dict_gets_wrapped(self, filter_func):
        assert filter_func({}) is False
