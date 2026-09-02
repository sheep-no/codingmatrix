from app.services import custom_skill_manager as module


def test_user_skills_are_isolated_and_same_names_use_separate_files(tmp_path, monkeypatch):
    skills_dir = tmp_path / "custom_skills"
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "METADATA_FILE", skills_dir / "_metadata.json")

    manager = module.CustomSkillManager()
    assert manager.upload_skill("review", "tool", "user one", owner_user_id="1")[0]
    assert manager.upload_skill("review", "tool", "user two", owner_user_id="2")[0]

    assert [skill["name"] for skill in manager.list_skills(owner_user_id="1")] == ["review"]
    assert manager.get_skill("review", owner_user_id="1")["content"] == "user one"
    assert manager.get_skill("review", owner_user_id="2")["content"] == "user two"
    assert (skills_dir / "tool" / "1" / "review.md").exists()
    assert (skills_dir / "tool" / "2" / "review.md").exists()
    assert manager.get_skill("review", owner_user_id="3") is None


def test_legacy_skills_migrate_once(tmp_path, monkeypatch):
    skills_dir = tmp_path / "custom_skills"
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "METADATA_FILE", skills_dir / "_metadata.json")

    manager = module.CustomSkillManager()
    assert manager.upload_skill("legacy", "tool", "legacy content", author="api_user")[0]
    assert manager.migrate_legacy_skills("7") == 1
    assert manager.migrate_legacy_skills("8") == 0
    assert manager.get_skill("legacy", owner_user_id="7")["content"] == "legacy content"
