"""legacy 增量路径失败时必须回滚已写盘与已删除的文件。"""

import json

import pytest

from app.agent.orchestrator_generation.incremental_modify import IncrementalModifyMixin


def _write_graph(tmp_path):
    graph = {
        "nodes": {
            "main.py": {"type": "entry", "priority": 1, "description": "entry"},
            "old.py": {"type": "utils", "priority": 3, "description": "old"},
        },
        "dependencies": {},
        "generation_order": ["main.py", "old.py"],
    }
    (tmp_path / ".dep_graph.json").write_text(json.dumps(graph), encoding="utf-8")


class _Harness(IncrementalModifyMixin):
    def __init__(self, output_dir, *, fail: bool):
        self.output_dir = output_dir
        self.complexity = None
        self.session_id = "sess"
        self.api_key_token = None
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.plans = []
        self.fail = fail

    async def _initialize_components_fast(self, requirement):
        return None

    def _report_progress(self, *args, **kwargs):
        return None

    async def _analyze_changes_with_architect(self, requirement, summary, graph, callback):
        return self.plans

    async def _generate_with_dynamic_topology_incremental(self, *args, **kwargs):
        if self.fail:
            # 模拟逐文件落盘后中途失败：main.py 已被改写、new.py 已被创建
            (self.output_dir / "main.py").write_text("print('partially written')\n", encoding="utf-8")
            (self.output_dir / "new.py").write_text("partially created\n", encoding="utf-8")
            raise RuntimeError("incremental file generation failed")
        return {
            "files_generated": 1,
            "files_failed": 0,
            "generated_files": [{"path": "main.py"}],
            "errors": [],
            "warnings": [],
        }

    async def _update_dependency_graph_incremental(self, graph, contents, adapter):
        return None


@pytest.fixture(autouse=True)
def _stub_dependencies(monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    monkeypatch.setattr(DependencyGraph, "enrich_and_save", lambda self, *a, **k: None)

    class _SpecStub:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def get_spec_budget(context_length):
            return 1000

        def get_spec_context_for_file(self, *args, **kwargs):
            return {}

    monkeypatch.setattr("app.agent.spec_first_generator.SpecFirstGenerator", _SpecStub)


@pytest.mark.asyncio
async def test_failed_incremental_restores_modified_and_deleted_files(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "main.py").write_text("print('original')\n", encoding="utf-8")
    (tmp_path / "old.py").write_text("legacy = True\n", encoding="utf-8")

    harness = _Harness(tmp_path, fail=True)
    harness.plans = [
        {"action": "modify", "path": "main.py", "reason": "change"},
        {"action": "delete", "path": "old.py"},
        {"action": "add", "path": "new.py"},
    ]

    with pytest.raises(RuntimeError, match="incremental file generation failed"):
        await harness.generate_incremental("break things")

    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "print('original')\n"
    assert (tmp_path / "old.py").read_text(encoding="utf-8") == "legacy = True\n"
    assert not (tmp_path / "new.py").exists()


@pytest.mark.asyncio
async def test_successful_incremental_keeps_changes(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "main.py").write_text("print('original')\n", encoding="utf-8")
    (tmp_path / "old.py").write_text("legacy = True\n", encoding="utf-8")

    harness = _Harness(tmp_path, fail=False)
    harness.plans = [
        {"action": "modify", "path": "main.py", "reason": "change"},
        {"action": "delete", "path": "old.py"},
    ]

    result = await harness.generate_incremental("change things")

    assert result["success"] is True
    assert not (tmp_path / "old.py").exists()
    assert not (tmp_path / ".orchestration-txn").exists()
