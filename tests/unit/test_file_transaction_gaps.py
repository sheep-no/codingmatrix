"""IncrementalFileTransaction 边界与回滚路径补测。"""

from pathlib import Path

import pytest

from app.agent.change_plan import ChangeAction, ChangePlan, FileChange
from app.agent.orchestration.file_transaction import IncrementalFileTransaction


def _plan(*changes: FileChange) -> ChangePlan:
    return ChangePlan(
        base_revision="r1",
        changes=tuple(changes),
        digest="0" * 64,
    )


def _txn(root: Path, plan: ChangePlan, txn_id: str = "t1") -> IncrementalFileTransaction:
    return IncrementalFileTransaction(root, plan, transaction_id=txn_id)


def test_stage_after_commit_raises(tmp_path):
    txn = _txn(tmp_path, _plan())
    txn.commit()

    with pytest.raises(RuntimeError, match="closed"):
        txn.stage()


def test_stage_after_rollback_raises(tmp_path):
    txn = _txn(tmp_path, _plan())
    txn.rollback()

    with pytest.raises(RuntimeError, match="closed"):
        txn.stage()


def test_stage_twice_raises(tmp_path):
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    txn = _txn(tmp_path, _plan(FileChange(path="a.py", action=ChangeAction.MODIFY)))
    txn.stage()

    with pytest.raises(RuntimeError, match="already staged"):
        txn.stage()


def test_add_existing_target_raises_and_rolls_back(tmp_path):
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    txn = _txn(tmp_path, _plan(FileChange(path="a.py", action=ChangeAction.ADD)))

    with pytest.raises(FileExistsError):
        txn.stage()

    assert txn._closed is True


def test_missing_source_raises(tmp_path):
    txn = _txn(tmp_path, _plan(FileChange(path="missing.py", action=ChangeAction.MODIFY)))

    with pytest.raises(FileNotFoundError):
        txn.stage()

    assert not txn.staging.exists()


def test_source_must_be_regular_file(tmp_path):
    (tmp_path / "dir.py").mkdir()
    txn = _txn(tmp_path, _plan(FileChange(path="dir.py", action=ChangeAction.MODIFY)))

    with pytest.raises(FileNotFoundError):
        txn.stage()


def test_rename_target_exists_raises_and_restores_source(tmp_path):
    (tmp_path / "old.py").write_text("OLD\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("NEW\n", encoding="utf-8")
    txn = _txn(
        tmp_path,
        _plan(
            FileChange(
                path="new.py",
                action=ChangeAction.RENAME,
                previous_path="old.py",
            )
        ),
    )

    with pytest.raises(FileExistsError):
        txn.stage()

    assert (tmp_path / "old.py").read_text(encoding="utf-8") == "OLD\n"
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "NEW\n"


def test_rename_without_previous_path_uses_target(tmp_path):
    (tmp_path / "same.py").write_text("SAME\n", encoding="utf-8")
    txn = _txn(tmp_path, _plan(FileChange(path="same.py", action=ChangeAction.RENAME)))

    txn.stage()

    assert not (tmp_path / "same.py").exists()
    txn.rollback()
    assert (tmp_path / "same.py").read_text(encoding="utf-8") == "SAME\n"


def test_delete_then_commit_removes_file(tmp_path):
    (tmp_path / "gone.py").write_text("X\n", encoding="utf-8")
    txn = _txn(tmp_path, _plan(FileChange(path="gone.py", action=ChangeAction.DELETE)))
    txn.stage()

    assert not (tmp_path / "gone.py").exists()
    txn.commit()

    assert not txn.staging.exists()
    assert txn._closed is True


def test_commit_is_idempotent(tmp_path):
    txn = _txn(tmp_path, _plan())
    txn.commit()
    txn.commit()

    assert txn._closed is True


def test_rollback_is_idempotent(tmp_path):
    txn = _txn(tmp_path, _plan())
    txn.rollback()
    txn.rollback()

    assert txn._closed is True


def test_rollback_skips_created_target_that_is_directory(tmp_path):
    (tmp_path / "dir.py").mkdir()
    txn = _txn(tmp_path, _plan(FileChange(path="dir.py", action=ChangeAction.ADD)))
    txn._created_targets.append(tmp_path / "dir.py")

    txn.rollback()

    assert (tmp_path / "dir.py").is_dir()


def test_rollback_skips_backup_that_is_gone(tmp_path):
    (tmp_path / "a.py").write_text("A\n", encoding="utf-8")
    txn = _txn(tmp_path, _plan(FileChange(path="a.py", action=ChangeAction.MODIFY)))
    txn.stage()
    original, backup = txn._backups[0]
    backup.unlink()

    txn.rollback()

    assert txn._closed is True
    assert original.read_text(encoding="utf-8") == "A\n"


def test_rollback_restores_backup_removing_created_files(tmp_path):
    (tmp_path / "old.py").write_text("OLD\n", encoding="utf-8")
    txn = _txn(
        tmp_path,
        _plan(
            FileChange(path="old.py", action=ChangeAction.MODIFY),
            FileChange(path="new.py", action=ChangeAction.ADD),
        ),
    )
    txn.stage()
    (tmp_path / "old.py").write_text("CHANGED\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("NEW\n", encoding="utf-8")

    txn.rollback()

    assert (tmp_path / "old.py").read_text(encoding="utf-8") == "OLD\n"
    assert not (tmp_path / "new.py").exists()
    assert not txn.staging.exists()
