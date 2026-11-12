"""Branch coverage for app/services/custom_skill_manager.py."""

import json

import pytest

from app.services import custom_skill_manager as module


@pytest.fixture
def manager(tmp_path, monkeypatch):
    skills_dir = tmp_path / "custom_skills"
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "METADATA_FILE", skills_dir / "_metadata.json")
    monkeypatch.setattr(module, "_notify_registry", lambda *args, **kwargs: None)
    return module.CustomSkillManager()


# ---------------------------------------------------------------------------
# registry notification
# ---------------------------------------------------------------------------


def test_notify_registry_delete(monkeypatch) -> None:
    from app.services import skill_registry

    calls = []

    class Registry:
        def unregister(self, name):
            calls.append(("unregister", name))
            return True

        def reload_custom_skills(self):
            calls.append(("reload",))

    monkeypatch.setattr(skill_registry, "get_registry", lambda: Registry())

    module._notify_registry("demo", "delete")

    assert calls == [("unregister", "demo")]


def test_notify_registry_create_and_update(monkeypatch) -> None:
    from app.services import skill_registry

    calls = []

    class Registry:
        def unregister(self, name):
            calls.append(("unregister", name))

        def reload_custom_skills(self):
            calls.append(("reload",))

    monkeypatch.setattr(skill_registry, "get_registry", lambda: Registry())

    module._notify_registry("demo", "create")
    module._notify_registry("demo", "update")

    assert calls == [("reload",), ("reload",)]


def test_notify_registry_ignores_unknown_action(monkeypatch) -> None:
    from app.services import skill_registry

    calls = []

    class Registry:
        def unregister(self, name):
            calls.append("unregister")

        def reload_custom_skills(self):
            calls.append("reload")

    monkeypatch.setattr(skill_registry, "get_registry", lambda: Registry())

    module._notify_registry("demo", "noop")

    assert calls == []


def test_notify_registry_swallows_errors(monkeypatch) -> None:
    from app.services import skill_registry

    warnings = []

    def boom():
        raise RuntimeError("registry down")

    monkeypatch.setattr(skill_registry, "get_registry", boom)
    import logging

    monkeypatch.setattr(
        logging.Logger,
        "warning",
        lambda self, *args, **kwargs: warnings.append(args),
    )

    module._notify_registry("demo", "create")

    assert warnings


# ---------------------------------------------------------------------------
# metadata handling
# ---------------------------------------------------------------------------


def test_load_metadata_without_file(tmp_path, monkeypatch) -> None:
    skills_dir = tmp_path / "custom"
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "METADATA_FILE", skills_dir / "_metadata.json")

    manager = module.CustomSkillManager()

    assert manager._metadata == {"skills": []}


def test_load_metadata_with_invalid_json(tmp_path, monkeypatch) -> None:
    skills_dir = tmp_path / "custom"
    skills_dir.mkdir()
    metadata = skills_dir / "_metadata.json"
    metadata.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "METADATA_FILE", metadata)

    manager = module.CustomSkillManager()

    assert manager._metadata == {"skills": []}


def test_load_metadata_with_existing_content(manager, tmp_path) -> None:
    manager._metadata["skills"].append({"name": "a", "category": "tool"})
    manager._save_metadata()

    reloaded = module.CustomSkillManager()

    assert reloaded._metadata["skills"][0]["name"] == "a"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("a", True),
        ("skill_1", True),
        ("A-b", True),
        ("1skill", False),
        ("_skill", False),
        ("a" * 65, False),
        ("bad name", False),
        ("", False),
    ],
)
def test_validate_name(manager, name, valid) -> None:
    assert manager._validate_name(name) is valid


def test_validate_content_empty(manager) -> None:
    assert manager._validate_content("") == (False, "内容不能为空")
    assert manager._validate_content("   ") == (False, "内容不能为空")


def test_validate_content_too_large(manager) -> None:
    valid, message = manager._validate_content("x" * (module.MAX_FILE_SIZE + 1))

    assert valid is False
    assert "KB" in message


def test_validate_content_ok(manager) -> None:
    assert manager._validate_content("body") == (True, "")


# ---------------------------------------------------------------------------
# upload_skill
# ---------------------------------------------------------------------------


