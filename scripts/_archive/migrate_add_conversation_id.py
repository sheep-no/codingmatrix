"""
数据库迁移脚本 - 添加 conversation_id 字段到 files 表

使用方法：
    python3 scripts/migrate_add_conversation_id.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.database import engine, async_session


async def migrate():
    """添加 conversation_id 字段"""
    
    print("🔍 检查数据库连接...")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        return False
    
    print("\n📝 开始迁移 files 表...")
    
    async with async_session() as session:
        try:
            # 直接添加字段（SQLite 会忽略已存在的字段）
            print("📌 添加 conversation_id 字段...")
            await session.execute(text("""
                ALTER TABLE files 
                ADD COLUMN conversation_id VARCHAR(64)
            """))
            await session.commit()
            print("✅ 字段添加成功（如已存在则忽略）")
            
            print("\n✅ 迁移完成！")
            return True
            
        except Exception as e:
            await session.rollback()
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️  conversation_id 字段已存在，跳过迁移")
                return True
            print(f"❌ 迁移失败：{e}")
            return False


if __name__ == "__main__":
    success = asyncio.run(migrate())
    sys.exit(0 if success else 1)
