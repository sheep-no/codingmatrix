"""补齐 SandboxFileOperator 的路径归一、读取审查与写入审查。"""

from pathlib import Path

import pytest

from app.utils.aicloud.sandbox_operator import SandboxFileOperator


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(SandboxFileOperator, "SANDBOX_BASE_DIR", str(tmp_path / "sandbox"))
    operator = SandboxFileOperator(user_id=7)
    Path(operator.base_path).mkdir(parents=True)
    return operator


def test_absolute_path_joins_base(sandbox):
    path = sandbox.get_absolute_path("a/b.txt")

    assert path == str(Path(sandbox.base_path) / "a" / "b.txt")


def test_absolute_path_strips_workspace_prefix(sandbox):
    path = sandbox.get_absolute_path("workspace/a.txt")

    assert path == str(Path(sandbox.base_path) / "a.txt")


def test_absolute_path_normalizes_traversal(sandbox):
    path = sandbox.get_absolute_path("a/../b.txt")

    assert path == str(Path(sandbox.base_path) / "b.txt")


@pytest.mark.asyncio
async def test_read_with_review_filters_and_analyzes(sandbox):
    (Path(sandbox.base_path) / "note.txt").write_text(
        "password=secret\nhello", encoding="utf-8"
    )

    result = await sandbox.read_with_review("note.txt")

    assert result["raw_content"].startswith("password=secret")
    assert "secret" not in result["content"]
    assert result["ai_passed"] is True
    assert result["path"] == "note.txt"
    assert result["size"] == len("password=secret\nhello")


@pytest.mark.asyncio
async def test_read_with_review_missing_file_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        await sandbox.read_with_review("missing.txt")


@pytest.mark.asyncio
async def test_write_with_review_returns_pending(sandbox):
    result = await sandbox.write_with_review("out.txt", "print('hi')")

    assert result["success"] is False
    assert result["review_status"] == "pending"
    assert result["analysis"]["operation_type"] == "write"
    assert result["path"] == "out.txt"
    assert not (Path(sandbox.base_path) / "out.txt").exists()


@pytest.mark.asyncio
async def test_write_with_review_rejects_traversal_before_analysis(sandbox, monkeypatch):
    calls = []

    async def fake_analysis(*args, **kwargs):
        calls.append(args)
        return {}

    monkeypatch.setattr(
        "app.utils.aicloud.content_analyzer.deep_content_analysis", fake_analysis
    )

    with pytest.raises(Exception):
        await sandbox.write_with_review("../escape.txt", "data")

    assert calls == []
