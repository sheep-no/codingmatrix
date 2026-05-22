import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.security import verify_token
from app.db.database import get_db
from app.services.agent_memory_service import AgentMemoryService

from .schemas import KnowledgeRequest, KnowledgeResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/knowledge", response_model=KnowledgeResponse)
async def add_knowledge(
    request: KnowledgeRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    knowledge = await service.add_knowledge(
        user_id=user_id,
        content=request.content,
        knowledge_key=request.knowledge_key,
        category=request.category,
        importance=request.importance,
        tags=request.tags
    )

    return KnowledgeResponse(
        id=knowledge.id,
        content=knowledge.content,
        knowledge_key=knowledge.knowledge_key,
        category=knowledge.category,
        importance=knowledge.importance,
        usage_count=knowledge.usage_count,
        created_at=knowledge.created_at.isoformat() if knowledge.created_at else None,
        tags=knowledge.tags if hasattr(knowledge, 'tags') else None
    )


@router.get("/knowledge", response_model=list[KnowledgeResponse])
async def list_knowledge(
    category: str = Query(None, description="分类筛选"),
    limit: int = Query(50, ge=1, le=200),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    entries = await service.get_user_knowledge(user_id, category=category, limit=limit)

    return [
        KnowledgeResponse(
            id=e.id,
            content=e.content,
            knowledge_key=e.knowledge_key,
            category=e.category,
            importance=e.importance,
            usage_count=e.usage_count,
            created_at=e.created_at.isoformat() if e.created_at else None,
            tags=getattr(e, 'tags', None)
        )
        for e in entries
    ]


@router.get("/knowledge/search", response_model=list[KnowledgeResponse])
async def search_knowledge(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    category: str = Query(None, description="分类筛选"),
    limit: int = Query(10, ge=1, le=50),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    entries = await service.search_knowledge(user_id, q, category=category, limit=limit)

    return [
        KnowledgeResponse(
            id=e.id,
            content=e.content,
            knowledge_key=e.knowledge_key,
            category=e.category,
            importance=e.importance,
            usage_count=e.usage_count,
            created_at=e.created_at.isoformat() if e.created_at else None,
            tags=getattr(e, 'tags', None)
        )
        for e in entries
    ]