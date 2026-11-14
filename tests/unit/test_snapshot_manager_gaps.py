"""snapshot_manager 失败回退与 finalize 分支补测。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.agent.git_operations import SnapshotInfo
from app.agent.snapshot_manager import SnapshotManager


def _snapshot(tag="agent-s-1-abcdef12", commit="abc123"):
    return SnapshotInfo(
        tag=tag, commit_hash=commit, message="msg",
        timestamp="2026-01-01T00:00:00", files_changed=[],
    )


def _ops(**overrides):
    ops = MagicMock()
    ops.init_repo = AsyncMock()
    ops.get_current_branch = AsyncMock(return_value="main")
    ops.create_branch = AsyncMock(return_value="feat")
    ops.commit_snapshot = AsyncMock(return_value="abc123")
    ops.create_tag = AsyncMock(return_value=True)
    ops.list_snapshots = AsyncMock(return_value=[])
    ops.get_head_commit = AsyncMock(return_value="head")
    ops.checkout_mainline = AsyncMock(return_value=True)
    ops.revert_to_commit = AsyncMock(return_value=True)
    ops.diff_files_between_commits = AsyncMock(return_value=["a.py"])
    ops.delete_branch = AsyncMock(return_value=True)
    ops.merge_branch = AsyncMock(return_value=True)
    for key, value in overrides.items():
        setattr(ops, key, value)
    return ops


async def test_save_snapshot_branch_creation_failure_is_logged():
    ops = _ops(create_branch=AsyncMock(return_value=None))
    ops.get_current_branch = AsyncMock(return_value="main")
    manager = SnapshotManager(ops)

    result = await manager.save_snapshot(
        Path("/tmp/p"), "s", "desc", [], branch_name="feat"
    )

    assert result is not None
    ops.create_branch.assert_awaited_once()


async def test_save_snapshot_tag_failure_returns_none():
    manager = SnapshotManager(_ops(create_tag=AsyncMock(return_value=False)))

    assert await manager.save_snapshot(Path("/tmp/p"), "s", "desc", []) is None


async def test_rollback_finds_snapshot_via_git_list():
    snapshot = _snapshot()
    ops = _ops(list_snapshots=AsyncMock(return_value=[snapshot]))
    manager = SnapshotManager(ops)

    result = await manager.rollback_to_snapshot(Path("/tmp/p"), snapshot.tag)

    assert result.success is True
    assert result.previous_tag == snapshot.tag


async def test_rollback_missing_snapshot_returns_none():
    manager = SnapshotManager(_ops())
    assert await manager.rollback_to_snapshot(Path("/tmp/p"), "missing") is None


async def test_rollback_keeps_branch_when_checkout_fails():
    snapshot = _snapshot()
    ops = _ops(
        get_current_branch=AsyncMock(return_value="agent-feature"),
        checkout_mainline=AsyncMock(return_value=False),
    )
    manager = SnapshotManager(ops)
    manager.snapshots[snapshot.tag] = snapshot

    result = await manager.rollback_to_snapshot(Path("/tmp/p"), snapshot.tag)

    assert result.success is True
    assert result.branch_deleted is False
    ops.delete_branch.assert_not_awaited()


async def test_rollback_reports_branch_delete_failure():
    snapshot = _snapshot()
    ops = _ops(
        get_current_branch=AsyncMock(return_value="agent-feature"),
        delete_branch=AsyncMock(return_value=False),
    )
    manager = SnapshotManager(ops)
    manager.snapshots[snapshot.tag] = snapshot

    result = await manager.rollback_to_snapshot(Path("/tmp/p"), snapshot.tag)

    assert result.branch_deleted is False


async def test_rollback_skips_restore_listing_when_head_missing():
    snapshot = _snapshot()
    ops = _ops(get_head_commit=AsyncMock(return_value=""))
    manager = SnapshotManager(ops)
    manager.snapshots[snapshot.tag] = snapshot

    result = await manager.rollback_to_snapshot(Path("/tmp/p"), snapshot.tag)

    assert result.files_restored == []
    ops.diff_files_between_commits.assert_not_awaited()


async def test_finalize_merges_and_cleans_branch():
    ops = _ops()
    manager = SnapshotManager(ops)

    result = await manager.finalize_session(Path("/tmp/p"), "s", True, "feat")

    assert result.merged is True
    assert result.final_tag == "agent-s-final"
    assert result.branch_deleted is True
    ops.delete_branch.assert_awaited_once()


async def test_finalize_merge_failure_offers_rollback():
    manager = SnapshotManager(_ops(merge_branch=AsyncMock(return_value=False)))

    result = await manager.finalize_session(Path("/tmp/p"), "s", True, "feat")

    assert result.merged is False
    assert result.rollback_offered is True


async def test_finalize_failed_session_offers_rollback():
    ops = _ops()
    manager = SnapshotManager(ops)

    result = await manager.finalize_session(Path("/tmp/p"), "s", False, "feat")

    assert result.merged is False
    assert result.rollback_offered is True
    ops.merge_branch.assert_not_awaited()


async def test_finalize_without_branch_is_noop_merge():
    manager = SnapshotManager(_ops())

    result = await manager.finalize_session(Path("/tmp/p"), "s", True)

    assert result == type(result)(merged=True)


async def test_save_snapshot_skips_branch_switch_when_already_on_branch():
    ops = _ops(get_current_branch=AsyncMock(return_value="feat"))
    manager = SnapshotManager(ops)

    result = await manager.save_snapshot(
        Path("/tmp/p"), "s", "desc", [], branch_name="feat"
    )

    assert result is not None
    ops.create_branch.assert_not_awaited()


async def test_rollback_scans_past_unrelated_snapshots():
    target = _snapshot(tag="target", commit="t")
    other = _snapshot(tag="other", commit="o")
    ops = _ops(list_snapshots=AsyncMock(return_value=[other, target]))
    manager = SnapshotManager(ops)

    result = await manager.rollback_to_snapshot(Path("/tmp/p"), "target")

    assert result.success is True
    assert result.previous_tag == "target"


async def test_save_snapshot_returns_none_when_commit_empty():
    ops = _ops(commit_snapshot=AsyncMock(return_value=""))
    manager = SnapshotManager(ops)

    assert await manager.save_snapshot(Path("/tmp/p"), "s", "desc", []) is None
