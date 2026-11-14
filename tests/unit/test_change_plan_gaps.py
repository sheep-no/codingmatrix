"""change_plan 合并规则、扩展守卫与快照校验的边界补测。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.change_plan import (
    ChangeAction,
    ChangePlan,
    FileChange,
    collapse_change_items,
    expand_change_plan_for_missing_exports,
)
from app.agent.project_snapshot import ProjectSnapshot


def test_collapse_skips_items_without_path():
    collapsed = collapse_change_items(
        [{"action": "modify", "path": "   "}, {"action": "modify", "path": "a.py"}]
    )

    assert [item["path"] for item in collapsed] == ["a.py"]


def test_merge_without_reasons_keeps_first_only_metadata():
    collapsed = collapse_change_items([{"path": "a.py"}, {"path": "a.py"}])

    assert "reason" not in collapsed[0]
    assert "dependencies" not in collapsed[0]


def test_merge_combines_description_and_dependencies():
    collapsed = collapse_change_items(
        [
            {"path": "a.py", "description": "first", "dependencies": ["x"]},
            {"path": "a.py", "description": "second", "depends_on": ["x", "y"]},
        ]
    )

    merged = collapsed[0]
    assert merged["reason"] == "first; second"
    assert merged["description"] == "first; second"
    assert merged["dependencies"] == ["x", "y"]


def test_merge_fills_previous_path_and_owner_from_second():
    collapsed = collapse_change_items(
        [
            {"path": "a.py", "action": "rename"},
            {"path": "a.py", "action": "rename", "previous_path": "old.py", "owner": "bob"},
        ]
    )

    assert collapsed[0]["previous_path"] == "old.py"
    assert collapsed[0]["owner"] == "bob"


def test_merge_actions_delete_wins():
    collapsed = collapse_change_items(
        [{"path": "a.py", "action": "add"}, {"path": "a.py", "action": "delete"}]
    )

    assert collapsed[0]["action"] == "delete"


def test_merge_actions_add_wins_over_unknown_non_delete():
    collapsed = collapse_change_items(
        [{"path": "new.py", "action": "add"}, {"path": "new.py", "action": "rename"}]
    )

    assert collapsed[0]["action"] == "add"


def test_merge_actions_falls_back_to_second():
    collapsed = collapse_change_items(
        [{"path": "new.py", "action": "modify"}, {"path": "new.py", "action": "rename"}],
        known_paths=set(),
    )

    assert collapsed[0]["action"] == "rename"


def test_merge_actions_known_path_becomes_modify():
    collapsed = collapse_change_items(
        [{"path": "a.py", "action": "add"}, {"path": "a.py", "action": "rename"}],
        known_paths={"a.py"},
    )

    assert collapsed[0]["action"] == "modify"


def test_expand_returns_existing_without_adapter():
    changes = [{"path": "a.py", "action": "modify"}]

    assert expand_change_plan_for_missing_exports(
        changes, output_dir=Path("."), language_adapter=None, known_files=["a.py"]
    ) == changes


def test_expand_returns_existing_when_root_unresolvable(tmp_path, monkeypatch):
    def boom(self):
        raise OSError("cannot resolve")

    monkeypatch.setattr(Path, "resolve", boom)

    assert expand_change_plan_for_missing_exports(
        [{"path": "a.py", "action": "modify"}],
        output_dir=tmp_path,
        language_adapter=object(),
        known_files=["a.py"],
    ) == [{"path": "a.py", "action": "modify"}]


class _Adapter:
    def __init__(self, imports=None, definitions=None, resolve=None, infer=None):
        self._imports = imports or {}
        self._definitions = definitions or {}
        self._resolve = resolve or {}
        self._infer = infer

    def extract_definitions(self, content):
        return self._definitions.get(content, set())

    def parse_imports(self, content, importer):
        return self._imports.get(importer, ())

    def resolve_import_to_file(self, info, importer):
        return self._resolve.get((importer, info.module), ())

    def infer_file_type(self, path):
        if self._infer is not None:
            return self._infer(path)
        return "python"


@pytest.fixture
def root(tmp_path):
    return tmp_path


def test_expand_skips_deleted_and_missing_files(root):
    (root / "keep.py").write_text("x = 1", encoding="utf-8")
    (root / "broken.py").write_bytes(b"\xff\xfe\x00bad")

    adapter = _Adapter()
    result = expand_change_plan_for_missing_exports(
        [
            {"path": "gone.py", "action": "delete"},
            {"path": "keep.py", "action": "modify"},
        ],
        output_dir=root,
        language_adapter=adapter,
        known_files=["gone.py", "keep.py", "missing.py", "broken.py"],
    )

    assert [item["path"] for item in result] == ["gone.py", "keep.py"]


def test_expand_skips_paths_outside_root(root):
    outside = root / "outside.py"
    outside.write_text("x = 1", encoding="utf-8")
    project = root / "project"
    project.mkdir()

    result = expand_change_plan_for_missing_exports(
        [{"path": "main.py", "action": "modify"}],
        output_dir=project,
        language_adapter=_Adapter(),
        known_files=["../outside.py"],
    )

    assert result == [{"path": "main.py", "action": "modify"}]


def test_expand_handles_adapter_failures_and_empty_symbols(root):
    (root / "main.py").write_text("import calc", encoding="utf-8")
    info = SimpleNamespace(module="calc", symbols=["*", ""])

    class _FailingAdapter(_Adapter):
        def extract_definitions(self, content):
            raise RuntimeError("definition failure")

        def parse_imports(self, content, importer):
            return [info]

        def resolve_import_to_file(self, info, importer):
            raise RuntimeError("resolve failure")

    result = expand_change_plan_for_missing_exports(
        [{"path": "main.py", "action": "modify"}],
        output_dir=root,
        language_adapter=_FailingAdapter(),
        known_files=["main.py"],
    )

    assert [item["path"] for item in result] == ["main.py"]


def test_expand_skips_imports_without_symbols_and_unresolved_provider(root):
    (root / "main.py").write_text("import calc", encoding="utf-8")
    (root / "calc.py").write_text("x = 1", encoding="utf-8")

    no_symbols = SimpleNamespace(module="calc", symbols=[])
    unresolved = SimpleNamespace(module="calc", symbols=["missing"])
    adapter = _Adapter(
        imports={"main.py": [no_symbols, unresolved]},
        resolve={("main.py", "calc"): ["other.py"]},
    )

    result = expand_change_plan_for_missing_exports(
        [{"path": "main.py", "action": "modify"}],
        output_dir=root,
        language_adapter=adapter,
        known_files=["main.py", "calc.py"],
    )

    assert [item["path"] for item in result] == ["main.py"]


def test_expand_prefers_known_candidate_and_skips_callable_missing(root):
    (root / "main.py").write_text("import calc", encoding="utf-8")
    (root / "calc.py").write_text("x = 1", encoding="utf-8")
    (root / "other.py").write_text("y = 1", encoding="utf-8")
    info = SimpleNamespace(module="calc", symbols=["missing"])
    adapter = _Adapter(
        imports={"main.py": [info]},
        definitions={"x = 1": set()},
        resolve={("main.py", "calc"): ["missing.py", "calc.py"]},
    )
    adapter.infer_file_type = None

    result = expand_change_plan_for_missing_exports(
        [{"path": "main.py", "action": "modify"}],
        output_dir=root,
        language_adapter=adapter,
        known_files=["main.py", "calc.py", "other.py"],
    )

    calc = [item for item in result if item["path"] == "calc.py"][0]
    assert calc["action"] == "modify"
    assert "missing" in calc["reason"]
    assert "file_type" not in calc


def test_expand_ignores_infer_file_type_errors(root):
    (root / "main.py").write_text("import calc", encoding="utf-8")
    (root / "calc.py").write_text("x = 1", encoding="utf-8")
    info = SimpleNamespace(module="calc", symbols=["missing"])
    adapter = _Adapter(
        imports={"main.py": [info]},
        definitions={"x = 1": set()},
        resolve={("main.py", "calc"): ["calc.py"]},
    )

    def boom(_path):
        raise RuntimeError("cannot infer")

    adapter._infer = boom
    adapter.infer_file_type = lambda path: (_ for _ in ()).throw(RuntimeError("bad"))

    result = expand_change_plan_for_missing_exports(
        [{"path": "main.py", "action": "modify"}],
        output_dir=root,
        language_adapter=adapter,
        known_files=["main.py", "calc.py"],
    )

    calc = [item for item in result if item["path"] == "calc.py"][0]
    assert "file_type" not in calc


def test_change_plan_build_rejects_modify_absent_from_snapshot(tmp_path):
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")

    with pytest.raises(ValueError, match="modified file is absent"):
        ChangePlan.build(snapshot, [{"path": "ghost.py", "action": "modify"}])


def test_change_plan_build_rejects_delete_absent_from_snapshot(tmp_path):
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")

    with pytest.raises(ValueError, match="deleted file is absent"):
        ChangePlan.build(snapshot, [{"path": "ghost.py", "action": "delete"}])


def test_change_plan_build_rejects_rename_absent_source(tmp_path):
    (tmp_path / "new.py").write_text("x = 1", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")

    with pytest.raises(ValueError, match="renamed source is absent"):
        ChangePlan.build(
            snapshot,
            [{"path": "new.py", "action": "rename", "previous_path": "old.py"}],
        )


def test_change_plan_affected_files_includes_previous_path(tmp_path):
    (tmp_path / "old.py").write_text("x = 1", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(
        snapshot,
        [FileChange(path="new.py", action=ChangeAction.RENAME, previous_path="old.py")],
    )

    assert plan.affected_files == ("new.py", "old.py")


def test_change_plan_verify_untouched_detects_out_of_scope_changes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("a = 1", encoding="utf-8")
    (project / "b.py").write_text("b = 1", encoding="utf-8")
    before = ProjectSnapshot.scan(project, revision="r1")
    plan = ChangePlan.build(before, [{"path": "a.py", "action": "modify"}])

    (project / "a.py").write_text("a = 2", encoding="utf-8")
    (project / "b.py").write_text("b = 2", encoding="utf-8")
    (project / "c.py").write_text("c = 1", encoding="utf-8")
    after = ProjectSnapshot.scan(project, revision="r2")

    assert plan.verify_untouched(before, after) == ("b.py", "c.py")
