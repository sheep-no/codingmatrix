"""SharedContext 回归测试。

覆盖 SC3（session_id 秒级冲突）、SC5（摘要截断无标记）、
SC2（未注册文件 file_type 恒 unknown）、SC4（files_generated 恒 0 死字段）、
SC6（to_export_dict 不含 content）五处演化缺陷。
"""

from datetime import datetime

import app.agent.shared_context as shared_context_module
from app.agent.dependency_rules import infer_file_type_fallback
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


class TestUnregisteredFileTypeInference:
    """SC2：save_file_content 未注册路径时 file_type 按路径推断，恒 unknown。"""

    def test_python_service_path_inferred(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("app/services/user_service.py", "x = 1\n", "model")

        assert ctx.files["app/services/user_service.py"].file_type == "service"

    def test_frontend_component_inferred(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("src/components/Button.vue", "<template />", "model")

        assert ctx.files["src/components/Button.vue"].file_type == "frontend_component"

    def test_frontend_page_beats_extension_map(self, tmp_path):
        # 与依赖图推断一致：路径规则（views/ → frontend_page）优先于 .vue 扩展名映射
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("src/views/App.vue", "<template />", "model")

        assert ctx.files["src/views/App.vue"].file_type == "frontend_page"

    def test_config_file_inferred(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("config/settings.yaml", "key: value\n", "model")

        assert ctx.files["config/settings.yaml"].file_type == "config"

    def test_unrecognizable_path_stays_unknown(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("blob/weird.xyz", "data", "model")

        assert ctx.files["blob/weird.xyz"].file_type == "unknown"

    def test_registered_file_keeps_explicit_type(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.register_file("app/custom.py", "model")
        ctx.save_file_content("app/custom.py", "x = 1\n", "model")

        assert ctx.files["app/custom.py"].file_type == "model"

    def test_inference_matches_dependency_graph_fallback(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("app/api/routes.py", "x = 1\n", "model")

        assert ctx.files["app/api/routes.py"].file_type == infer_file_type_fallback(
            "app/api/routes.py", fallback="unknown"
        )


class TestExportDictCompleteness:
    """SC6/SC4：导出字典必须含文件内容；失真的 files_generated 字段已删除。"""

    def test_export_dict_contains_file_content(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.save_file_content("app/a.py", "print('hi')\n", "model")

        exported = ctx.to_export_dict()

        assert exported["files"]["app/a.py"]["content"] == "print('hi')\n"

    def test_export_dict_phase_has_no_files_generated(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.start_phase("code_generation", total_files=5)
        ctx.complete_phase("code_generation")

        exported = ctx.to_export_dict()

        assert "files_generated" not in exported["phases"]["code_generation"]

    def test_generation_phase_has_no_files_generated_attribute(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.start_phase("code_generation", total_files=3)

        assert not hasattr(ctx.phases["code_generation"], "files_generated")
