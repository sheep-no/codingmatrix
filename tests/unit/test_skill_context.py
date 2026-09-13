from pathlib import Path

import app.api.v1.ai_agent.orchestrate_endpoints as endpoints


class _Manager:
    def list_skills(self, owner_user_id=None):
        return [{"name": "whisper-ellipsis", "description": "whisper ellipsis greeting"}]

    def get_skill(self, name, owner_user_id=None):
        return {"name": name, "content": "SKILL_MARKER_ELLIPSIS"}


class _Registry:
    def discover_skills(self, requirement):
        return []


def test_user_skill_injects_when_two_terms_overlap(monkeypatch):
    monkeypatch.setattr("app.services.custom_skill_manager.get_skill_manager", lambda: _Manager())
    monkeypatch.setattr("app.services.skill_registry.get_registry", lambda: _Registry())
    monkeypatch.setattr("app.api.v1.agent_host.get_latest_session_skills", lambda user_id: {})

    context = endpoints._skill_context_for_user(
        "1", "add whisper ellipsis to the greeting function",
    )
    assert "[user:whisper-ellipsis]" in context
    assert "SKILL_MARKER_ELLIPSIS" in context


def test_user_skill_skips_when_only_one_term_overlaps(monkeypatch):
    monkeypatch.setattr("app.services.custom_skill_manager.get_skill_manager", lambda: _Manager())
    monkeypatch.setattr("app.services.skill_registry.get_registry", lambda: _Registry())
    monkeypatch.setattr("app.api.v1.agent_host.get_latest_session_skills", lambda user_id: {})

    context = endpoints._skill_context_for_user("1", "add whisper function to greet")
    assert context == ""


def test_stream_respects_enable_skills_flag():
    source = Path("app/api/v1/ai_agent/orchestrate_endpoints.py").read_text(encoding="utf-8")
    assert source.count("if request.enable_skills") >= 2
