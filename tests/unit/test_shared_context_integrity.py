"""SharedContext 回归测试。

覆盖 SC3（session_id 秒级冲突）与 SC5（摘要截断无标记）两处演化缺陷。
"""

from datetime import datetime

import app.agent.shared_context as shared_context_module
from app.agent.shared_context import SharedContext


class TestSessionIdUniqueness:
    """SC3：同秒创建的实例 session_id 不能相同。"""

    def test_session_ids_are_unique_within_same_second(self, tmp_path, monkeypatch):
        fixed = datetime(2026, 1, 1, 12, 0, 0)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        monkeypatch.setattr(shared_context_module, "datetime", _FrozenDatetime)

        ids = {SharedContext("req", tmp_path).session_id for _ in range(50)}

        assert len(ids) == 50

    def test_session_id_keeps_timestamp_prefix(self, tmp_path, monkeypatch):
        fixed = datetime(2026, 1, 1, 12, 0, 0)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        monkeypatch.setattr(shared_context_module, "datetime", _FrozenDatetime)

        assert SharedContext("req", tmp_path).session_id.startswith("20260101_120000_")


class TestSummaryTruncationMarkers:
    """SC5：截断的摘要必须带明确标记。"""

    def test_specs_summary_marks_truncation(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_spec("openapi", {"big": "x" * 600}, "model")

        assert "（内容已截断）" in ctx.get_all_specs_summary()

    def test_specs_summary_short_content_has_no_marker(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_spec("openapi", {"a": 1}, "model")

        assert "（内容已截断）" not in ctx.get_all_specs_summary()

    def test_generated_files_summary_marks_truncation(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("app/a.py", "print('x')\n" * 100, "model")

        assert "（内容已截断）" in ctx.get_generated_files_summary()

    def test_generated_files_summary_short_content_has_no_marker(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("app/a.py", "print('x')\n", "model")

        assert "（内容已截断）" not in ctx.get_generated_files_summary()