def test_upload_rejects_invalid_name(manager) -> None:
    success, message, info = manager.upload_skill("1bad", "tool", "body")

    assert success is False
    assert "名称无效" in message
    assert info is None


def test_upload_rejects_invalid_category(manager) -> None:
    success, message, info = manager.upload_skill("demo", "invalid", "body")

    assert success is False
    assert "无效分类" in message
    assert info is None


def test_upload_rejects_empty_content(manager) -> None:
    success, message, info = manager.upload_skill("demo", "tool", "")

    assert success is False
    assert message == "内容不能为空"


def test_upload_rejects_duplicate(manager) -> None:
    assert manager.upload_skill("demo", "tool", "body")[0]

    success, message, info = manager.upload_skill("demo", "tool", "other")

    assert success is False
    assert "已存在" in message


def test_upload_duplicate_is_scoped_to_owner(manager) -> None:
    assert manager.upload_skill("demo", "tool", "one", owner_user_id="1")[0]
    assert manager.upload_skill("demo", "tool", "two", owner_user_id="2")[0]


def test_upload_rejects_when_author_limit_reached(manager, monkeypatch) -> None:
    monkeypatch.setattr(module, "MAX_SKILLS_PER_USER", 1)
    manager.upload_skill("first", "tool", "body", author="alice")

    success, message, info = manager.upload_skill("second", "tool", "body", author="alice")

    assert success is False
    assert "最大 skill 数量" in message
    assert info is None


def test_upload_rejects_when_owner_limit_reached(manager, monkeypatch) -> None:
    monkeypatch.setattr(module, "MAX_SKILLS_PER_USER", 1)
    manager.upload_skill("first", "tool", "body", owner_user_id="1")

    success, message, _ = manager.upload_skill("second", "tool", "body", owner_user_id="1")

    assert success is False
    assert "最大 skill 数量" in message


def test_upload_success_with_owner(manager) -> None:
    success, message, info = manager.upload_skill(
        "demo", "tool", "body", description="d", owner_user_id=7
    )

    assert success is True
    assert message == "Skill 创建成功"
    assert info["owner_user_id"] == "7"
    assert info["version"] == 1
    assert info["created_at"].endswith("Z")
    assert manager.get_skill("demo", owner_user_id="7")["content"] == "body"


def test_upload_success_without_owner(manager) -> None:
    _, _, info = manager.upload_skill("demo", "tool", "body", author="alice")

    assert "owner_user_id" not in info
    assert info["author"] == "alice"


# ---------------------------------------------------------------------------
# update_skill
# ---------------------------------------------------------------------------


def test_update_missing_skill(manager) -> None:
    assert manager.update_skill("missing", "body") == (
        False,
        "Skill 'missing' 不存在",
        None,
    )


def test_update_rejects_invalid_content(manager) -> None:
    manager.upload_skill("demo", "tool", "body")

    success, message, info = manager.update_skill("demo", "   ")

    assert success is False
    assert message == "内容不能为空"
    assert info is None


def test_update_skill_content_and_description(manager) -> None:
    manager.upload_skill("demo", "tool", "body", description="old")

    success, message, info = manager.update_skill("demo", "new", description="new desc")

    assert success is True
    assert message == "Skill 更新成功"
    assert info["version"] == 2
    assert info["description"] == "new desc"
    assert manager.get_skill("demo")["content"] == "new"


def test_update_skill_keeps_description_when_none(manager) -> None:
    manager.upload_skill("demo", "tool", "body", description="old")

    _, _, info = manager.update_skill("demo", "new")

    assert info["description"] == "old"


def test_update_owned_skill(manager) -> None:
    manager.upload_skill("demo", "tool", "body", owner_user_id="1")

    assert manager.update_skill("demo", "new", owner_user_id="1")[0] is True
    assert manager.update_skill("demo", "new", owner_user_id="2")[0] is False


# ---------------------------------------------------------------------------
# delete_skill
# ---------------------------------------------------------------------------


def test_delete_missing_skill(manager) -> None:
    assert manager.delete_skill("missing") == (False, "Skill 'missing' 不存在")


