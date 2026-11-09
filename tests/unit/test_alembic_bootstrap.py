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
KEY_TABLES = (
    "user",
    "tasks",
    "permission",
    # 这些模型原先没有在 migrations/env.py 里导入，空库 upgrade head 会漏建。
    "github_user_configs",
    "project_sessions",
    "workflow_history",
    "image_generation_history",
    "conversation_messages",
    "saved_projects",
    "server_config",
)


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


def _run_user_management_migration(create_system_logs: bool) -> set:
    """在受控 schema 上直接执行 20260425 的 upgrade()。

    空库走 env.py 的 metadata 旁路，不会重放历史迁移，因此该迁移里的悬空
    调用只在「已有 alembic_version 的库」这条路径上暴露，需要单独回归。
    """
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text

    module_path = ROOT / "migrations" / "versions" / "20260425_add_user_management_indexes.py"
    spec = importlib.util.spec_from_file_location("user_management_indexes", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            'CREATE TABLE "user"(id INTEGER PRIMARY KEY, permission_level TEXT, '
            "created_at TEXT, username TEXT, email TEXT)"
        ))
        conn.execute(text(
            'CREATE TABLE "permission"(id INTEGER PRIMARY KEY, permission_level TEXT)'
        ))
        if create_system_logs:
            conn.execute(text(
                "CREATE TABLE system_logs(id INTEGER PRIMARY KEY, timestamp TEXT, level TEXT)"
            ))
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            module.upgrade()
        names = {row[0] for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        )}
    engine.dispose()
    return names


def test_user_management_indexes_migration_runs():
    """20260425 迁移不得含未定义调用（原 if_exists_exists 会 NameError）。"""
    indexes = _run_user_management_migration(create_system_logs=True)
    assert "ix_logs_timestamp_level" in indexes
    assert "ix_user_permission_created" in indexes


def test_user_management_indexes_migration_tolerates_missing_system_logs():
    """system_logs 不存在时跳过日志索引，其余索引仍要建出来。"""
    indexes = _run_user_management_migration(create_system_logs=False)
    assert "ix_logs_timestamp_level" not in indexes
    assert "ix_user_permission_created" in indexes
    assert "ix_user_username" in indexes


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+pymysql://u:p@localhost/db",
        "postgresql://u:p@localhost/db",
    ],
)
def test_offline_sql_generation_reaches_head(tmp_path, database_url):
    """`alembic upgrade head --sql` 必须能生成完整脚本。

    历史迁移里有多处 `sa.inspect(op.get_bind())`，离线模式拿到的是
    MockConnection，无法反射。缺少 `as_sql` 分支时这里会直接抛
    NoInspectionAvailable，CI 与审计常用该命令导出变更 SQL。
    """
    env = _alembic_env(tmp_path / "offline.db")
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    script = result.stdout
    assert "NoInspectionAvailable" not in result.stderr
    assert "github_user_configs" in script
    assert "verified_at" in script
    assert _head_revision() in script
