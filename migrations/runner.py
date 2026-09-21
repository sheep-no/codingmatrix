# migrations/runner.py
"""
完全独立的异步迁移运行器，支持 MySQL 和 SQLite
"""
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from app.core.config import settings  # 使用统一的配置
from app.models.base import Base

# 导入所有模型以注册到 Base.metadata
from app.models.server_config import ServerConfig
from app.models.user import User
from app.models.github_config import GithubUserConfig
from app.models.history import History
from app.models.task import Task
from app.db.models import ProjectSession
from app.models.chat_history import ChatHistory, ChatSummary, CustomCharacter, UserPreference
from app.models.unified_state import (
    Session, Message, SessionEvent, TaskEvent, Checkpoint, Artifact,
    StateCompatibilityMapping, StateRetentionRecord,
    StateReconciliationRecord,
)


async def run_async_migrations():
    """根据 DATABASE_URL 自动适配数据库类型"""
    database_url = settings.DATABASE_URL
    parsed = urlparse(database_url)
    db_type = parsed.scheme.split('+')[0]  # 'mysql' or 'sqlite'

    print(f"正在初始化数据库: {db_type}://{parsed.hostname or 'localhost'}/{parsed.path.strip('/')}")

    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        if db_type == 'sqlite':
            # SQLite: 检查 sqlite_master
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            existing_tables = {row[0] for row in result}
        elif db_type == 'mysql':
            # MySQL: 检查 information_schema
            db_name = parsed.path.strip('/')
            result = await conn.execute(
                text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db_name}'")
            )
            existing_tables = {row[0] for row in result}
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        # 只创建不存在的表
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                await conn.execute(CreateTable(table))
                print(f"✅ 创建表: {table_name}")
                # CreateTable 只建表结构，不建索引；tasks.task_id 等唯一索引是其他表外键的解析目标
                for index in table.indexes:
                    await conn.execute(CreateIndex(index))
                    print(f"✅ 创建索引: {index.name}")
            else:
                print(f"⏭ 表已存在，跳过: {table_name}")

        # create_all does not evolve an existing tasks table. Add the unified
        # state columns here so upgrades remain safe for existing SQLite/MySQL
        # deployments that predate the unified state model.
        if "tasks" in existing_tables:
            if db_type == "sqlite":
                columns_result = await conn.execute(text("PRAGMA table_info(tasks)"))
                task_columns = {row[1] for row in columns_result}
            else:
                columns_result = await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :db_name AND table_name = 'tasks'"
                    ),
                    {"db_name": parsed.path.strip("/")},
                )
                task_columns = {row[0] for row in columns_result}

            additions = {
                "session_id": "VARCHAR(64)",
                "revision": "INTEGER NOT NULL DEFAULT 0",
                "idempotency_key": "VARCHAR(128)",
                "stage": "VARCHAR(80)",
                "lease_until": "DATETIME",
                "error_json": "JSON",
                "result_json": "JSON",
                "updated_at": "DATETIME",
                "finished_at": "DATETIME",
                "outline_id": "VARCHAR(64)",
                "outline_version": "INTEGER",
                "quality_mode": "VARCHAR(20)",
                "quality_report_artifact_id": "VARCHAR(64)",
            }
            for column_name, column_type in additions.items():
                if column_name not in task_columns:
                    await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}"))
                    print(f"已升级 tasks 表字段: {column_name}")

        if "project_sessions" in existing_tables:
            if db_type == "sqlite":
                columns_result = await conn.execute(text("PRAGMA table_info(project_sessions)"))
                project_columns = {row[1] for row in columns_result}
                indexes_result = await conn.execute(text("PRAGMA index_list(project_sessions)"))
                project_indexes = {row[1] for row in indexes_result}
            else:
                columns_result = await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :db_name AND table_name = 'project_sessions'"
                    ),
                    {"db_name": parsed.path.strip("/")},
                )
                project_columns = {row[0] for row in columns_result}
                indexes_result = await conn.execute(
                    text(
                        "SELECT DISTINCT index_name FROM information_schema.statistics "
                        "WHERE table_schema = :db_name AND table_name = 'project_sessions'"
                    ),
                    {"db_name": parsed.path.strip("/")},
                )
                project_indexes = {row[0] for row in indexes_result}

            project_additions = {
                "lifecycle_status": "VARCHAR(30) NOT NULL DEFAULT 'active'",
                "retention_class": "VARCHAR(30) NOT NULL DEFAULT 'standard'",
                "pinned": "BOOLEAN NOT NULL DEFAULT FALSE",
                "archived_at": "DATETIME",
                "purge_after": "DATETIME",
            }
            for column_name, column_type in project_additions.items():
                if column_name not in project_columns:
                    await conn.execute(
                        text(f"ALTER TABLE project_sessions ADD COLUMN {column_name} {column_type}")
                    )
                    print(f"已升级 project_sessions 表字段: {column_name}")

            if "ix_project_sessions_lifecycle_status" not in project_indexes:
                await conn.execute(
                    text(
                        "CREATE INDEX ix_project_sessions_lifecycle_status "
                        "ON project_sessions (lifecycle_status)"
                    )
                )
                print("已升级 project_sessions 索引: ix_project_sessions_lifecycle_status")

        if "user_preferences" in existing_tables:
            if db_type == "sqlite":
                columns_result = await conn.execute(text("PRAGMA table_info(user_preferences)"))
                preference_columns = {row[1] for row in columns_result}
            else:
                columns_result = await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :db_name AND table_name = 'user_preferences'"
                    ),
                    {"db_name": parsed.path.strip("/")},
                )
                preference_columns = {row[0] for row in columns_result}

            additions = {
                "status": "VARCHAR(20) NOT NULL DEFAULT 'confirmed'",
                "consent_source": "VARCHAR(30) NOT NULL DEFAULT 'system_derived'",
                "visibility": "VARCHAR(30) NOT NULL DEFAULT 'companion_allowed'",
                "last_used_at": "DATETIME",
            }
            for column_name, column_type in additions.items():
                if column_name not in preference_columns:
                    await conn.execute(
                        text(f"ALTER TABLE user_preferences ADD COLUMN {column_name} {column_type}")
                    )
                    print(f"已升级 user_preferences 表字段: {column_name}")

        # Permission.user_id 的唯一约束是后补的模型约束（2026-09-18），
        # CreateTable 只对新库生效；既有库里已经有 permission 表，需要补建
        # 唯一索引，否则同一用户可能出现多行权限，uselist=False 读取会抛
        # MultipleResultsFound。存在重复数据时只告警不删除，留待人工清理。
        if "permission" in existing_tables and not await _has_unique_user_id_index(
            conn, db_type, parsed.path.strip("/")
        ):
            duplicates_result = await conn.execute(
                text(
                    "SELECT user_id FROM permission "
                    "GROUP BY user_id HAVING COUNT(*) > 1 LIMIT 5"
                )
            )
            duplicates = [row[0] for row in duplicates_result]
            if duplicates:
                print(f"⚠️ permission 表存在重复 user_id={duplicates}，跳过唯一索引创建")
            else:
                await conn.execute(
                    text("CREATE UNIQUE INDEX uq_permission_user_id ON permission (user_id)")
                )
                print("已升级 permission 表唯一索引: uq_permission_user_id")

    await engine.dispose()


async def _has_unique_user_id_index(conn, db_type: str, db_name: str) -> bool:
    """判断 permission 表是否已有仅覆盖 user_id 的唯一约束/索引。"""
    if db_type == "sqlite":
        indexes_result = await conn.execute(text("PRAGMA index_list(permission)"))
        for index_row in indexes_result:
            index_name, is_unique = index_row[1], index_row[2]
            if not is_unique:
                continue
            columns_result = await conn.execute(
                text(f"PRAGMA index_info('{index_name}')")
            )
            if [row[2] for row in columns_result] == ["user_id"]:
                return True
        return False

    columns_result = await conn.execute(
        text(
            "SELECT index_name, column_name FROM information_schema.statistics "
            "WHERE table_schema = :db_name AND table_name = 'permission' "
            "AND non_unique = 0 ORDER BY index_name, seq_in_index"
        ),
        {"db_name": db_name},
    )
    indexes: dict[str, list[str]] = {}
    for index_name, column_name in columns_result:
        indexes.setdefault(index_name, []).append(column_name)
    return any(columns == ["user_id"] for columns in indexes.values())
