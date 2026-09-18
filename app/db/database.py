from sqlalchemy import AsyncAdaptedQueuePool, event
from app.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, \
    async_sessionmaker, AsyncSession


_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    # SQLite 默认 busy_timeout=0，并发写立即 database is locked；timeout 单位秒。
    connect_args={"check_same_thread": False, "timeout": 30} if _IS_SQLITE else {},
)


if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, connection_record):
        """每个 SQLite 连接开启外键约束并切 WAL，供多进程并发写使用。"""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


# 优化的会话工厂
async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,  # 减少自动刷新开销
    autocommit=False,
)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            # 确保会话关闭
            await session.close()

