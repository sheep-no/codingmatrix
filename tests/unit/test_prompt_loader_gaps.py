"""prompt_loader 异常路径与各快捷加载函数补测。"""

from pathlib import Path

import pytest

from app.utils import prompt_loader as module
from app.utils.prompt_loader import PromptLoader


def _root(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(module, "PROMPTS_ROOT", root)
    return root


def test_load_returns_none_when_resolve_raises(monkeypatch):
    class Broken:
        def resolve(self):
            raise OSError("boom")

    monkeypatch.setattr(module, "PROMPTS_ROOT", Broken())
    assert PromptLoader.load("x.md") is None


def test_load_returns_none_when_file_missing(monkeypatch, tmp_path):
    _root(monkeypatch, tmp_path)
    assert PromptLoader.load("nope.md") is None


def test_load_returns_none_when_read_fails(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    target = root / "tpl.md"
    target.write_text("x", encoding="utf-8")

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        raise OSError("disk error")

    monkeypatch.setattr(Path, "read_text", boom)
    try:
        assert PromptLoader.load("tpl.md") is None
    finally:
        monkeypatch.setattr(Path, "read_text", real_read_text)


def test_format_returns_none_when_load_fails(monkeypatch, tmp_path):
    _root(monkeypatch, tmp_path)
    assert PromptLoader.format("missing.md") is None


def test_project_generation_prompt(monkeypatch):
    calls = []

    def fake_format(path, **kwargs):
        calls.append((path, kwargs))
        return "ok"

    monkeypatch.setattr(PromptLoader, "format", classmethod(
        lambda cls, path, **kwargs: fake_format(path, **kwargs)
    ))
    result = module.load_project_generation_prompt("out", "tools")
    assert result == "ok"
    assert calls[0][1] == {"output_dir": "out", "tools_description": "tools"}


def test_resume_prompt_lists_and_truncates(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        PromptLoader, "format", classmethod(lambda cls, path, **kw: seen.update(kw) or "ok")
    )
    module.load_resume_prompt("req", [f"f{i}" for i in range(35)])
    assert seen["current_files_list"].count("\n") == 29
    assert seen["current_files_list"].startswith("- f0")
    assert seen["requirement"] == "req"


def test_resume_prompt_empty_files(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        PromptLoader, "format", classmethod(lambda cls, path, **kw: seen.update(kw) or "ok")
    )
    module.load_resume_prompt("req", [])
    assert seen["current_files_list"] == "(暂无文件)"


def test_directory_status_prompt(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        PromptLoader, "format", classmethod(lambda cls, path, **kw: seen.update(kw) or "ok")
    )
    module.load_directory_status_prompt([f"f{i}" for i in range(25)])
    assert seen["existing_files_list"].count("\n") == 19
    module.load_directory_status_prompt([])
    assert seen["existing_files_list"] == ""


@pytest.mark.parametrize(
    "func,path",
    [
        (module.load_orchestrator_prompt, "orchestrator/enhanced_orchestrator_prompt.md"),
        (module.load_architect_prompt, "orchestrator/enhanced_architect_prompt.md"),
        (module.load_frontend_engineer_prompt, "orchestrator/enhanced_frontend_engineer_prompt.md"),
        (module.load_backend_engineer_prompt, "orchestrator/enhanced_backend_engineer_prompt.md"),
        (module.load_code_reviewer_prompt, "orchestrator/enhanced_code_reviewer_prompt.md"),
        (module.load_complexity_analysis_prompt, "orchestrator/complexity_analysis_prompt.md"),
        (module.load_openapi_generator_prompt, "specs/openapi_generator_prompt.md"),
        (module.load_types_generator_prompt, "specs/types_generator_prompt.md"),
        (module.load_db_schema_generator_prompt, "specs/db_schema_generator_prompt.md"),
        (module.load_config_generator_prompt, "specs/config_generator_prompt.md"),
        (module.load_code_patcher_prompt, "validation/code_patcher_prompt.md"),
        (module.load_code_refinement_prompt, "validation/code_refinement_prompt.md"),
        (module.load_cross_validator_prompt, "validation/cross_validator_prompt.md"),
        (module.load_cognitive_skills_prompt, "skills/cognitive_skills_prompt.md"),
    ],
)
def test_shortcut_loaders_delegate(func, path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        PromptLoader, "load", classmethod(lambda cls, p: seen.append(p) or "content")
    )
    assert func() == "content"
    assert seen == [path]
