"""GitOperations 错误分支与降级路径覆盖。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import git_operations as module
from app.agent.git_operations import GitOperations


def _completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout.encode() if isinstance(stdout, str) else stdout,
        stderr=stderr.encode() if isinstance(stderr, str) else stderr,
    )


def _patch_thread(monkeypatch, exc=None):
    async def fake_thread(fn, *args, **kwargs):
        if exc is not None:
            raise exc
        return fn(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", fake_thread)


@pytest.mark.asyncio
async def test_init_repo_existing_git_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    assert await GitOperations().init_repo(tmp_path) is True


@pytest.mark.asyncio
async def test_init_repo_writes_gitignore_and_handles_failure(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(0))

    assert await GitOperations().init_repo(tmp_path) is True
    assert (tmp_path / ".gitignore").exists()


@pytest.mark.asyncio
async def test_init_repo_git_failure_returns_false(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="boom")
    )

    assert await GitOperations().init_repo(tmp_path) is False


@pytest.mark.asyncio
async def test_init_repo_exception_returns_false(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("no git"))

    assert await GitOperations().init_repo(tmp_path) is False


@pytest.mark.asyncio
async def test_create_branch_falls_back_to_existing(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    responses = iter([
        _completed(1, stderr="no main"),
        _completed(0),
        _completed(1, stderr="exists"),
        _completed(0),
    ])

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: next(responses))

    assert await GitOperations().create_branch(tmp_path, "feat") == "feat"


@pytest.mark.asyncio
async def test_create_branch_returns_none_when_both_fail(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    responses = iter([
        _completed(0),
        _completed(1, stderr="exists"),
        _completed(1, stderr="cannot switch"),
    ])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: next(responses))

    assert await GitOperations().create_branch(tmp_path, "feat") is None


@pytest.mark.asyncio
async def test_create_branch_exception_returns_none(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("boom"))

    assert await GitOperations().create_branch(tmp_path, "feat") is None


@pytest.mark.asyncio
async def test_commit_snapshot_add_failure_returns_none(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="add")
    )

    assert await GitOperations().commit_snapshot(tmp_path, "msg") is None


@pytest.mark.asyncio
async def test_commit_snapshot_builds_metadata_message(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    commands = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return _completed(0, stdout="abc123\n")
        return _completed(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    sha = await GitOperations().commit_snapshot(
        tmp_path,
        "msg",
        metadata={"files": ["a.py", "b.py"], "model": "m", "duration": 3},
    )

    assert sha == "abc123"
    commit_cmd = next(cmd for cmd in commands if cmd[:2] == ["git", "commit"])
    assert "Files: a.py, b.py" in commit_cmd[-1]
    assert "Model: m" in commit_cmd[-1]
    assert "Duration: 3s" in commit_cmd[-1]


@pytest.mark.asyncio
async def test_commit_snapshot_no_metadata_and_failure(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)

    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["git", "commit"]:
            return _completed(1, stderr="nothing")
        return _completed(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert await GitOperations().commit_snapshot(tmp_path, "msg") is None


@pytest.mark.asyncio
async def test_commit_snapshot_exception_returns_none(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("boom"))

    assert await GitOperations().commit_snapshot(tmp_path, "msg") is None


@pytest.mark.asyncio
async def test_create_tag_failure_and_exception(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="tag")
    )
    assert await GitOperations().create_tag(tmp_path, "v1") is None

    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    assert await GitOperations().create_tag(tmp_path, "v1") is None


@pytest.mark.asyncio
async def test_merge_branch_checkout_failure_and_merge_failure(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="checkout")
    )
    assert await GitOperations().merge_branch(tmp_path, "feat") is False

    responses = iter([_completed(0), _completed(1), _completed(0)])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: next(responses))
    assert await GitOperations().merge_branch(tmp_path, "feat") is False


@pytest.mark.asyncio
async def test_merge_branch_exception_returns_false(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("boom"))

    assert await GitOperations().merge_branch(tmp_path, "feat") is False


@pytest.mark.asyncio
async def test_delete_revert_checkout_exception_paths(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    ops = GitOperations()

    assert await ops.delete_branch(tmp_path, "feat") is False
    assert await ops.revert_to_commit(tmp_path, "abc") is False
    assert await ops.checkout_branch(tmp_path, "feat") is False


@pytest.mark.asyncio
async def test_revert_failure(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="reset")
    )

    assert await GitOperations().revert_to_commit(tmp_path, "abc") is False


@pytest.mark.asyncio
async def test_list_snapshots_skips_malformed_and_handles_exception(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)

    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["git", "tag"]:
            return _completed(0, stdout="v1\nv2\n")
        if cmd[-1] == "v1":
            return _completed(0, stdout="hash\x1fmsg\x1f2020-01-01\n")
        return _completed(0, stdout="only-part\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    snapshots = await GitOperations().list_snapshots(tmp_path)

    assert [s.tag for s in snapshots] == ["v1"]
    assert snapshots[0].message == "msg"

    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    assert await GitOperations().list_snapshots(tmp_path) == []


@pytest.mark.asyncio
async def test_diff_and_branch_exception_paths(tmp_path, monkeypatch):
    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    ops = GitOperations()

    assert await ops.diff_between_commits(tmp_path, "a", "b") == ""
    assert await ops.get_current_branch(tmp_path) == ""
    assert await ops.get_head_commit(tmp_path) == ""


@pytest.mark.asyncio
async def test_get_head_commit_nonzero_return(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stdout="HEAD\n")
    )

    assert await GitOperations().get_head_commit(tmp_path) == ""


@pytest.mark.asyncio
async def test_checkout_mainline_branches(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    ops = GitOperations()

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(0))
    assert await ops.checkout_mainline(tmp_path) == "main"

    responses = iter([_completed(1), _completed(0)])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: next(responses))
    assert await ops.checkout_mainline(tmp_path) == "master"

    responses = iter([_completed(1), _completed(1), _completed(0)])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: next(responses))
    assert await ops.checkout_mainline(tmp_path) == "main"

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(1))
    assert await ops.checkout_mainline(tmp_path) is None

    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    assert await ops.checkout_mainline(tmp_path) is None


@pytest.mark.asyncio
async def test_diff_files_between_commits_branches(tmp_path, monkeypatch):
    ops = GitOperations()
    assert await ops.diff_files_between_commits(tmp_path, "", "b") == []

    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(1, stderr="diff")
    )
    assert await ops.diff_files_between_commits(tmp_path, "a", "b") == []

    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(0, stdout="a.py\n\nb.py\n")
    )
    assert await ops.diff_files_between_commits(tmp_path, "a", "b") == ["a.py", "b.py"]

    _patch_thread(monkeypatch, exc=RuntimeError("boom"))
    assert await ops.diff_files_between_commits(tmp_path, "a", "b") == []


@pytest.mark.asyncio
async def test_create_tag_success(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(0))

    assert await GitOperations().create_tag(tmp_path, "v1") == "v1"


@pytest.mark.asyncio
async def test_commit_snapshot_metadata_variants(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    messages = []

    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["git", "commit"]:
            messages.append(cmd[-1])
        if cmd[:2] == ["git", "rev-parse"]:
            return _completed(0, stdout="sha\n")
        return _completed(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ops = GitOperations()

    await ops.commit_snapshot(tmp_path, "m", metadata={"files": ["a.py"]})
    await ops.commit_snapshot(tmp_path, "m", metadata={"model": "x"})
    await ops.commit_snapshot(tmp_path, "m", metadata={"duration": 1})
    await ops.commit_snapshot(tmp_path, "m", metadata={"other": 1})

    assert "Files: a.py" in messages[0]
    assert "Model: x" in messages[1]
    assert "Duration: 1s" in messages[2]
    assert messages[3] == "m"


@pytest.mark.asyncio
async def test_merge_branch_success_without_abort(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    commands = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return _completed(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert await GitOperations().merge_branch(tmp_path, "feat") is True
    assert not any(cmd[:3] == ["git", "merge", "--abort"] for cmd in commands)


@pytest.mark.asyncio
async def test_get_current_branch_and_checkout_success(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: _completed(0, stdout="feature\n"),
    )
    ops = GitOperations()

    assert await ops.get_current_branch(tmp_path) == "feature"
    assert await ops.checkout_branch(tmp_path, "feature") is True


@pytest.mark.asyncio
async def test_init_repo_keeps_existing_gitignore(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(0))
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("custom\n", encoding="utf-8")

    assert await GitOperations().init_repo(tmp_path) is True
    assert gitignore.read_text(encoding="utf-8") == "custom\n"


@pytest.mark.asyncio
async def test_diff_between_commits_success(tmp_path, monkeypatch):
    _patch_thread(monkeypatch)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: _completed(0, stdout="diff --git\n"),
    )

    assert await GitOperations().diff_between_commits(tmp_path, "a", "b") == "diff --git\n"
