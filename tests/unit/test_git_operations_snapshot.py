"""GitOperations / SnapshotManager 快照链路缺陷回归。

覆盖 docs/evolution/modules/git_operations.md 的 GO1/GO2/GO3/GO4/GO5/GO6/GO7/GO10/GO11。
使用真实临时 git 仓库（零 mock），保证子进程语义与生产一致。
"""

import subprocess
from pathlib import Path

from app.agent.git_operations import GitOperations
from app.agent.snapshot_manager import SnapshotManager


def _git(repo: Path, *args, check=False):
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", ".")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "checkout", "-q", "-b", branch)
    return path


def _current_branch(path: Path) -> str:
    return _git(path, "branch", "--show-current").stdout.strip()


def _commit_count(path: Path) -> int:
    return int(_git(path, "rev-list", "--count", "HEAD").stdout.strip() or 0)


def _tags(path: Path) -> list:
    return [t for t in _git(path, "tag", "-l").stdout.strip().splitlines() if t]


async def test_save_snapshot_skips_when_no_changes(tmp_path):
    """GO1: 无变更时不再产生空提交/空快照"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    mgr = SnapshotManager(ops)

    (repo / "a.py").write_text("print(1)\n")
    first = await mgr.save_snapshot(repo, "s1", "first", [])
    assert first is not None
    count_after_first = _commit_count(repo)

    second = await mgr.save_snapshot(repo, "s1", "second", [])
    assert second is None
    assert _commit_count(repo) == count_after_first
    assert len(_tags(repo)) == 1


async def test_list_snapshots_preserves_pipe_in_message(tmp_path):
    """GO5: 描述含 `|` 时不再被截断"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    mgr = SnapshotManager(ops)

    (repo / "a.py").write_text("x\n")
    snapshot = await mgr.save_snapshot(repo, "s1", "fix | auth | flow", [])

    snapshots = await ops.list_snapshots(repo)
    matched = [s for s in snapshots if s.tag == snapshot.tag]
    assert matched and matched[0].message == "fix | auth | flow"


async def test_rollback_reports_real_files_and_branch(tmp_path):
    """GO7: current_tag 用实际分支，files_restored 用真实 git diff"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    mgr = SnapshotManager(ops)

    (repo / "a.py").write_text("v1\n")
    snap1 = await mgr.save_snapshot(repo, "s1", "first", [])
    (repo / "a.py").write_text("v2\n")
    (repo / "b.py").write_text("b\n")
    await mgr.save_snapshot(repo, "s1", "second", [])

    result = await mgr.rollback_to_snapshot(repo, snap1.tag)

    assert result.success is True
    assert result.current_tag == "main"
    assert set(result.files_restored) == {"a.py", "b.py"}
    assert (repo / "a.py").read_text() == "v1\n"
    assert not (repo / "b.py").exists()


async def test_rollback_deletes_feature_branch_and_keeps_snapshot_content(tmp_path):
    """GO2: 先切主线再 reset，feature 分支被删除且回滚内容保留"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    mgr = SnapshotManager(ops)

    (repo / "a.py").write_text("v1\n")
    await mgr.save_snapshot(repo, "s1", "base", [])

    (repo / "feat.py").write_text("f\n")
    snap_feat = await mgr.save_snapshot(
        repo, "s1", "feature", [], branch_name="agent-feature"
    )
    assert snap_feat is not None
    assert _current_branch(repo) == "agent-feature"

    (repo / "a.py").write_text("v2\n")
    await mgr.save_snapshot(repo, "s1", "feature2", [])

    result = await mgr.rollback_to_snapshot(repo, snap_feat.tag, delete_branch=True)

    assert result.success is True
    assert result.branch_deleted is True
    assert result.current_tag == "main"
    assert "agent-feature" not in _git(repo, "branch", "--list").stdout
    assert (repo / "a.py").read_text() == "v1\n"
    assert (repo / "feat.py").read_text() == "f\n"


async def test_rollback_keeps_default_master_branch(tmp_path):
    """GO2/GO7: 默认分支为 master 时被视作主线，不误删、不谎报 main"""
    repo = _init_repo(tmp_path / "proj", branch="master")
    ops = GitOperations()
    mgr = SnapshotManager(ops)

    (repo / "a.py").write_text("v1\n")
    snap1 = await mgr.save_snapshot(repo, "s1", "base", [])
    (repo / "a.py").write_text("v2\n")
    await mgr.save_snapshot(repo, "s1", "second", [])

    result = await mgr.rollback_to_snapshot(repo, snap1.tag, delete_branch=True)

    assert result.success is True
    assert result.current_tag == "master"
    assert result.branch_deleted is False
    assert "master" in _git(repo, "branch", "--list").stdout


async def test_get_current_branch_empty_outside_repo(tmp_path):
    """GO3: 非 git 目录不再谎报 main"""
    ops = GitOperations()
    assert await ops.get_current_branch(tmp_path) == ""


async def test_get_head_commit_empty_without_commits(tmp_path):
    """GO4: 无提交仓库不再返回字面量 HEAD"""
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    ops = GitOperations()
    assert await ops.get_head_commit(repo) == ""


async def test_create_branch_existing_switches_instead_of_failing(tmp_path):
    """GO6: 分支已存在时返回分支名并切换过去，而非返回 None"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    (repo / "a.py").write_text("x\n")
    await ops.commit_snapshot(repo, "base")

    assert await ops.create_branch(repo, "feat") == "feat"
    assert await ops.create_branch(repo, "feat") == "feat"
    assert _current_branch(repo) == "feat"


async def test_merge_branch_returns_false_when_target_missing(tmp_path):
    """GO11: 目标分支不存在时 checkout 失败应显式返回 False"""
    repo = _init_repo(tmp_path / "proj")
    ops = GitOperations()
    (repo / "a.py").write_text("x\n")
    await ops.commit_snapshot(repo, "base")

    assert await ops.merge_branch(repo, "does-not-exist", target="no-such-branch") is False


async def test_commit_snapshot_returns_none_outside_repo(tmp_path):
    """GO10: git add 失败时显式返回 None，而非继续 commit"""
    ops = GitOperations()
    assert await ops.commit_snapshot(tmp_path, "x") is None
