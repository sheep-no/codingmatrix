# app/db/clear.py
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import Settings   # 确保这里指向 SQLite 文件
settings = Settings()
DATABASE_URL = settings.DATABASE_URL
async def delete_non_numeric_conversation_ids():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # 用 text() 包装 SQL
        result = await conn.execute(text("""
            DELETE FROM history
            WHERE conversation_id GLOB '*[^0-9]*'
        """))
        print(f"已删除 {result.rowcount} 条脏数据")

if __name__ == "__main__":
    asyncio.run(delete_non_numeric_conversation_ids())