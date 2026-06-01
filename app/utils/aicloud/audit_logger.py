"""
审计日志

实现 aicloud 的审计日志功能：
- 记录操作
- 记录文件读取/写入
- 记录网络请求
- 查询审计日志
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.aicloud import AicloudAuditLog


async def log_operation(
    db: AsyncSession,
    user_id: int,
    operation: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
    url: Optional[str] = None
) -> AicloudAuditLog:
    """
    记录操作

    Args:
        db: 数据库会话
        user_id: 用户 ID
        operation: 操作类型
        status: 操作状态
        details: 详情
        file_path: 文件路径
        url: URL

    Returns:
        创建的审计日志
    """
    log = AicloudAuditLog(
        user_id=user_id,
        operation=operation,
        file_path=file_path,
        url=url,
        status=status,
        details=str(details) if details else None
    )

    db.add(log)
    await db.commit()
    await db.refresh(log)

    return log


async def log_file_read(
    db: AsyncSession,
    user_id: int,
    file_path: str,
    success: bool,
    error: Optional[str] = None
) -> AicloudAuditLog:
    """
    记录文件读取操作

    Args:
        db: 数据库会话
        user_id: 用户 ID
        file_path: 文件路径
        success: 是否成功
        error: 错误信息

    Returns:
        创建的审计日志
    """
    details = {"action": "read"}
    if error:
        details["error"] = error

    return await log_operation(
        db=db,
        user_id=user_id,
        operation="file_read",
        status="success" if success else "failed",
        file_path=file_path,
        details=details
    )


async def log_file_write(
    db: AsyncSession,
    user_id: int,
    file_path: str,
    success: bool,
    bytes_written: Optional[int] = None,
    error: Optional[str] = None
) -> AicloudAuditLog:
    """
    记录文件写入操作

    Args:
        db: 数据库会话
        user_id: 用户 ID
        file_path: 文件路径
        success: 是否成功
        bytes_written: 写入字节数
        error: 错误信息

    Returns:
        创建的审计日志
    """
    details = {"action": "write"}
    if bytes_written is not None:
        details["bytes_written"] = bytes_written
    if error:
        details["error"] = error

    return await log_operation(
        db=db,
        user_id=user_id,
        operation="file_write",
        status="success" if success else "failed",
        file_path=file_path,
        details=details
    )


async def log_network_request(
    db: AsyncSession,
    user_id: int,
    url: str,
    method: str,
    status_code: Optional[int] = None,
    error: Optional[str] = None
) -> AicloudAuditLog:
    """
    记录网络请求

    Args:
        db: 数据库会话
        user_id: 用户 ID
        url: 请求 URL
        method: HTTP 方法
        status_code: 响应状态码
        error: 错误信息

    Returns:
        创建的审计日志
    """
    details = {"method": method}
    if status_code is not None:
        details["status_code"] = status_code
    if error:
        details["error"] = error

    return await log_operation(
        db=db,
        user_id=user_id,
        operation="network_request",
        status="success" if status_code and 200 <= status_code < 400 else "failed",
        url=url,
        details=details
    )


async def query_audit_logs(
    db: AsyncSession,
    user_id: Optional[int] = None,
    operation: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
) -> List[AicloudAuditLog]:
    """
    查询审计日志

    Args:
        db: 数据库会话
        user_id: 用户 ID
        operation: 操作类型
        start_date: 开始日期
        end_date: 结束日期
        limit: 返回数量限制

    Returns:
        审计日志列表
    """
    conditions = []

    if user_id is not None:
        conditions.append(AicloudAuditLog.user_id == user_id)

    if operation:
        conditions.append(AicloudAuditLog.operation == operation)

    if start_date:
        conditions.append(AicloudAuditLog.created_at >= start_date)

    if end_date:
        conditions.append(AicloudAuditLog.created_at <= end_date)

    query = select(AicloudAuditLog)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(AicloudAuditLog.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_recent_operations(
    db: AsyncSession,
    user_id: int,
    days: int = 10
) -> List[AicloudAuditLog]:
    """
    获取用户最近的操作记录

    Args:
        db: 数据库会话
        user_id: 用户 ID
        days: 天数

    Returns:
        审计日志列表
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    return await query_audit_logs(
        db=db,
        user_id=user_id,
        start_date=start_date,
        limit=100
    )


async def cleanup_old_audit_logs(db: AsyncSession, days: int = 90) -> int:
    """
    清理过期的审计日志

    Args:
        db: 数据库会话
        days: 保留天数（默认 90 天）

    Returns:
        删除的记录数
    """
    from sqlalchemy import delete, and_
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    stmt = delete(AicloudAuditLog).where(
        and_(
            AicloudAuditLog.created_at < cutoff_date,
            AicloudAuditLog.status == "success"  # 只清理成功的操作日志
        )
    )
    
    result = await db.execute(stmt)
    await db.commit()
    
    return result.rowcount
