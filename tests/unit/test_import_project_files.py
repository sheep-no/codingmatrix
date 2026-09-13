import pytest

from app.api.v1.ai_agent import helpers


def test_materialize_imported_project_writes_under_user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))

    result = helpers.materialize_imported_project(
        "1",
        [
            {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"},
            {"path": "main.py", "content": "from calc import add\nprint(add(1, 2))\n"},
            {"path": "__MACOSX/._calc.py", "content": "skip"},
            {"path": "../secret.py", "content": "nope"},
        ],
        project_name="semi_calc.zip",
    )

    assert result["project_path"] == "1/semi_calc"
    assert set(result["files"]) == {"calc.py", "main.py"}
    assert (tmp_path / "1/semi_calc/calc.py").read_text(encoding="utf-8").startswith("def add")
    assert not (tmp_path / "1/semi_calc/__MACOSX").exists()
    assert not list(tmp_path.rglob("secret.py"))


def test_materialize_imported_project_rejects_empty_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="没有可导入的文件"):
        helpers.materialize_imported_project("1", [])


def test_materialize_imported_project_disambiguates_existing_name(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    (tmp_path / "1/demo").mkdir(parents=True)

    result = helpers.materialize_imported_project(
        "1",
        [{"path": "main.py", "content": "print(1)\n"}],
        project_name="demo",
    )

    assert result["project_path"].startswith("1/demo_")
    assert (tmp_path / result["project_path"] / "main.py").is_file()
