from dataclasses import dataclass

import pytest

from app.services.girlai_companion_model import CompanionModelService


@dataclass
class Assignment:
    reviewer_model: str = "reviewer"
    frontend_model: str = "fast"
    fallback_model: str = "fallback"


@pytest.mark.asyncio
async def test_select_models_maps_companion_roles(monkeypatch):
    class Router:
        def get_assignment(self):
            return Assignment()

    async def get_router():
        return Router()

    monkeypatch.setattr("app.services.girlai_companion_model.get_dynamic_router", get_router)

    selected = await CompanionModelService().select_models()

    assert selected["conversation"] == "reviewer"
    assert selected["classification"] == "fast"
    assert selected["memory"] == "fast"
    assert selected["fallback"] == "fallback"
