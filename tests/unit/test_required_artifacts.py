"""Requirement-named artifacts must be enforced, not only warned about."""

from app.agent.orchestrator_generation.coverage_checker import (
    check_required_artifacts,
    extract_required_artifacts,
)


def test_extracts_root_scoped_artifacts_from_requirement():
    required = extract_required_artifacts(
        "请生成根级 index.html 与 README.md，页面包含登录表单。"
    )

    assert required == [
        {"path": "index.html", "root": True},
        {"path": "README.md", "root": True},
    ]


def test_ignores_paths_mentioned_without_creation_intent():
    assert extract_required_artifacts("参考 README.md 了解背景，不必生成文件") == []


def test_ignores_urls_and_upgrades_duplicate_paths_to_root():
    required = extract_required_artifacts(
        "创建 docs/guide.md 与 http.html。根级生成 README.md，并生成 README.md。"
    )

    assert required == [
        {"path": "docs/guide.md", "root": False},
        {"path": "README.md", "root": True},
    ]


def test_root_scoped_later_sentence_upgrades_earlier_artifact():
    required = extract_required_artifacts(
        "生成 README.md 与 README.md 与 index.html。"
        "根级生成 README.md 与 app.py。"
    )

    assert required == [
        {"path": "README.md", "root": True},
        {"path": "index.html", "root": False},
        {"path": "app.py", "root": True},
    ]


def test_root_file_missing_even_if_nested_copy_exists():
    result = check_required_artifacts(
        "生成根级 index.html",
        ["src/index.html", "app/main.py"],
    )

    assert result["checked"] is True
    assert result["missing"] == ["index.html"]
    assert result["passed"] is False


def test_nested_artifact_satisfies_unqualified_requirement():
    result = check_required_artifacts(
        "创建 README.md 说明项目",
        ["docs/README.md"],
    )

    assert result["missing"] == []
    assert result["passed"] is True


def test_empty_requirement_skips_check():
    result = check_required_artifacts("", ["main.py"])

    assert result == {
        "checked": False,
        "required": [],
        "missing": [],
        "passed": True,
    }


def test_artifact_written_to_disk_satisfies_requirement(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\n")

    result = check_required_artifacts(
        "包含 requirements.txt",
        ["src/main.py"],
        output_dir=tmp_path,
    )

    assert result["missing"] == []
    assert result["passed"] is True


def test_root_artifact_must_be_at_output_root_on_disk(tmp_path):
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "index.html").write_text("<html></html>")

    result = check_required_artifacts(
        "生成根级 index.html",
        ["src/main.py"],
        output_dir=tmp_path,
    )

    assert result["missing"] == ["index.html"]
    assert result["passed"] is False
