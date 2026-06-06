"""
P2 充实单测：3 个事件方法的实现和正确事件形态

修复：之前 _report_warning 存在但无人调用，_report_file_rejected /
_report_step_detail 根本不存在；前端 useAgentStreaming.js case 'warning' /
'file_rejected' / 'step_detail' 永远走 default 路径。

本测试验证：
1. _report_warning 推送正确的事件形态（含 code 字段）
2. _report_file_rejected 推送嵌套在 data.file_path 的事件
3. _report_step_detail 推送 description + category 字段
4. _emit_event 复用：3 个方法都通过同一个 callback 推送
5. callback 异常时不会崩溃
"""
import asyncio
import json
import pytest

from app.agent.orchestrator_progress import ProgressMixin


class _CapturingReporter(ProgressMixin):
    """捕获所有事件回调的测试 reporter"""

    def __init__(self):
        # ProgressMixin 没有 __init__，跳过 super()
        # 关键属性：callback（事件出口）+ _pending_tasks（async 任务池）
        self.events = []
        self.callback = lambda raw: self.events.append(json.loads(raw))
        self._pending_tasks = set()


class TestReportWarning:
    """_report_warning 事件形态"""

    def test_minimal_warning(self):
        reporter = _CapturingReporter()
        reporter._report_warning("test warning")
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event["type"] == "warning"
        assert event["message"] == "test warning"
        assert event["code"] == ""  # 默认空
        assert "timestamp" in event

    def test_warning_with_code(self):
        """前端 useAgentStreaming.js case 'warning' 读 data.code 来显示详情"""
        reporter = _CapturingReporter()
        reporter._report_warning("test failed", code="review_suggestion", file_path="foo.py")
        event = reporter.events[0]
        assert event["code"] == "review_suggestion"
        assert event["file_path"] == "foo.py"

    def test_warning_does_not_emit_when_no_callback(self):
        """无 callback 时不应崩溃（_emit_event 直接 return）"""
        reporter = _CapturingReporter()
        reporter.callback = None
        # 应当静默成功，不抛异常
        reporter._report_warning("ignored")
        assert reporter.events == []


class TestReportFileRejected:
    """_report_file_rejected 事件形态（P2 新增）"""

    def test_basic_event(self):
        """事件应包含 type + data.file_path"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected("src/api/users.py")
        event = reporter.events[0]
        assert event["type"] == "file_rejected"
        assert event["data"]["file_path"] == "src/api/users.py"
        assert "timestamp" in event

    def test_with_reason(self):
        """带拒绝原因"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected(
            file_path="main.py",
            reason="用户在 HITL 审批中拒绝"
        )
        event = reporter.events[0]
        assert event["data"]["reason"] == "用户在 HITL 审批中拒绝"

    def test_with_extra_kwargs(self):
        """额外字段透传"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected(
            file_path="x.py",
            reason="r",
            reviewer="admin",
            risk_level="high"
        )
        event = reporter.events[0]
        assert event["reviewer"] == "admin"
        assert event["risk_level"] == "high"


class TestReportStepDetail:
    """_report_step_detail 事件形态（P2 新增）"""

    def test_basic_event(self):
        reporter = _CapturingReporter()
        reporter._report_step_detail("项目上下文已加载")
        event = reporter.events[0]
        assert event["type"] == "step_detail"
        assert event["description"] == "项目上下文已加载"
        assert event["category"] == "执行步骤"  # 默认

    def test_with_category(self):
        """带自定义 category"""
        reporter = _CapturingReporter()
        reporter._report_step_detail(
            description="规格书已生成（API 契约 + 数据模型）",
            category="规格书"
        )
        event = reporter.events[0]
        assert event["category"] == "规格书"

    def test_with_extra_kwargs(self):
        reporter = _CapturingReporter()
        reporter._report_step_detail(
            description="test",
            file_count=42,
            layer_index=2
        )
        event = reporter.events[0]
        assert event["file_count"] == 42
        assert event["layer_index"] == 2


class TestEmitEventReuse:
    """_emit_event 统一入口的健壮性"""

    def test_callback_exception_does_not_propagate(self):
        """callback 抛异常时，_emit_event 应吞掉（避免中断主流程）"""
        reporter = _CapturingReporter()

        def bad_callback(raw):
            raise RuntimeError("network down")

        reporter.callback = bad_callback
        # 应当只记日志，不抛
        reporter._report_warning("test")
        # 3 个 _report_* 方法都通过 _emit_event，应当都健壮
        reporter._report_file_rejected("x.py")
        reporter._report_step_detail("y")

    @pytest.mark.asyncio
    async def test_async_callback_supported(self):
        """async callback 也支持（包装为 task）"""
        async def async_callback(raw):
            await asyncio.sleep(0)
            return json.loads(raw)

        reporter = _CapturingReporter()
        reporter.callback = async_callback
        reporter._report_warning("test")

        # 等所有 task 完成
        if reporter._pending_tasks:
            await asyncio.gather(*reporter._pending_tasks, return_exceptions=True)


class TestEventShapeContract:
    """事件形态契约（与前端 useAgentStreaming.js case 一一对齐）"""

    def test_warning_event_matches_frontend(self):
        """前端 case 'warning': 读 data.message, data.code, data.content"""
        reporter = _CapturingReporter()
        reporter._report_warning("review failed", code="REV001", content="details")
        event = reporter.events[0]
        # 验证前端能正确读取的字段
        assert event["message"] == "review failed"
        assert event["code"] == "REV001"
        assert event["content"] == "details"

    def test_file_rejected_event_matches_frontend(self):
        """前端 case 'file_rejected': 读 data.data?.file_path"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected("foo.py")
        event = reporter.events[0]
        # 嵌套 data
        assert event["data"]["file_path"] == "foo.py"

    def test_step_detail_event_matches_frontend(self):
        """前端 case 'step_detail': 读 data.description, data.category"""
        reporter = _CapturingReporter()
        reporter._report_step_detail("done", category="验证")
        event = reporter.events[0]
        # 平铺字段
        assert event["description"] == "done"
        assert event["category"] == "验证"


