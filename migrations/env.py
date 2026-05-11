# migrations/env.py
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from app.core.config import BASE_DIR
from app.models.base import Base

from app.models.aicloud import AicloudSession, AicloudMessage, AicloudReview, AicloudAuditLog
from app.models.user import User
from app.models.history import History
from app.models.chat_history import ChatHistory
from app.models.file import File
from app.models.task import Task
from app.models.Permission import Permission

# 初始化配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 动态构建数据库 URL
db_path = Path(BASE_DIR) / "app.db"
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
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
    """同步执行迁移"""
    context.configure(connection=connection, target_metadata=target_metadata)
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