def test_delete_removes_file_and_metadata(manager) -> None:
    manager.upload_skill("demo", "tool", "body")
    path = module.CUSTOM_SKILLS_DIR / "tool" / "demo.md"

    success, message = manager.delete_skill("demo")

    assert success is True
    assert message == "Skill 删除成功"
    assert not path.exists()
    assert manager.list_skills() == []


def test_delete_tolerates_missing_file(manager) -> None:
    manager.upload_skill("demo", "tool", "body")
    (module.CUSTOM_SKILLS_DIR / "tool" / "demo.md").unlink()

    assert manager.delete_skill("demo")[0] is True


def test_delete_owned_skill_is_scoped(manager) -> None:
    manager.upload_skill("demo", "tool", "body", owner_user_id="1")

    assert manager.delete_skill("demo", owner_user_id="2")[0] is False
    assert manager.delete_skill("demo", owner_user_id="1")[0] is True


# ---------------------------------------------------------------------------
# get / list
# ---------------------------------------------------------------------------


def test_get_missing_skill_returns_none(manager) -> None:
    assert manager.get_skill("missing") is None


def test_get_skill_missing_file_returns_empty_content(manager) -> None:
    manager.upload_skill("demo", "tool", "body")
    (module.CUSTOM_SKILLS_DIR / "tool" / "demo.md").unlink()

    assert manager.get_skill("demo")["content"] == ""


def test_list_skills_filters(manager) -> None:
    manager.upload_skill("a", "tool", "body", author="alice", owner_user_id="1")
    manager.upload_skill("b", "workflow", "body", author="bob", owner_user_id="2")

    assert {s["name"] for s in manager.list_skills()} == {"a", "b"}
    assert {s["name"] for s in manager.list_skills(owner_user_id="1")} == {"a"}
    assert {s["name"] for s in manager.list_skills(category="workflow")} == {"b"}
    assert {s["name"] for s in manager.list_skills(author="alice")} == {"a"}


def test_get_all_skills_includes_content(manager) -> None:
    manager.upload_skill("demo", "tool", "body")

    skills = manager.get_all_skills()

    assert skills[0]["content"] == "body"


def test_get_all_skills_missing_file_returns_empty_content(manager) -> None:
    manager.upload_skill("demo", "tool", "body")
    (module.CUSTOM_SKILLS_DIR / "tool" / "demo.md").unlink()

    assert manager.get_all_skills()[0]["content"] == ""


def test_get_skills_by_category(manager) -> None:
    manager.upload_skill("demo", "tool", "body")
    manager._metadata["skills"].append({"name": "x", "category": "unknown"})

    grouped = manager.get_skills_by_category()

    assert [s["name"] for s in grouped["tool"]] == ["demo"]
    assert "unknown" not in grouped


# ---------------------------------------------------------------------------
# migration / singleton
# ---------------------------------------------------------------------------


def test_migrate_skips_owned_and_non_api_user(manager, monkeypatch) -> None:
    calls = []
    manager._metadata["skills"] = [
        {"name": "a", "author": "api_user", "owner_user_id": "9"},
        {"name": "b", "author": "someone"},
    ]
    from app.services import skill_registry

    monkeypatch.setattr(
        skill_registry,
        "get_registry",
        lambda: type("R", (), {"reload_custom_skills": lambda self: calls.append(1)})(),
    )

    assert manager.migrate_legacy_skills("1") == 0
    assert calls == []


def test_migrate_legacy_skills_reloads_registry(manager, monkeypatch) -> None:
    calls = []
    manager._metadata["skills"] = [
        {"name": "a", "author": "api_user"},
    ]
    from app.services import skill_registry

    monkeypatch.setattr(
        skill_registry,
        "get_registry",
        lambda: type("R", (), {"reload_custom_skills": lambda self: calls.append(1)})(),
    )

    assert manager.migrate_legacy_skills("5") == 1
    assert calls == [1]


def test_get_skill_manager_singleton(monkeypatch) -> None:
    created = []

    class Fake(module.CustomSkillManager):
        def __init__(self):
            created.append(self)
            self._metadata = {"skills": []}

    monkeypatch.setattr(module, "CustomSkillManager", Fake)
    monkeypatch.setattr(module, "_skill_manager", None)

    first = module.get_skill_manager()
    second = module.get_skill_manager()

    assert first is second
    assert len(created) == 1
