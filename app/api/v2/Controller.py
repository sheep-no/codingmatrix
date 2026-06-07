import asyncio
import logging
import time
import json

import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.utils.security import verify_token_ws
from app.utils.permissions import is_admin
from app.utils.system_monitor import get_system_stats
from app.db.log_server import LogService, LogFilter

logger = logging.getLogger(__name__)
router = APIRouter()


# 辅助函数

def check_admin_permission(permission_level: str) -> bool:
    """
    检查是否为 admin 及以上权限
    
    Args:
        permission_level: 用户权限级别
    
    Returns:
        bool: 是否为 admin 及以上权限
    """
    return is_admin(permission_level)


async def get_db_pool_stats(engine) -> dict:
    """
    获取数据库连接池统计信息（使用官方 API）
    
    Args:
        engine: SQLAlchemy Engine
    
    Returns:
        dict: 连接池统计
    """
    try:
        pool = engine.pool
        pool_size = pool.size() if callable(pool.size) else pool.size
        
        return {
            "pool_size": pool_size,
            "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else 0,
            "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else 0,
            "overflow": pool.overflow() if hasattr(pool, 'overflow') else 0,
            "invalidated": 0  # SQLite 不支持
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.debug(f"获取连接池统计失败：{e}")
        return {"pool_size": 0, "checked_in": 0, "checked_out": 0, "overflow": 0, "invalidated": 0}


async def get_active_queries(engine) -> int:
    """
    获取活跃查询数（带异常处理）
    
    Args:
        engine: SQLAlchemy Engine
    
    Returns:
        int: 活跃查询数
    """
    try:
        async with engine.connect() as conn:
            if "sqlite" in str(engine.url):
                result = await conn.execute(text("SELECT COUNT(*) FROM sqlite_master;"))
                return result.scalar() or 0
            elif "postgresql" in str(engine.url):
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active';")
                )
                return result.scalar() or 0
            else:
                return 0
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.warning(f"查询活跃连接失败：{e}")
        return 0


