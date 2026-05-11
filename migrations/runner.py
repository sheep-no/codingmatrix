# migrations/async_runner.py
"""
完全独立的异步迁移运行器，支持 MySQL 和 SQLite
"""
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateTable

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from app.core.config import settings  # 使用统一的配置
from app.models.base import Base

# 导入所有模型以注册到 Base.metadata
from app.models.server_config import ServerConfig
from app.models.user import User
from app.models.history import History


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
            else:
                print(f"⏭ 表已存在，跳过: {table_name}")

    await engine.dispose()