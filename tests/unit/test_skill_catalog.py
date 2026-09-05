from app.agent.skill_catalog import SkillCatalog


def test_catalog_reads_manifest_metadata_and_ranks_matching_skill(tmp_path):
    skill_dir = tmp_path / "crud-persistence"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: crud-persistence\n"
        "version: 2\n"
        "kind: capability\n"
        "languages: [python, typescript]\n"
        "frameworks: [fastapi]\n"
        "databases: [sqlite]\n"
        "capabilities: [crud, persistence]\n"
        "stages: [generation, validation]\n"
        "priority: 90\n"
        "---\n"
        "# CRUD persistence\n\nUse a file-backed SQLite database and verify restart persistence.",
        encoding="utf-8",
    )

    catalog = SkillCatalog.from_directory(tmp_path)
    selected = catalog.discover("生成 Python FastAPI SQLite CRUD 持久化项目")

    assert len(selected) == 1
    assert selected[0].name == "crud-persistence"
    assert selected[0].version == "2"
    assert selected[0].frameworks == ("fastapi",)
    assert "version: 2" not in selected[0].content
    assert "file-backed SQLite" in selected[0].content


def test_catalog_skips_unmatched_skills(tmp_path):
    skill_dir = tmp_path / "java-spring"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Spring\nUse JPA.", encoding="utf-8")

    assert SkillCatalog.from_directory(tmp_path).discover("生成 FastAPI 项目") == ()
