"""incremental_generate 空会话、复用文件、无变更与取消分支补测。"""

import asyncio
import types

import pytest

from app.agent.orchestrator_generation import incremental_generate as ig


class _Harness:
    def __init__(self, output_dir, *, state=None, plan=None, cancel=False, session=True):
        self.output_dir = output_dir
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.cancel_event = types.SimpleNamespace(is_set=lambda: cancel) if cancel else None
        self.session_id = "s1" if session else None
        self.session_manager = types.SimpleNamespace(
            detect_incremental_changes=self._detect,
            get_file_plan_for_incremental=lambda _state: plan or [],
        ) if session else None
        self._state = state or types.SimpleNamespace(unchanged_files=[], changed_files=[])
        self.small_project_calls = []
        self.progress = []

    async def _detect(self, *_args, **_kwargs):
        return {"state": self._state}

    def _report_progress(self, label, current, total, **kwargs):
        self.progress.append((label, current, total, kwargs))

    async def _generate_files_small_project(self, file_plan, context, total):
        self.small_project_calls.append((file_plan, context, total))

    async def _generate_single_file(self, file_info, *_args, **_kwargs):
        return {"path": file_info["path"], "success": True}


@pytest.fixture(autouse=True)
def _stash(monkeypatch):
    calls = {"push": [], "pop": 0, "drop": 0}
    monkeypatch.setattr(ig, "_git_stash_push", lambda root, files, msg: calls["push"].append((files, msg)) or True)
    monkeypatch.setattr(ig, "_git_stash_pop", lambda root: calls.__setitem__("pop", calls["pop"] + 1))
    monkeypatch.setattr(ig, "_git_stash_drop", lambda root: calls.__setitem__("drop", calls["drop"] + 1))
    return calls


async def test_falls_back_to_small_project_without_session(tmp_path):
    harness = _Harness(tmp_path, session=False)
    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [{"path": "a.py"}], {"architecture": {}}, 1
    )
    assert harness.small_project_calls == [([{"path": "a.py"}], {"architecture": {}}, 1)]
    assert harness.generated_files == []


async def test_unchanged_files_are_recorded_as_reused(tmp_path, _stash):
    harness = _Harness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=["keep.py"], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
    )
    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [{"path": "a.py"}], {}, 2
    )
    assert harness.generated_files[0] == {
        "path": "keep.py",
        "description": "复用已有文件",
        "success": True,
        "reused": True,
    }
    assert harness.progress[0][3]["files_reusable"] == 1
    assert harness.progress[0][3]["files_to_regenerate"] == 1


async def test_no_incremental_plan_reports_and_returns(tmp_path, _stash):
    harness = _Harness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=[]),
        plan=[],
    )
    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [], {}, 0
    )
    assert harness.progress[-1][:3] == (
        ig.PROGRESS_LABELS.get("incremental_no_changes", "无变更"), 1, 1
    )
    assert _stash["push"] == []
    assert harness.generated_files == []


async def test_cancel_event_skips_generation(tmp_path, _stash):
    harness = _Harness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
        cancel=True,
    )
    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [{"path": "a.py"}], {}, 1
    )
    assert _stash["push"] == []
    assert harness.generated_files == []
    assert harness.errors == []


async def test_cancelled_result_rolls_back_and_raises(tmp_path, _stash):
    class CancelHarness(_Harness):
        async def _generate_single_file(self, file_info, *_args, **_kwargs):
            raise asyncio.CancelledError("cancelled by user")

    harness = CancelHarness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
    )

    with pytest.raises(RuntimeError, match="incremental file generation cancelled"):
        await ig.IncrementalGenerateMixin._handle_incremental_generation(
            harness, "req", [{"path": "a.py"}], {}, 1
        )

    assert any("文件生成被取消: a.py" in e for e in harness.errors)
    assert _stash["pop"] == 1


async def test_exception_result_is_reported(tmp_path, _stash):
    class BoomHarness(_Harness):
        async def _generate_single_file(self, file_info, *_args, **_kwargs):
            raise ValueError("boom")

    harness = BoomHarness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
    )

    with pytest.raises(RuntimeError, match="incremental file generation failed"):
        await ig.IncrementalGenerateMixin._handle_incremental_generation(
            harness, "req", [{"path": "a.py"}], {}, 1
        )

    assert any("boom" in e for e in harness.errors)
    assert _stash["pop"] == 1


async def test_falsy_result_is_ignored(tmp_path, _stash):
    class EmptyHarness(_Harness):
        async def _generate_single_file(self, file_info, *_args, **_kwargs):
            return {}

    harness = EmptyHarness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
    )

    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [{"path": "a.py"}], {}, 1
    )

    assert harness.generated_files == []
    assert harness.errors == []


async def test_success_without_stash_does_not_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "_git_stash_push", lambda *a, **k: False)
    drops = []
    monkeypatch.setattr(ig, "_git_stash_drop", lambda root: drops.append(root))

    harness = _Harness(
        tmp_path,
        state=types.SimpleNamespace(unchanged_files=[], changed_files=["a.py"]),
        plan=[{"path": "a.py"}],
    )

    await ig.IncrementalGenerateMixin._handle_incremental_generation(
        harness, "req", [{"path": "a.py"}], {}, 1
    )

    assert harness.generated_files[0]["path"] == "a.py"
    assert drops == []
    assert any("增量备份不可用" in w for w in harness.warnings)
