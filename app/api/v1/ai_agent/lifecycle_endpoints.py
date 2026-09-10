from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ProjectSession
from app.services.state_migration_service import (
    archive_project,
    LocalProjectStorageAdapter,
    permanently_delete_project,
    restore_project,
    set_project_pinned,
)
from app.api.v1.ai_agent.project_config import PROJECTS_BASE_DIR
from app.utils.security import verify_token


router = APIRouter(prefix="/projects", tags=["AI Agent Projects"])


async def _owned_project(db: AsyncSession, session_id: str, token: dict) -> ProjectSession:
    user_id = token.get("sub")
    if not isinstance(user_id, str) or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    project = await db.scalar(
        select(ProjectSession).where(
            ProjectSession.session_id == session_id,
            ProjectSession.user_id == int(user_id),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.post("/{session_id}/archive")
async def archive_project_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, session_id, token)
    try:
        project = await archive_project(db, session_id)
        await db.commit()
    except ValueError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"session_id": project.session_id, "lifecycle_status": project.lifecycle_status}


@router.delete("/{session_id}")
async def permanently_delete_project_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, session_id, token)
    try:
        result = await permanently_delete_project(
            db, project, LocalProjectStorageAdapter(PROJECTS_BASE_DIR)
        )
        await db.commit()
    except (ValueError, PermissionError, OSError) as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return result


@router.post("/{session_id}/restore")
async def restore_project_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, session_id, token)
    try:
        project = await restore_project(db, session_id)
        await db.commit()
    except ValueError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"session_id": project.session_id, "lifecycle_status": project.lifecycle_status}


@router.post("/{session_id}/pin")
async def pin_project_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, session_id, token)
    project = await set_project_pinned(db, session_id, True)
    await db.commit()
    return {"session_id": project.session_id, "pinned": project.pinned}


@router.delete("/{session_id}/pin")
async def unpin_project_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, session_id, token)
    project = await set_project_pinned(db, session_id, False)
    await db.commit()
    return {"session_id": project.session_id, "pinned": project.pinned}
