"""
数据库迁移 - 添加 metadata_json 字段到 history 表
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.database import engine, async_session


async def migrate():
    """添加 metadata_json 字段"""
    
    print("🔍 检查数据库连接...")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        return False
    
    print("\n📝 迁移 history 表...")
    
    async with async_session() as session:
        try:
            print("📌 添加 metadata_json 字段...")
            await session.execute(text("""
                ALTER TABLE history 
                ADD COLUMN metadata_json TEXT
            """))
            await session.commit()
            print("✅ 字段添加成功")
            
            print("\n✅ 迁移完成！")
            return True
            
        except Exception as e:
            await session.rollback()
            if "duplicate" in str(e).lower():
                print("⚠️ 字段已存在，跳过迁移")
                return True
            print(f"❌ 迁移失败：{e}")
            return False


if __name__ == "__main__":
    success = asyncio.run(migrate())
    sys.exit(0 if success else 1)
