from app.utils import prompt_loader
from app.utils.prompt_loader import PromptLoader


def _patch_root(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(prompt_loader, "PROMPTS_ROOT", root)
    return root


def test_load_returns_none_for_parent_traversal(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")

    assert PromptLoader.load("../secret.md") is None


def test_load_returns_none_for_absolute_path(monkeypatch, tmp_path):
    _patch_root(monkeypatch, tmp_path)
    target = tmp_path / "secret.md"
    target.write_text("secret", encoding="utf-8")

    assert PromptLoader.load(str(target)) is None


def test_load_reads_file_inside_root(monkeypatch, tmp_path):
    root = _patch_root(monkeypatch, tmp_path)
    (root / "nested").mkdir()
    (root / "nested" / "prompt.md").write_text("hello", encoding="utf-8")

    assert PromptLoader.load("nested/prompt.md") == "hello"


def test_format_returns_none_for_missing_variable(monkeypatch, tmp_path):
    root = _patch_root(monkeypatch, tmp_path)
    (root / "tpl.md").write_text("Hello {name}", encoding="utf-8")

    assert PromptLoader.format("tpl.md") is None


def test_format_returns_none_for_bad_braces(monkeypatch, tmp_path):
    root = _patch_root(monkeypatch, tmp_path)
    (root / "tpl.md").write_text("Hello {name", encoding="utf-8")

    assert PromptLoader.format("tpl.md", name="world") is None


def test_format_replaces_variables(monkeypatch, tmp_path):
    root = _patch_root(monkeypatch, tmp_path)
    (root / "tpl.md").write_text("Hello {name}", encoding="utf-8")

    assert PromptLoader.format("tpl.md", name="world") == "Hello world"
