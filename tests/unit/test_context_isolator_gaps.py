"""上下文隔离器路径/文件保护与单例补测。"""

import threading

import pytest

from app.utils.aicloud import context_isolator as module
from app.utils.aicloud.context_isolator import (
    ContextIsolator,
    get_isolator,
    is_protected_file,
    is_protected_path,
    setup_sandbox,
)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    monkeypatch.setattr(module, "_isolator_instance", None)


def test_setup_sandbox_resets_main_env():
    isolator = ContextIsolator()
    isolator.main_project_env = {"SECRET": "x"}
    isolator.setup_sandbox(42)
    assert isolator.sandbox_env == {
        "HOME": "/sandbox/42",
        "WORK_DIR": "/sandbox/42/workspace",
    }
    assert isolator.main_project_env == {}


@pytest.mark.parametrize("path", [
    "/etc/passwd",
    "/root/.bashrc",
    "/home/alice/.ssh/id_rsa",
    "/proc/self/environ",
    "/sys/kernel",
    "/var/log/syslog",
    "/usr/bin/python",
    "/boot/vmlinuz",
    "/dev/null",
    "/run/lock",
    "/snap/core",
    "/srv/data",
    "/opt/app",
])
def test_block_protected_directories(path):
    assert is_protected_path(path) is True


def test_block_protected_directory_lookalike():
    assert is_protected_path("/workspace/src/etc_helper.py") is False


def test_block_protected_wildcard_home():
    assert is_protected_path("/home/bob/.ssh/config") is True
    assert is_protected_path("/home/bob/public/config") is False


def test_block_protected_custom_pattern_contains():
    isolator = ContextIsolator()
    original = module.PROTECTED_PATHS
    module.PROTECTED_PATHS = ["danger"]
    try:
        assert isolator.block_protected_paths("/tmp/danger/file") is True
    finally:
        module.PROTECTED_PATHS = original


@pytest.mark.parametrize("path", [
    ".env",
    "app/.env.production",
    "keys/server.key",
    "cert.pem",
    "credentials.json",
    "secrets.json",
    "user.credentials",
    "id_rsa",
    "id_ed25519",
    ".git/config",
    ".git/credentials",
    "db.password",
    "token.secret",
])
def test_block_protected_files(path):
    assert is_protected_file(path) is True


def test_block_protected_files_allows_normal():
    assert is_protected_file("/workspace/app/main.py") is False


def test_block_protected_git_pattern_by_parts():
    assert is_protected_file("/workspace/project/config") is False
    assert is_protected_file("/workspace/.git/config") is True


def test_get_isolator_returns_singleton():
    first = get_isolator()
    assert get_isolator() is first


def test_get_isolator_double_checked_locking(monkeypatch):
    created = []

    class FakeIsolator:
        def __init__(self):
            created.append(True)

    monkeypatch.setattr(module, "ContextIsolator", FakeIsolator)
    monkeypatch.setattr(module, "_isolator_instance", None)

    result = module.get_isolator()

    assert isinstance(result, FakeIsolator)
    assert created == [True]


def test_setup_sandbox_function_sets_global_isolator():
    env = setup_sandbox(7)
    assert env["HOME"] == "/sandbox/7"
    assert get_isolator().sandbox_env is env


def test_block_protected_wildcard_directory_itself():
    assert is_protected_path("/home/bob/.ssh") is True


def test_block_protected_custom_pattern_non_match_continues():
    isolator = ContextIsolator()
    original = module.PROTECTED_PATHS
    module.PROTECTED_PATHS = ["danger"]
    try:
        assert isolator.block_protected_paths("/tmp/safe/file") is False
    finally:
        module.PROTECTED_PATHS = original


def test_get_isolator_inner_recheck(monkeypatch):
    created = []

    class FakeIsolator:
        def __init__(self):
            created.append(True)

    class RacingLock:
        def __enter__(self):
            module._isolator_instance = FakeIsolator()
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(module, "ContextIsolator", FakeIsolator)
    monkeypatch.setattr(module, "_isolator_instance", None)
    monkeypatch.setattr(module, "_isolator_lock", RacingLock())

    result = module.get_isolator()

    assert isinstance(result, FakeIsolator)
    assert created == [True]
