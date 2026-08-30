"""SQL-backed services for unified sessions, tasks, events and artifacts."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.unified_state import Artifact, Checkpoint, Message, Session, TaskEvent


TERMINAL_TASK_STATUSES = {"success", "failed", "cancelled"}


class UnifiedStateError(Exception):
    """Base error for unified state operations."""


class StateNotFoundError(UnifiedStateError):
    pass


class StateOwnershipError(UnifiedStateError):
    pass


class StateConflictError(UnifiedStateError):
    pass


async def create_session(
    db: AsyncSession,
    user_id: int,
    module: str,
    external_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Session:
    session = Session(
        id=str(uuid.uuid4()),
        user_id=int(user_id),
        module=module,
        external_id=external_id,
        title=title,
    )
    db.add(session)
    await db.flush()
    return session


async def get_owned_session(db: AsyncSession, session_id: str, user_id: int) -> Session:
    session = await db.scalar(select(Session).where(Session.id == session_id))
    if not session:
        raise StateNotFoundError("会话不存在")
    if session.user_id != int(user_id):
        raise StateOwnershipError("无权访问此会话")
    return session


async def append_message(
    db: AsyncSession,
    session_id: str,
    user_id: int,
    role: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Message:
    session = await get_owned_session(db, session_id, user_id)
    sequence = await db.scalar(
        select(func.coalesce(func.max(Message.sequence), 0) + 1).where(Message.session_id == session_id)
    )
    message = Message(
        session_id=session.id,
        user_id=int(user_id),
        sequence=int(sequence or 1),
        role=role,
        content=content,
        metadata_json=metadata or {},
    )
    db.add(message)
    session.updated_at = datetime.utcnow()
    await db.flush()
    return message


async def list_messages(
    db: AsyncSession,
    session_id: str,
    user_id: int,
    limit: int = 100,
    before_sequence: Optional[int] = None,
) -> list[Message]:
    await get_owned_session(db, session_id, user_id)
    query = select(Message).where(Message.session_id == session_id)
    if before_sequence is not None:
        query = query.where(Message.sequence < before_sequence)
    query = query.order_by(Message.sequence.desc()).limit(max(1, min(limit, 500)))
    messages = list((await db.scalars(query)).all())
    messages.reverse()
    return messages


async def create_task(
    db: AsyncSession,
    user_id: int,
    task_type: str,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    input_file_id: Optional[int] = None,
) -> Task:
    if session_id:
        await get_owned_session(db, session_id, user_id)
    if idempotency_key:
        existing = await db.scalar(
            select(Task).where(Task.user_id == int(user_id), Task.idempotency_key == idempotency_key)
        )
        if existing:
            return existing
    task = Task(
        task_id=task_id or str(uuid.uuid4()),
        session_id=session_id,
        idempotency_key=idempotency_key,
        task_type=task_type,
        user_id=int(user_id),
        params={**(params or {}), "idempotency_key": idempotency_key} if idempotency_key else (params or {}),
        input_file_id=input_file_id,
        status="pending",
    )
    db.add(task)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise StateConflictError("任务创建冲突") from error
    return task


async def get_owned_task(db: AsyncSession, task_id: str, user_id: int) -> Task:
    task = await db.scalar(select(Task).where(Task.task_id == task_id))
    if not task:
        raise StateNotFoundError("任务不存在")
    if task.user_id != int(user_id):
        raise StateOwnershipError("无权访问此任务")
    return task


async def transition_task(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    status: str,
    progress: Optional[int] = None,
    stage: Optional[str] = None,
    result: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
    allow_recovery: bool = False,
    expected_revision: Optional[int] = None,
) -> Task:
    task = await get_owned_task(db, task_id, user_id)
    if expected_revision is not None and task.revision != expected_revision:
        raise StateConflictError("任务版本已变化")
    if task.status in TERMINAL_TASK_STATUSES and status != task.status and not allow_recovery:
        raise StateConflictError("任务已进入终态")
    task.status = status
    task.revision += 1
    task.stage = stage or task.stage
    if progress is not None:
        task.progress = min(100, max(0, int(progress)))
    if stage:
        task.progress_message = stage
    if result is not None:
        task.result = result
        task.result_json = result
    if error_message is not None:
        task.error_message = error_message or None
        task.error_json = {"message": error_message} if error_message else {}
    if status == "running" and task.started_at is None:
        task.started_at = datetime.utcnow()
    if status in TERMINAL_TASK_STATUSES:
        task.completed_at = task.completed_at or datetime.utcnow()
        task.finished_at = task.finished_at or task.completed_at
    await db.flush()
    return task


async def append_task_event(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    status: Optional[str] = None,
    progress: Optional[int] = None,
) -> TaskEvent:
    await get_owned_task(db, task_id, user_id)
    sequence = await db.scalar(
        select(func.coalesce(func.max(TaskEvent.sequence), 0) + 1).where(TaskEvent.task_id == task_id)
    )
    event = TaskEvent(
        task_id=task_id,
        sequence=int(sequence or 1),
        event_type=event_type,
        status=status,
        progress=progress,
        payload_json=payload or {},
    )
    db.add(event)
    await db.flush()
    return event


async def replay_task_events(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    after_sequence: int = 0,
    limit: int = 500,
) -> list[TaskEvent]:
    await get_owned_task(db, task_id, user_id)
    query = (
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.sequence > max(0, after_sequence))
        .order_by(TaskEvent.sequence.asc())
        .limit(max(1, min(limit, 1000)))
    )
    return list((await db.scalars(query)).all())


async def heartbeat_task(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    worker_id: str,
    lease_until: datetime,
) -> Task:
    task = await get_owned_task(db, task_id, user_id)
    if task.status in TERMINAL_TASK_STATUSES:
        raise StateConflictError("终态任务无法续租")
    task.worker_id = worker_id
    task.lease_until = lease_until
    await db.flush()
    return task


async def compare_task_snapshot(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """返回旧状态与 SQL 权威状态的差异，供迁移期巡检使用。"""
    task = await get_owned_task(db, task_id, user_id)
    fields = ("status", "progress", "error_message")
    differences = {
        field: {"sql": getattr(task, field), "legacy": snapshot.get(field)}
        for field in fields
        if getattr(task, field) != snapshot.get(field)
    }
    return {"task_id": task_id, "consistent": not differences, "differences": differences}


async def save_checkpoint(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    revision: int,
    step: str,
    state: dict[str, Any],
    idempotency_key: str,
    input_ref: Optional[str] = None,
    artifact_ref: Optional[str] = None,
) -> Checkpoint:
    await get_owned_task(db, task_id, user_id)
    existing = await db.scalar(
        select(Checkpoint).where(Checkpoint.task_id == task_id, Checkpoint.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    checkpoint = Checkpoint(
        task_id=task_id,
        revision=revision,
        step=step,
        state_json=state,
        input_ref=input_ref,
        artifact_ref=artifact_ref,
        idempotency_key=idempotency_key,
    )
    db.add(checkpoint)
    await db.flush()
    return checkpoint


async def create_artifact(
    db: AsyncSession,
    user_id: int,
    artifact_type: str,
    storage_uri: str,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    version: int = 1,
    content_hash: Optional[str] = None,
    parent_artifact_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Artifact:
    if task_id:
        await get_owned_task(db, task_id, user_id)
    if session_id:
        await get_owned_session(db, session_id, user_id)
    artifact = Artifact(
        id=str(uuid.uuid4()),
        user_id=int(user_id),
        task_id=task_id,
        session_id=session_id,
        artifact_type=artifact_type,
        version=version,
        storage_uri=storage_uri,
        content_hash=content_hash,
        parent_artifact_id=parent_artifact_id,
        metadata_json=metadata or {},
    )
    db.add(artifact)
    await db.flush()
    return artifact
