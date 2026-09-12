from app.agent import dynamic_model_router as dmr
from app.services.model_config_manager import ModelConfigManager


def test_refresh_runtime_config_reloads_role_assignment(monkeypatch):
    monkeypatch.setattr(
        dmr,
        "load_agent_model_config",
        lambda: {
            "roles": {
                "architect": "glm-4.7-flash",
                "frontend": "glm-4-flash-250414",
                "backend": "glm-4-flash-250414",
                "reviewer": "glm-z1-flash",
                "fallback": "glm-4.7-flash",
            }
        },
    )
    dmr._roles_cache = {
        "architect": "Qwen/Qwen3-8B",
        "frontend": "deepseek-ai/DeepSeek-R1",
        "backend": "Qwen/Qwen3.5-4B",
        "reviewer": "THUDM/glm-z1-9b",
        "fallback": "Qwen/Qwen3-8B",
    }
    try:
        ModelConfigManager._refresh_runtime_config()
        assignment = dmr.DynamicModelRouter().get_assignment()
        assert assignment.architect_model == dmr.resolve_model_key("glm-4.7-flash")
        assert assignment.frontend_model == dmr.resolve_model_key("glm-4-flash-250414")
        assert assignment.backend_model == dmr.resolve_model_key("glm-4-flash-250414")
        assert assignment.reviewer_model == dmr.resolve_model_key("glm-z1-flash")
    finally:
        dmr._roles_cache = None
        dmr.reload_roles_config()
