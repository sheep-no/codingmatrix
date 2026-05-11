"""初始化工作流历史记录表"""
import asyncio
from app.db.database import engine
from app.db.models import Base


async def init_workflow_history_table():
    """创建 workflow_history 表（如果不存在）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("workflow_history 表已就绪")


if __name__ == "__main__":
    asyncio.run(init_workflow_history_table())