# 系统状态推送接口
@router.websocket("/Controller/sys-status")
async def controller(websocket: WebSocket, token: str):
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else "unknown"

    logger.info(
        f"WebSocket连接请求 | client={client_host}:{client_port} | token_preview={token[:20] if token else 'None'}")

    await websocket.accept()
    logger.info(f"WebSocket连接已建立 | client={client_host}:{client_port}")

    # 验证 token
    is_valid, payload, close_code, reason = verify_token_ws(token)
    if not is_valid:
        await websocket.close(code=close_code, reason=reason)
        logger.warning(
            f"WebSocket连接被拒绝 | client={client_host}:{client_port} | code={close_code} | reason={reason}")
        return

    user_id = payload.get("sub")
    permission_level = payload.get("permission_level", "unknown")
    logger.info(
        f"Token 验证通过 | user_id={user_id} | permission_level={permission_level} | client={client_host}:{client_port}")

    # 权限检查：需要 admin 及以上权限

    if not check_admin_permission(permission_level):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="需要管理员权限")
        logger.warning(f"权限不足拒绝连接 | user_id={user_id} | level={permission_level}")
        return

    logger.info(f"开始推送系统状态 | user_id={user_id} | client={client_host}:{client_port}")
    message_count = 0

    try:
        while True:
            start_time = time.time()
            stats = await asyncio.to_thread(get_system_stats)

            try:
                await websocket.send_json({
                    "type": "system_stats",
                    "data": stats
                })
            except RuntimeError:
                logger.info(f"发送失败，连接已断开 | user_id={user_id} | messages_sent={message_count}")
                break

            duration_ms = (time.time() - start_time) * 1000
            logger.debug(f"消息发送成功 | user_id={user_id} | msg_id={message_count} | duration={duration_ms:.2f}ms")

            message_count += 1
            await asyncio.sleep(3)

    except WebSocketDisconnect as e:
        logger.info(
            f"客户端主动断开 | user_id={user_id} | code={e.code} | reason={e.reason} | messages_sent={message_count}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"推送异常 | user_id={user_id} | error={str(e)} | messages_sent={message_count}", exc_info=True)
    finally:
        try:
            await websocket.close(code=1000)
            logger.info(f"连接已关闭 | user_id={user_id}")
        except Exception:
            logger.debug(f"连接已在别处关闭 | user_id={user_id}")


# 增强型日志推送接口（带实时数据库监控） ====================
@router.websocket("/Controller/logs")
async def stream_logs_websocket(
        websocket: WebSocket,
        token: str = Query(..., description="JWT Token"),
        log_type: str = Query("app", description="日志类型", enum=["app", "error", "debug"]),
        enable_db_monitor: bool = Query(True, description="是否启用数据库监控")
):
    """
    WebSocket 实时日志流 + 可选数据库连接监控
    协议：
    - 服务端推送：{"type": "log", "data": "..."} 或 {"type": "db_status", "data": {...}}
    - 客户端可发送：{"action": "filter", "level": "ERROR", "keyword": "websocket"}
    - 客户端可发送：{"action": "ping"} 保持连接
    """
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"日志流连接请求 | client={client_host} | log_type={log_type} | db_monitor={enable_db_monitor}")

    await websocket.accept()

    # 验证 token
    is_valid, payload, close_code, reason = verify_token_ws(token)
    if not is_valid:
        await websocket.close(code=close_code, reason=reason)
        logger.warning(f"日志流连接被拒绝 | client={client_host}")
        return

    user_id = payload.get("sub")
    permission_level = payload.get("permission_level")

    # 权限检查：需要 admin 及以上权限

    if not check_admin_permission(permission_level):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="需要管理员权限")
        logger.warning(f"日志流权限不足 | user_id={user_id} | level={permission_level}")
        return

    logger.info(f"日志流连接已建立 | user_id={user_id} | db_monitor={enable_db_monitor}")

    # 初始化服务和过滤器
    log_service = LogService()
    log_filter = LogFilter()

    # 数据库监控任务
    db_monitor_task = None
    db_filter = {"level": None, "keyword": None}  # 数据库监控过滤器

    async def log_streamer():
        """后台任务：持续推送日志"""
        async for log_line in log_service.stream_logs_with_filter(
                log_type=log_type,
                filters=log_filter.to_dict()
        ):
            try:
                await websocket.send_json({"type": "log", "data": log_line})
            except RuntimeError:
                break
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                logger.error(f"日志流发送失败 | user_id={user_id} | error={str(e)}")
                break

    async def database_monitor():
        """后台任务：实时监控数据库连接"""
        from app.db.database import engine

        while True:
            try:
                # 获取连接池统计（使用官方 API）
                pool_stats = await get_db_pool_stats(engine)

                # 获取活跃查询数（带异常处理）
                active_queries = await get_active_queries(engine)

                # 获取当前进程内存和 CPU
                process = psutil.Process()
                db_status = {
                    "timestamp": time.time(),
                    "active_queries": active_queries,
                    "pool_stats": pool_stats,
                    "memory_mb": process.memory_info().rss / 1024 / 1024,
                    "cpu_percent": process.cpu_percent(),
                    "dialect": engine.dialect.name
                }

                # 应用数据库过滤器（与日志过滤器独立）
                if db_filter.get("keyword"):
                    if db_filter["keyword"] not in str(db_status):
                        await asyncio.sleep(5)
                        continue

                await websocket.send_json({"type": "db_status", "data": db_status})

            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                logger.error(f"数据库监控异常 | user_id={user_id} | error={str(e)}")
                await websocket.send_json({"type": "error", "data": f"DB监控错误: {str(e)}"})

            await asyncio.sleep(5)  # 每 5 秒推送一次

    # 启动后台任务
    stream_task = asyncio.create_task(log_streamer())
    if enable_db_monitor:
        db_monitor_task = asyncio.create_task(database_monitor())

    try:
        # 主循环：接收客户端命令
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                try:
                    data = json.loads(message)
                    action = data.get("action", "filter")

                    if action == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif action == "filter":
                        # 更新日志过滤器
                        log_filter.level = data.get("level")
                        log_filter.keyword = data.get("keyword")

                        # 可选：更新数据库过滤器（独立）
                        db_filter["keyword"] = data.get("db_keyword")

                        await websocket.send_json({
                            "type": "status",
                            "message": "过滤条件已更新",
                            "log_filters": log_filter.to_dict(),
                            "db_filters": db_filter
                        })

                    elif action == "clear":
                        log_filter.level = None
                        log_filter.keyword = None
                        db_filter["keyword"] = None

                        await websocket.send_json({
                            "type": "status",
                            "message": "过滤条件已清除"
                        })

                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"未知操作: {action}"
                        })

                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "无效的JSON格式"
                    })

            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect as e:
        logger.info(f"日志流客户端断开 | user_id={user_id} | code={e.code}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"日志流异常 | user_id={user_id} | error={str(e)}", exc_info=True)
    finally:
        # 清理后台任务
        if stream_task and not stream_task.done():
            stream_task.cancel()
        if db_monitor_task and not db_monitor_task.done():
            db_monitor_task.cancel()

        # 等待任务取消
        for task in [stream_task, db_monitor_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    # 预期内的取消，不处理
                    pass

        try:
            await websocket.close(code=1000)
            logger.info(f"日志流连接已关闭 | user_id={user_id}")
        except RuntimeError:
            # WebSocket 已关闭，忽略
            pass