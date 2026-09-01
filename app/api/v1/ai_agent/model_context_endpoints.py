from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ai_agent.helpers import verify_session_ownership
from app.api.v1.ai_agent.schemas import AgentModelContextResponse, AgentModelContextUpdate
from app.db.database import get_db
from app.services.agent_state_adapter import ensure_project_session
from app.services.model_context_service import (
    build_runtime_model_context,
    get_model_context_snapshot,
    save_model_context,
)
from app.services.state_migration_service import resolve_compatibility_mapping
from app.services.unified_state_service import StateConflictError
from app.utils.security import verify_token


router = APIRouter()


@router.get(
    "/sessions/{session_id}/model-context",
    response_model=AgentModelContextResponse,
)
async def read_agent_model_context(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(token["sub"])
    mapping = await resolve_compatibility_mapping(
        db, user_id, "agent", "project_session", session_id
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="Agent session not found")

    snapshot = await get_model_context_snapshot(db, user_id, mapping.unified_id)
    return AgentModelContextResponse(
        found=snapshot is not None,
        revision=snapshot.revision if snapshot else 0,
        context=snapshot.context if snapshot else build_runtime_model_context(),
    )


@router.put(
    "/sessions/{session_id}/model-context",
    response_model=AgentModelContextResponse,
)
async def update_agent_model_context(
    session_id: str,
    payload: AgentModelContextUpdate,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(token["sub"])
    await verify_session_ownership(db, session_id, str(user_id))
    session = await ensure_project_session(db, user_id, session_id)
    update = payload.model_dump(exclude_unset=True)
    expected_revision = update.pop("expected_revision", None)
    try:
        snapshot = await save_model_context(
            db,
            user_id,
            session.id,
            update,
            expected_revision=expected_revision,
        )
    except StateConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await db.commit()
    return AgentModelContextResponse(
        found=True,
        revision=snapshot.revision,
        context=snapshot.context,
    )
