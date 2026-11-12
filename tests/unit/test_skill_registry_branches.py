"""Branch coverage for app/services/skill_registry.py."""

import json

import pytest

from app.services import skill_registry as module


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    custom_dir = tmp_path / "custom"
    metadata = custom_dir / "_metadata.json"
    monkeypatch.setattr(module, "WORKSPACE_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", custom_dir)
    monkeypatch.setattr(module, "METADATA_FILE", metadata)
    return skills_dir, custom_dir, metadata


@pytest.fixture
def registry(isolated_registry):
    return module.SkillRegistry()


def test_initialize_is_idempotent(registry, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(registry, "_load_workspace_skills", lambda: calls.append("workspace"))
    monkeypatch.setattr(registry, "_load_custom_skills", lambda: calls.append("custom"))

    registry.initialize()
    registry.initialize()

    assert calls == ["workspace", "custom"]
    assert registry._initialized is True


def test_register_and_unregister(registry) -> None:
    skill = registry.register("demo", "tool", description="desc", content="body", author="me")

    assert skill.name == "demo"
    assert skill.created_at.endswith("Z")
    assert registry.unregister("demo") is True
    assert registry.unregister("demo") is False


def test_get_missing_skill_returns_none(registry) -> None:
    assert registry.get("missing") is None


def test_get_caches_loader_result(registry) -> None:
    calls = []

    def loader():
        calls.append(1)
        return {"value": 1}

    registry.register("cached", "tool", loader=loader)

    assert registry.get("cached") == {"value": 1}
    assert registry.get("cached") == {"value": 1}
    assert calls == [1]
    assert registry.get("cached", use_cache=False) == {"value": 1}
    assert calls == [1, 1]


def test_get_loader_failure_returns_none(registry, monkeypatch) -> None:
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    def loader():
        raise RuntimeError("boom")

    registry.register("broken", "tool", loader=loader)

    assert registry.get("broken") is None
    assert errors


def test_get_without_loader_returns_content(registry) -> None:
    registry.register("plain", "tool", content="raw")

    assert registry.get("plain") == "raw"


def test_get_info(registry) -> None:
    skill = registry.register("demo", "tool")

    assert registry.get_info("demo") is skill
    assert registry.get_info("missing") is None


def test_list_skills_filters(registry) -> None:
    registry.register("a", "tool", author="alice")
    registry.register("b", "workflow", author="bob")
    registry.register("c", "tool", author="bob")

    assert {s.name for s in registry.list_skills()} == {"a", "b", "c"}
    assert {s.name for s in registry.list_skills(category="tool")} == {"a", "c"}
    assert {s.name for s in registry.list_skills(author="bob")} == {"b", "c"}
    assert {
        s.name for s in registry.list_skills(category="tool", author="bob")
    } == {"c"}


def test_get_by_category(registry) -> None:
    registry.register("a", "tool")
    registry.register("b", "workflow")

    assert [s.name for s in registry.get_by_category("tool")] == ["a"]


def test_invalidate_cache_and_reload(registry) -> None:
    calls = []

    def loader():
        calls.append(1)
        return "value"

    registry.register("demo", "tool", loader=loader)
    registry.get("demo")

    assert registry.invalidate_cache("demo") is True
    assert registry.invalidate_cache("missing") is False
    assert registry.get("demo") == "value"
    assert calls == [1, 1]
    assert registry.reload_skill("demo") is True
    assert registry.reload_skill("missing") is False


def test_invalidate_all_cache(registry) -> None:
    registry.register("a", "tool", loader=lambda: "a")
    registry.register("b", "tool", loader=lambda: "b")
    registry.get("a")
    registry.get("b")

    registry.invalidate_all_cache()

    assert all(not skill._cache_valid for skill in registry._skills.values())
    assert all(skill._cached_data is None for skill in registry._skills.values())


def test_load_custom_skills_without_directory(registry, isolated_registry) -> None:
    _, custom_dir, _ = isolated_registry
    registry._load_custom_skills()

    assert registry._skills == {}
    assert not custom_dir.exists()


def test_load_custom_skills_without_metadata(registry, isolated_registry) -> None:
    _, custom_dir, _ = isolated_registry
    custom_dir.mkdir()

    registry._load_custom_skills()

    assert registry._skills == {}


def test_load_custom_skills_uses_user_namespaced_name(
    registry, isolated_registry
) -> None:
    _, custom_dir, metadata = isolated_registry
    custom_dir.mkdir()
    skill_file = custom_dir / "demo.md"
    skill_file.write_text("custom body", encoding="utf-8")
    metadata.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "demo",
                        "owner_user_id": "u1",
                        "category": "tool",
                        "file": "demo.md",
                        "description": "d",
                        "author": "alice",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    registry._load_custom_skills()

    info = registry.get_info("user:u1:demo")
    assert info is not None
    assert info.author == "alice"
    assert info.content == "custom body"
    assert registry.get("user:u1:demo") == "custom body"


def test_load_custom_skills_without_owner_uses_plain_name(
    registry, isolated_registry
) -> None:
    _, custom_dir, metadata = isolated_registry
    custom_dir.mkdir()
    (custom_dir / "demo.md").write_text("body", encoding="utf-8")
    metadata.write_text(
        json.dumps({"skills": [{"name": "demo", "file": "demo.md"}]}),
        encoding="utf-8",
    )

    registry._load_custom_skills()

    info = registry.get_info("demo")
    assert info is not None
    assert info.category == "other"
    assert info.author == "unknown"


def test_load_custom_skills_skips_missing_file(registry, isolated_registry) -> None:
    _, custom_dir, metadata = isolated_registry
    custom_dir.mkdir()
    metadata.write_text(
        json.dumps({"skills": [{"name": "missing", "file": "none.md"}]}),
        encoding="utf-8",
    )

    registry._load_custom_skills()

    assert registry._skills == {}


def test_load_custom_skills_invalid_json_logs_error(
    registry, isolated_registry, monkeypatch
) -> None:
    _, custom_dir, metadata = isolated_registry
    custom_dir.mkdir()
    metadata.write_text("{not json", encoding="utf-8")
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    registry._load_custom_skills()

    assert registry._skills == {}
    assert errors


def test_load_workspace_skills_registers_manifests(
    registry, isolated_registry
) -> None:
    skills_dir, _, _ = isolated_registry
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Demo\n\nDemo skill description.", encoding="utf-8")

    registry._load_workspace_skills()

    info = registry.get_info("workspace:demo")
    assert info is not None
    assert info.author == "workspace"
    assert info.category == "workspace"


def test_reload_custom_skills_removes_only_custom_entries(
    registry, isolated_registry
) -> None:
    skills_dir, custom_dir, metadata = isolated_registry
    skill_dir = skills_dir / "ws"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# WS\n\nworkspace", encoding="utf-8")
    registry._load_workspace_skills()
    registry.register("system", "tool", author="system")
    registry.register("custom", "tool", author="alice")
    custom_dir.mkdir()
    metadata.write_text(json.dumps({"skills": []}), encoding="utf-8")

    registry.reload_custom_skills()

    assert registry.get_info("workspace:ws") is not None
    assert registry.get_info("system") is not None
    assert registry.get_info("custom") is None


def test_discover_skills_skips_unknown_manifests(monkeypatch, registry) -> None:
    class Manifest:
        name = "ghost"

    class Catalog:
        @classmethod
        def from_directory(cls, path):
            return cls()

        def discover(self, requirement, limit=5):
            return [Manifest()]

    monkeypatch.setattr(module, "SkillCatalog", Catalog)

    assert registry.discover_skills("anything") == []


def test_discover_skills_logs_candidate_count(monkeypatch, registry) -> None:
    registry.register("workspace:demo", "workspace", author="workspace")
    logs = []

    class Manifest:
        name = "demo"

    class Catalog:
        @classmethod
        def from_directory(cls, path):
            return cls()

        def discover(self, requirement, limit=5):
            return [Manifest()]

    monkeypatch.setattr(module, "SkillCatalog", Catalog)
    monkeypatch.setattr(
        module.logger, "info", lambda *args, **kwargs: logs.append(args)
    )

    selected = registry.discover_skills("demo")

    assert [skill.name for skill in selected] == ["workspace:demo"]
    assert logs


def test_get_registry_caches_singleton(monkeypatch, isolated_registry) -> None:
    created = []

    class Registry(module.SkillRegistry):
        def __init__(self):
            super().__init__()
            created.append(self)

        def initialize(self):
            self._initialized = True

    monkeypatch.setattr(module, "SkillRegistry", Registry)
    monkeypatch.setattr(module, "_registry", None)

    first = module.get_registry()
    second = module.get_registry()

    assert first is second
    assert len(created) == 1


def test_convenience_functions(monkeypatch, registry) -> None:
    monkeypatch.setattr(module, "_registry", registry)
    skill = module.register_skill("demo", "tool", content="body")

    assert skill.name == "demo"
    assert module.get_skill("demo") == "body"
    assert [s.name for s in module.list_skills("tool")] == ["demo"]
