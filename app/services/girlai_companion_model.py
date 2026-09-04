"""Model selection metadata for GirlAI companion workloads."""

from dataclasses import asdict
from typing import Any

from app.agent.dynamic_model_router import DynamicModelRouter, get_dynamic_router


class CompanionModelService:
    """Select configured models for companion task roles."""

    async def select_models(self) -> dict[str, Any]:
        router: DynamicModelRouter = await get_dynamic_router()
        assignment = router.get_assignment()
        return {
            "conversation": assignment.reviewer_model,
            "classification": assignment.frontend_model,
            "memory": assignment.frontend_model,
            "fallback": assignment.fallback_model,
            "assignment": asdict(assignment),
        }


__all__ = ["CompanionModelService"]
