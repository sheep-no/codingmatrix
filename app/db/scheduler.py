# app/services/scheduler.py
import logging
import os
import shutil
from datetime import datetime, timedelta
from sqlalchemy import delete, select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.db.database import async_session
from app.db.chat_archiver import ChatArchiver
from app.models.file import File
from app.models.task import Task
from app.utils.task_manager import task_manager

scheduler = AsyncIOScheduler()
logger = logging.getLogger(__name__)


async def archive_task():
    """定时归档任务：每 10 天执行一次"""
    async with async_session() as db:
        archiver = ChatArchiver(db)
        await archiver.archive_all_users()


async def cleanup_files_task():
    """
    定时清理文件任务：每 7 天执行一次
    - 清理软删除超过 7 天的文件
    - 清理上传超过 30 天且无关联任务的孤立文件
    """
    async with async_session() as db:
        deleted_count = 0
        orphaned_count = 0
        
        try:
            # 1. 清理软删除超过 7 天的文件
            all_deleted = (await db.execute(
                select(File).where(File.is_deleted == 1)
            )).scalars().all()
            
            for file in all_deleted:
                # 检查是否超过 7 天
                if file.updated_at:
                    days_since_deleted = (datetime.utcnow() - file.updated_at).days
                    if days_since_deleted > 7:
                        # 删除物理文件
                        if os.path.exists(file.file_path):
                            if os.path.isfile(file.file_path):
                                os.remove(file.file_path)
                            elif os.path.isdir(file.file_path):
                                shutil.rmtree(file.file_path)
                            logger.info(f"删除物理文件：{file.file_path}")
                        
                        # 删除数据库记录
                        await db.delete(file)
                        deleted_count += 1
            
            # 2. 清理上传超过 30 天且无关联任务的孤立文件
            orphaned_cutoff = datetime.utcnow() - timedelta(days=30)
            
            orphaned_files = (await db.execute(
                select(File)
                .where(File.created_at < orphaned_cutoff)
                .where(File.is_deleted == 0)
            )).scalars().all()
            
            for file in orphaned_files:
                # 检查是否有关联的任务
                tasks = (await db.execute(
                    select(Task).where(Task.input_file_id == file.id)
                )).scalars().all()
                
                if not tasks:
                    # 删除物理文件
                    if os.path.exists(file.file_path):
                        if os.path.isfile(file.file_path):
                            os.remove(file.file_path)
                        elif os.path.isdir(file.file_path):
                            shutil.rmtree(file.file_path)
                        logger.info(f"删除孤立文件：{file.file_path}")
                    
                    await db.delete(file)
                    orphaned_count += 1
            
            await db.commit()
            
            logger.info(
                f"文件清理完成 | 删除过期文件={deleted_count} | 删除孤立文件={orphaned_count}"
            )
            
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            await db.rollback()
            logger.error(f"文件清理任务失败：{str(e)}", exc_info=True)
            raise


async def cleanup_tasks_task():
    """
    定时清理任务队列：每 7 天执行一次
    - 清理数据库中 7 天前的已完成/失败/取消任务
    - 清理内存中的旧任务记录
    """
    async with async_session() as db:
        deleted_count = 0
        
        try:
            # 1. 清理数据库中 7 天前的任务
            cutoff = datetime.utcnow() - timedelta(days=7)
            
            old_tasks = (await db.execute(
                select(Task).where(
                    Task.created_at < cutoff,
                    Task.status.in_(["success", "failed", "cancelled"])
                )
            )).scalars().all()
            
            for task in old_tasks:
                await db.delete(task)
                deleted_count += 1
            
            await db.commit()
            
            # 2. 清理内存中的旧任务
            memory_count = await task_manager.cleanup_old_tasks(days=7)
            
            logger.info(
                f"任务清理完成 | 数据库清理={deleted_count} | 内存清理={memory_count}"
            )
            
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            await db.rollback()
            logger.error(f"任务清理任务失败：{str(e)}", exc_info=True)
            raise


async def cleanup_logs_task():
    """
    定时清理日志文件：每 7 天执行一次
    - 删除超过保留期的日志文件
    - 压缩旧日志文件节省空间
    """
    try:
        from app.utils.log_archiver import get_log_archiver
        archiver = get_log_archiver()
        stats = archiver.archive_all()
        logger.info(
            f"日志归档完成 | 轮转={len(stats['rotated'])} | 归档={len(stats['archived'])} | 清理={len(stats['cleaned'])}"
        )
    except Exception as e:
        logger.error(f"日志清理任务失败：{str(e)}", exc_info=True)


# 配置定时任务
# 1. 对话归档 - 每 10 天执行一次
scheduler.add_job(
    archive_task,
    trigger=IntervalTrigger(days=10),
    id="chat_archive",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)

# 2. 文件清理 - 每 7 天执行一次
scheduler.add_job(
    cleanup_files_task,
    trigger=IntervalTrigger(days=7),
    id="file_cleanup",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)

# 3. 任务清理 - 每 7 天执行一次
scheduler.add_job(
    cleanup_tasks_task,
    trigger=IntervalTrigger(days=7),
    id="task_cleanup",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)

# 4. 日志清理 - 每 7 天执行一次
scheduler.add_job(
    cleanup_logs_task,
    trigger=IntervalTrigger(days=7),
    id="log_cleanup",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)


def start_scheduler():
    """启动定时任务调度器"""
    scheduler.start()
    logger.info("定时任务调度器已启动")
    logger.info("  - 对话归档：每 10 天执行")
    logger.info("  - 文件清理：每 7 天执行")
    logger.info("  - 任务清理：每 7 天执行")
    logger.info("  - 日志清理：每 7 天执行")
