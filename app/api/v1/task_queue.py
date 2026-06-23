"""
任务队列 API (Celery 版本)

提供基于 Celery + Redis 的分布式任务队列功能。
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.utils.security import verify_token
from app.schema.task_schema import (
    TaskCreateRequest,
    TaskResponse,
    TaskListResponse,
    TaskPriorityEnum
)
from app.models.task import Task
from app.celery_app import celery_app
from app.services.websocket_manager import ws_manager
from app.tasks.base import parse_priority, parse_timeout

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["任务管理"])


@router.post("", response_model=TaskResponse, summary="创建任务")
async def create_task(
    body: TaskCreateRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    创建异步任务（Celery 驱动）

    支持的任务类型:
    - project_generate: 项目生成
    - code_generate: 代码生成
    - ppt_generate: PPT 生成
    - file_process: 文件处理
    - modify_with_test: 修改+自动测试（P1 新增）
    """
    user_id = int(token.get("sub"))
    task_type = body.task_type.value

    logger.info(f"创建任务请求 | user_id={user_id} | type={task_type}")

    priority_value = parse_priority(body.priority.value)
    timeout_value = parse_timeout(body.timeout)

    task_map = {
        "project_generate": "app.tasks.project_tasks.generate_project",
        "code_generate": "app.tasks.code_tasks.generate_code",
        "modify_with_test": "app.tasks.code_tasks.modify_with_test",  # P1 新增
    }

    celery_task_name = task_map.get(task_type)
    if not celery_task_name:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的任务类型：{task_type}"
        )

    task_record = Task(
            task_id=f"task_{user_id}_{id(body)}",
            task_type=task_type,
            status="pending",
            priority=priority_value,
            timeout=timeout_value,
            params=body.params,
            user_id=user_id,
            input_file_id=body.input_file_id,
            parent_task_id=body.parent_task_id,
            max_retries=3
        )
    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    result = celery_app.send_task(
        celery_task_name,
        task_id=task_record.task_id,
        requirement=body.params.get("requirement", ""),
        prompt=body.params.get("prompt", ""),
        language=body.params.get("language", "python"),
        user_id=user_id,
        priority=priority_value,
        time_limit=timeout_value
    )

    task_record.celery_task_id = result.id
    await db.commit()

    logger.info(f"任务创建成功 | task_id={task_record.task_id} | celery_id={result.id}")

    return TaskResponse(
        task_id=task_record.task_id,
        celery_task_id=result.id,
        task_type=task_record.task_type,
        status="pending",
        priority=priority_value,
        progress=0,
        progress_message="等待中...",
        result=None,
        error_message=None,
        retry_count=0,
        max_retries=3,
        parent_task_id=task_record.parent_task_id,
        created_at=task_record.created_at.isoformat() if task_record.created_at else "",
        started_at=None,
        completed_at=None
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="查询任务状态")
async def get_task(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """查询任务状态和进度"""
    user_id = int(token.get("sub"))

    result = await db.execute(
        select(Task).where(Task.task_id == task_id)
    )
    task_record = result.scalar_one_or_none()

    if not task_record:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task_record.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    celery_state = None
    celery_info = None
    if task_record.celery_task_id:
        celery_result = celery_app.AsyncResult(task_record.celery_task_id)
        celery_state = celery_result.state
        celery_info = celery_result.info

    status = celery_state.lower() if celery_state else task_record.status
    progress = 0
    progress_message = task_record.progress_message or ""

    if celery_info and isinstance(celery_info, dict):
        progress = celery_info.get("progress", progress)
        progress_message = celery_info.get("message", progress_message)

    return TaskResponse(
        task_id=task_record.task_id,
        celery_task_id=task_record.celery_task_id,
        task_type=task_record.task_type,
        status=status,
        priority=task_record.priority,
        progress=progress,
        progress_message=progress_message,
        result=task_record.result,
        error_message=task_record.error_message,
        retry_count=task_record.retry_count,
        max_retries=task_record.max_retries,
        parent_task_id=task_record.parent_task_id,
        created_at=task_record.created_at.isoformat() if task_record.created_at else "",
        started_at=task_record.started_at.isoformat() if task_record.started_at else None,
        completed_at=task_record.completed_at.isoformat() if task_record.completed_at else None
    )


@router.get("", response_model=TaskListResponse, summary="列出任务")
async def list_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    task_type: Optional[str] = Query(None, description="类型筛选"),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """列出用户的任务"""
    user_id = int(token.get("sub"))

    query = select(Task).where(Task.user_id == user_id)

    if status:
        query = query.where(Task.status == status)
    if task_type:
        query = query.where(Task.task_type == task_type)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Task.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskListResponse(
        total=total,
        tasks=[
            TaskResponse(
                task_id=t.task_id,
                celery_task_id=t.celery_task_id,
                task_type=t.task_type,
                status=t.status,
                priority=t.priority,
                progress=t.progress,
                progress_message=t.progress_message,
                result=t.result,
                error_message=t.error_message,
                retry_count=t.retry_count,
                max_retries=t.max_retries,
                parent_task_id=t.parent_task_id,
                created_at=t.created_at.isoformat() if t.created_at else "",
                started_at=t.started_at.isoformat() if t.started_at else None,
                completed_at=t.completed_at.isoformat() if t.completed_at else None
            )
            for t in tasks
        ],
        page=page,
        page_size=page_size
    )


@router.delete("/{task_id}", status_code=204, summary="取消任务")
async def cancel_task(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """取消运行中的任务"""
    user_id = int(token.get("sub"))

    result = await db.execute(
        select(Task).where(Task.task_id == task_id)
    )
    task_record = result.scalar_one_or_none()

    if not task_record:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task_record.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权取消此任务")

    if task_record.status not in ["pending", "running", "retrying"]:
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {task_record.status}，无法取消"
        )

    if task_record.celery_task_id:
        celery_app.control.revoke(
            task_record.celery_task_id,
            terminate=True,
            signal='SIGTERM'
        )

    task_record.status = "cancelled"
    await db.commit()

    logger.info(f"任务取消成功 | task_id={task_id}")


@router.post("/{task_id}/retry", response_model=TaskResponse, summary="重试任务")
async def retry_task(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """重试失败的任务"""
    user_id = int(token.get("sub"))

    result = await db.execute(
        select(Task).where(Task.task_id == task_id)
    )
    task_record = result.scalar_one_or_none()

    if not task_record:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task_record.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权重试此任务")

    if task_record.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {task_record.status}，无需重试"
        )

    task_record.status = "pending"
    task_record.retry_count = 0
    task_record.error_message = None
    task_record.progress = 0

    task_map = {
        "project_generate": "app.tasks.project_tasks.generate_project",
        "code_generate": "app.tasks.code_tasks.generate_code",
    }

    celery_task_name = task_map.get(task_record.task_type)
    if celery_task_name and task_record.celery_task_id:
        celery_app.send_task(
            celery_task_name,
            task_id=task_record.task_id,
            requirement=task_record.params.get("requirement", ""),
            prompt=task_record.params.get("prompt", ""),
            language=task_record.params.get("language", "python"),
            user_id=user_id,
            priority=task_record.priority,
            time_limit=task_record.timeout
        )

    await db.commit()

    logger.info(f"任务重试成功 | task_id={task_id}")

    return TaskResponse(
        task_id=task_record.task_id,
        celery_task_id=task_record.celery_task_id,
        task_type=task_record.task_type,
        status="pending",
        priority=task_record.priority,
        progress=0,
        progress_message="等待重试...",
        result=None,
        error_message=None,
        retry_count=0,
        max_retries=task_record.max_retries,
        parent_task_id=task_record.parent_task_id,
        created_at=task_record.created_at.isoformat() if task_record.created_at else "",
        started_at=None,
        completed_at=None
    )


@router.websocket("/ws/{user_id}")
async def task_websocket(websocket: WebSocket, user_id: int):
    """
    WebSocket 连接用于实时任务状态推送

    连接后会自动接收该用户所有任务的状态更新。
    """
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)
        logger.info(f"WebSocket disconnected: user_id={user_id}")