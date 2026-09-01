import shutil

from app.agent import utils


def test_runtime_validation_is_delegated_to_local_agent_host(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda command: None)

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "print('hello')"},
        level="run",
    )

    assert passed is True
    assert errors == []


def test_cloud_validation_skips_when_bwrap_is_unavailable(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda command: None)

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "print('hello')"},
        level="syntax",
    )

    assert passed is True
    assert errors == []
