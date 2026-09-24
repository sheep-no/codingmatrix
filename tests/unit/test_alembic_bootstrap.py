"""Alembic 首次接入回归：空库与 runner.py 管理的库都必须能 `upgrade head`。

历史状态是两条轨道互相冲突：

- 空库 `upgrade head` 失败于 `no such table: main.user`——迁移链起点
  `56882bedb846` 是空迁移，紧随的 `a1b2c3d4e5f6` 就对 `user` 等表建索引。
- `runner.py` 管理过的库 `upgrade head` 失败于 `duplicate column name`——
  runner.py 已按 `Base.metadata` 提前建表补列。

`migrations/env.py` 现在的契约是：库内没有 `alembic_version` 时，`Base.metadata`
即真相来源，先建全量表再把版本登记为 head；已有版本的库走标准迁移。

用子进程驱动 alembic 命令，避免在测试进程内污染 `settings` 单例与测试库。
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "configs" / "alembic.ini"
KEY_TABLES = ("user", "tasks", "permission")


def _alembic_env(db_path: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ENV"] = "development"
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    return env


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=ROOT,
        env=_alembic_env(db_path),
        capture_output=True,
        text=True,
        timeout=180,
    )


def _seed_with_runner(db_path: Path) -> None:
    """用生产启动路径上的 runner.py 建库，模拟既有部署。"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio; from migrations.runner import run_async_migrations; "
            "asyncio.run(run_async_migrations())",
        ],
        cwd=ROOT,
        env=_alembic_env(db_path),
        capture_output=True,
        text=True,
        timeout=180,
    )


def _tables(db_path: Path) -> set:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _version_rows(db_path: Path) -> list:
    conn = sqlite3.connect(db_path)
    try:
        return [row[0] for row in conn.execute("SELECT version_num FROM alembic_version")]
    finally:
        conn.close()


def _head_revision() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "heads"],
        cwd=ROOT,
        env=_alembic_env(ROOT / "unused.db"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()[0]


@pytest.mark.timeout(240)
def test_upgrade_head_bootstraps_empty_database(tmp_path):
    """空库 upgrade head 必须建全量表并登记 head，而非在 a1b2c3d4e5f6 处崩溃。"""
    db = tmp_path / "fresh.db"

    result = _run_alembic(db, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    tables = _tables(db)
    missing = [name for name in KEY_TABLES if name not in tables]
    assert not missing, f"upgrade head 后仍缺表: {missing}"
    assert _version_rows(db) == [_head_revision()]


@pytest.mark.timeout(240)
def test_upgrade_head_is_idempotent(tmp_path):
    """二次执行必须走标准迁移分支并保持版本不变。"""
    db = tmp_path / "repeat.db"
    assert _run_alembic(db, "upgrade", "head").returncode == 0
    head = _head_revision()

    second = _run_alembic(db, "upgrade", "head")
    assert second.returncode == 0, second.stderr
    assert _version_rows(db) == [head]


@pytest.mark.timeout(300)
def test_upgrade_head_accepts_runner_managed_database(tmp_path):
    """runner.py 建过的库再 upgrade head 不得报 duplicate column。"""
    db = tmp_path / "runner.db"
    _seed_with_runner(db)
    seeded = _tables(db)
    assert "user" in seeded, "runner.py 未建出基础表，用例前提不成立"

    result = _run_alembic(db, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert "duplicate column" not in (result.stderr + result.stdout)
    assert _version_rows(db) == [_head_revision()]
    assert "user" in _tables(db)