class TestReportWarning:
    """_report_warning 事件形态"""

    def test_minimal_warning(self):
        reporter = _CapturingReporter()
        reporter._report_warning("test warning")
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event["type"] == "warning"
        assert event["message"] == "test warning"
        assert event["code"] == ""  # 默认空
        assert "timestamp" in event

    def test_warning_with_code(self):
        """前端 useAgentStreaming.js case 'warning' 读 data.code 来显示详情"""
        reporter = _CapturingReporter()
        reporter._report_warning("test failed", code="review_suggestion", file_path="foo.py")
        event = reporter.events[0]
        assert event["code"] == "review_suggestion"
        assert event["file_path"] == "foo.py"

    def test_warning_does_not_emit_when_no_callback(self):
        """无 callback 时不应崩溃（之前 _emit_event 没抽出来时直接 if self.callback 判空）"""
        reporter = _CapturingReporter()
        reporter.callback = None
        # 应当静默成功，不抛异常
        reporter._report_warning("ignored")
        # 注意：progress reporter 的 _pending_tasks 仍会被 set（如果 iscoroutine）
        # 这里 callback 为 None，所以 _emit_event 直接 return


class TestReportFileRejected:
    """_report_file_rejected 事件形态（P2 新增）"""

    def test_basic_event(self):
        """事件应包含 type + data.file_path"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected("src/api/users.py")
        event = reporter.events[0]
        assert event["type"] == "file_rejected"
        assert event["data"]["file_path"] == "src/api/users.py"
        assert "timestamp" in event

    def test_with_reason(self):
        """带拒绝原因"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected(
            file_path="main.py",
            reason="用户在 HITL 审批中拒绝"
        )
        event = reporter.events[0]
        assert event["data"]["reason"] == "用户在 HITL 审批中拒绝"

    def test_with_extra_kwargs(self):
        """额外字段透传"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected(
            file_path="x.py",
            reason="r",
            reviewer="admin",
            risk_level="high"
        )
        event = reporter.events[0]
        assert event["reviewer"] == "admin"
        assert event["risk_level"] == "high"


class TestReportStepDetail:
    """_report_step_detail 事件形态（P2 新增）"""

    def test_basic_event(self):
        reporter = _CapturingReporter()
        reporter._report_step_detail("项目上下文已加载")
        event = reporter.events[0]
        assert event["type"] == "step_detail"
        assert event["description"] == "项目上下文已加载"
        assert event["category"] == "执行步骤"  # 默认

    def test_with_category(self):
        """带自定义 category"""
        reporter = _CapturingReporter()
        reporter._report_step_detail(
            description="规格书已生成（API 契约 + 数据模型）",
            category="规格书"
        )
        event = reporter.events[0]
        assert event["category"] == "规格书"

    def test_with_extra_kwargs(self):
        reporter = _CapturingReporter()
        reporter._report_step_detail(
            description="test",
            file_count=42,
            layer_index=2
        )
        event = reporter.events[0]
        assert event["file_count"] == 42
        assert event["layer_index"] == 2


class TestEmitEventReuse:
    """_emit_event 统一入口的健壮性"""

    def test_callback_exception_does_not_propagate(self):
        """callback 抛异常时，_emit_event 应吞掉（避免中断主流程）"""
        reporter = _CapturingReporter()

        def bad_callback(raw):
            raise RuntimeError("network down")

        reporter.callback = bad_callback
        # 应当只记日志，不抛
        reporter._report_warning("test")
        # 3 个 _report_* 方法都通过 _emit_event，应当都健壮
        reporter._report_file_rejected("x.py")
        reporter._report_step_detail("y")

    @pytest.mark.asyncio
    async def test_async_callback_supported(self):
        """async callback 也支持（包装为 task）"""
        async def async_callback(raw):
            await asyncio.sleep(0)
            return json.loads(raw)

        reporter = _CapturingReporter()
        reporter.callback = async_callback
        reporter._report_warning("test")

        # 等所有 task 完成
        if reporter._pending_tasks:
            await asyncio.gather(*reporter._pending_tasks, return_exceptions=True)


class TestEventShapeContract:
    """事件形态契约（与前端 useAgentStreaming.js case 一一对齐）"""

    def test_warning_event_matches_frontend(self):
        """前端 case 'warning': 读 data.message, data.code, data.content"""
        reporter = _CapturingReporter()
        reporter._report_warning("review failed", code="REV001", content="details")
        event = reporter.events[0]
        # 验证前端能正确读取的字段
        assert event["message"] == "review failed"
        assert event["code"] == "REV001"
        assert event["content"] == "details"

    def test_file_rejected_event_matches_frontend(self):
        """前端 case 'file_rejected': 读 data.data?.file_path"""
        reporter = _CapturingReporter()
        reporter._report_file_rejected("foo.py")
        event = reporter.events[0]
        # 嵌套 data
        assert event["data"]["file_path"] == "foo.py"

    def test_step_detail_event_matches_frontend(self):
        """前端 case 'step_detail': 读 data.description, data.category"""
        reporter = _CapturingReporter()
        reporter._report_step_detail("done", category="验证")
        event = reporter.events[0]
        # 平铺字段
        assert event["description"] == "done"
        assert event["category"] == "验证"
