from app.services import skill_registry as module


def test_workspace_skill_files_are_registered_and_discoverable(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fastapi-crud"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# FastAPI CRUD\n\nFastAPI SQLite SQLAlchemy CRUD validation rules.",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WORKSPACE_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", tmp_path / "custom")
    monkeypatch.setattr(module, "METADATA_FILE", tmp_path / "custom" / "_metadata.json")

    registry = module.SkillRegistry()
    registry.initialize()

    skill = registry.get_info("workspace:fastapi-crud")
    assert skill is not None
    assert skill.author == "workspace"
    assert registry.discover_skills("请生成 FastAPI SQLite CRUD 项目") == [skill]


def test_reloading_custom_skills_preserves_workspace_skills(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    (skills_dir / "review").mkdir(parents=True)
    (skills_dir / "review" / "SKILL.md").write_text("# Review\n代码审查", encoding="utf-8")
    monkeypatch.setattr(module, "WORKSPACE_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "CUSTOM_SKILLS_DIR", tmp_path / "custom")
    monkeypatch.setattr(module, "METADATA_FILE", tmp_path / "custom" / "_metadata.json")

    registry = module.SkillRegistry()
    registry.initialize()
    registry.reload_custom_skills()

    assert registry.get_info("workspace:review") is not None
