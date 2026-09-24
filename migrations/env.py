# migrations/env.py
from logging.config import fileConfig
from sqlalchemy import inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from alembic.script import ScriptDirectory
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from app.core.config import settings
from app.models.base import Base

from app.models.aicloud import AicloudSession, AicloudMessage, AicloudReview, AicloudAuditLog
from app.models.user import User
from app.models.history import History
from app.models.chat_history import ChatHistory
from app.models.file import File
from app.models.task import Task
from app.models.unified_state import (
    Session, Message, SessionEvent, TaskEvent, Checkpoint, Artifact,
    StateCompatibilityMapping, StateRetentionRecord,
    StateReconciliationRecord,
)
from app.models.Permission import Permission
from app.models.agent_memory import (
    AgentSession,
    MemoryEntry,
    AgentReflection,
    KnowledgeEntry,
    ToolExecutionLog,
    ModelUsageStats,
)

# 初始化配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 使用统一配置中的数据库 URL：生产由 DATABASE_URL 注入，硬编码 BASE_DIR/app.db
# 会让容器内的 alembic 命令迁移到与 API 不同的空库
DATABASE_URL = settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式"""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """同步执行迁移。

    首次接入（库内尚无 alembic_version）时以 `Base.metadata` 为唯一真相来源：
    生产启动由 `migrations/runner.py` 依据同一份 metadata 建表补列，而 alembic
    历史迁移链无法在空库重放——起点 `56882bedb846` 是空迁移，紧随的
    `a1b2c3d4e5f6` 就假设 `user` 等基础表已存在。此处先按 metadata 建全量表，
    再把版本直接登记为 head，避免重放这段无法自洽的伪历史。

    已有 alembic_version 的库走标准迁移，只执行尚未应用的新修订。
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    if not inspect(connection).has_table("alembic_version"):
        Base.metadata.create_all(bind=connection, checkfirst=True)
        script = ScriptDirectory.from_config(config)
        context.get_context().stamp(script, script.get_current_head())
        connection.commit()
        return

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """在线模式（异步）"""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
