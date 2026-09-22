"""Spec-First 收尾清理的行为约束（SPFG11/SPFG12/SPFG15）。"""

from types import SimpleNamespace

from app.agent.dependency_graph import DependencyGraph
from app.agent.orchestrator_generation.spec_first_generate import (
    _dedup_keep_rank,
    _select_duplicate_files,
    _select_language_mismatch_files,
)


def _artifact(generated_by: str = "engineer") -> SimpleNamespace:
    return SimpleNamespace(generated_by=generated_by)


class TestLanguageMismatchSelection:
    def test_flags_generated_file_outside_expected_extensions(self):
        files = {"src/a.py": _artifact(), "web/b.js": _artifact()}
        # 纯 Python 项目：.js 不在允许扩展名内
        assert _select_language_mismatch_files(files, {".py"}) == ["web/b.js"]

    def test_keeps_multi_language_plan_extensions(self):
        files = {"src/a.py": _artifact(), "web/b.js": _artifact()}
        assert _select_language_mismatch_files(files, {".py", ".js"}) == []

    def test_skips_resumed_cached_files(self):
        files = {"web/b.js": _artifact("cached")}
        assert _select_language_mismatch_files(files, {".py"}) == []

    def test_unrelated_extension_not_touched(self):
        files = {"README.md": _artifact(), "data.json": _artifact()}
        assert _select_language_mismatch_files(files, {".py"}) == []


class TestDuplicateSelection:
    def test_same_name_same_content_removes_lower_priority(self):
        files = {"manage.py": _artifact(), "src/manage.py": _artifact()}
        contents = {"manage.py": "print(1)\n", "src/manage.py": "print(1)\n"}
        assert _select_duplicate_files(files, contents) == {"manage.py": "src/manage.py"}

    def test_same_name_different_content_is_kept(self):
        files = {"manage.py": _artifact(), "src/manage.py": _artifact()}
        contents = {"manage.py": "django.setup()\n", "src/manage.py": "print(1)\n"}
        assert _select_duplicate_files(files, contents) == {}

    def test_app_dir_beats_src_app_dir(self):
        files = {"src/app/main.py": _artifact(), "app/main.py": _artifact()}
        contents = {"src/app/main.py": "x\n", "app/main.py": "x\n"}
        # `src/` 优先于 `app/`（与既有优先级列表一致）
        assert _select_duplicate_files(files, contents) == {"app/main.py": "src/app/main.py"}

    def test_skips_resumed_cached_files(self):
        files = {"manage.py": _artifact("cached"), "src/manage.py": _artifact()}
        contents = {"manage.py": "x\n", "src/manage.py": "x\n"}
        # 根目录 manage.py 同名同内容但来自断点续传复用，不作删除对象
        assert _select_duplicate_files(files, contents) == {}

    def test_rank_prefers_named_dirs_over_root(self):
        assert _dedup_keep_rank("src/a.py") < _dedup_keep_rank("lib/a.py")
        assert _dedup_keep_rank("lib/a.py") < _dedup_keep_rank("a.py")


class TestRemoveNode:
    def test_removes_node_and_edges(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        graph.add_file("b.py")
        graph.add_dependency("b.py", "a.py")

        assert graph.remove_node("a.py") is True
        assert "a.py" not in graph.nodes
        assert "a.py" not in graph.adjacency.get("b.py", set())

    def test_is_idempotent(self):
        graph = DependencyGraph()
        graph.add_file("a.py")
        assert graph.remove_node("a.py") is True
        assert graph.remove_node("a.py") is False
