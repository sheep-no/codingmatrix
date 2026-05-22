from fastapi import APIRouter

from .generate_endpoints import router as generate_router
from .orchestrate_endpoints import router as orchestrate_router
from .association_endpoints import router as association_router
from .knowledge_endpoints import router as knowledge_router
from .performance_endpoints import router as performance_router

router = APIRouter(prefix="/agent", tags=["AI Agent"])

router.include_router(generate_router)
router.include_router(orchestrate_router)
router.include_router(association_router)
router.include_router(knowledge_router)
router.include_router(performance_router)