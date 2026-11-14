"""aicloud sandbox 路径工具补测。"""

from pathlib import Path

from app.utils.aicloud import sandbox


def test_paths_are_derived_from_base_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "SANDBOX_BASE_DIR", str(tmp_path / "sandbox"))

    assert sandbox.get_sandbox_path(7) == str(tmp_path / "sandbox" / "7")
    assert sandbox.get_sandbox_workspace_path(7) == str(
        tmp_path / "sandbox" / "7" / "workspace"
    )


async def test_ensure_user_sandbox_creates_both_directories(monkeypatch, tmp_path):
    base = tmp_path / "sandbox"
    monkeypatch.setattr(sandbox, "SANDBOX_BASE_DIR", str(base))

    result = await sandbox.ensure_user_sandbox(3)

    assert result == str(base / "3")
    assert (base / "3").is_dir()
    assert (base / "3" / "workspace").is_dir()


async def test_ensure_user_sandbox_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "SANDBOX_BASE_DIR", str(tmp_path / "sandbox"))

    first = await sandbox.ensure_user_sandbox(1)
    second = await sandbox.ensure_user_sandbox(1)

    assert first == second
    assert Path(first).is_dir()
