"""ppt_template_samples 缓存、生成与渲染补测。"""

import subprocess
from pathlib import Path

import pytest

from app.services import ppt_template_samples as module


class _Manager:
    def __init__(self, selected=None):
        self.selected = selected

    def select_template(self, template_id):
        return self.selected or template_id


@pytest.fixture
def sample_root(tmp_path, monkeypatch):
    root = tmp_path / "samples"
    monkeypatch.setattr(module, "SAMPLE_ROOT", root)
    monkeypatch.setattr(module, "TemplateManager", _Manager)
    return root


def _create_cached(root, template_id="classic"):
    paths = module._paths(template_id)
    paths["pptx"].parent.mkdir(parents=True, exist_ok=True)
    paths["pptx"].write_bytes(b"pptx")
    paths["png_dir"].mkdir(parents=True, exist_ok=True)
    for n in range(1, 4):
        (paths["png_dir"] / f"slide-{n}.png").write_bytes(b"png")
    return paths


async def test_returns_cached_metadata_without_regeneration(sample_root, monkeypatch):
    _create_cached(sample_root, "classic")

    async def boom(*_args, **_kwargs):
        raise AssertionError("should not regenerate")

    monkeypatch.setattr(module, "_render_pngs", boom)
    result = await module.ensure_template_sample("classic")

    assert result["status"] == "available"
    assert result["slides"][0] == "/pptx/templates/classic/preview/1"


async def test_regenerates_missing_sample(sample_root, monkeypatch):
    calls = {}

    class _Request:
        def __init__(self, **kwargs):
            calls["request"] = kwargs

    async def fake_generate(path, fixture, request):
        calls["generate"] = (path, fixture)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"generated")

    async def fake_convert(pptx, pdf):
        calls["convert"] = (pptx, pdf)
        Path(pdf).write_bytes(b"pdf")

    def fake_render(pdf, output):
        calls["render"] = (pdf, output)

    async def inline_to_thread(func, *args):
        func(*args)

    monkeypatch.setattr(
        "app.api.v1.aiGeneratorPptx.PPTGenerationRequest", _Request
    )
    monkeypatch.setattr(
        "app.api.v1.aiGeneratorPptx.generate_pptx_file_enhanced", fake_generate
    )
    monkeypatch.setattr(
        "app.api.v1.aiGeneratorPptx._convert_pptx_to_pdf", fake_convert
    )
    monkeypatch.setattr(module, "_render_pngs", fake_render)
    monkeypatch.setattr(module.asyncio, "to_thread", inline_to_thread)

    result = await module.ensure_template_sample("classic")

    assert calls["generate"][1]["template"] == "classic"
    assert calls["request"]["template"] == "classic"
    assert calls["convert"][0].name == "classic-v1.pptx"
    assert calls["render"][0].name == "classic-v1.pdf"
    assert result["version"] == "v1"


async def test_uses_selected_template_id(sample_root, monkeypatch):
    monkeypatch.setattr(module, "TemplateManager", lambda: _Manager("normalized"))
    _create_cached(sample_root, "normalized")

    result = await module.ensure_template_sample("alias")

    assert result["slides"][0].endswith("/normalized/preview/1")


async def test_regenerates_when_one_png_missing(sample_root, monkeypatch):
    paths = _create_cached(sample_root, "classic")
    (paths["png_dir"] / "slide-2.png").unlink()
    regenerated = []

    async def fake_generate(path, fixture, request):
        regenerated.append(path)

    async def fake_convert(pptx, pdf):
        Path(pdf).write_bytes(b"pdf")

    async def inline_to_thread(func, *args):
        return None

    monkeypatch.setattr("app.api.v1.aiGeneratorPptx.generate_pptx_file_enhanced", fake_generate)
    monkeypatch.setattr("app.api.v1.aiGeneratorPptx._convert_pptx_to_pdf", fake_convert)
    monkeypatch.setattr(module.asyncio, "to_thread", inline_to_thread)

    await module.ensure_template_sample("classic")

    assert regenerated == [paths["pptx"]]


def test_render_pngs_invokes_pdftoppm_per_page(monkeypatch, tmp_path):
    commands = []

    def fake_run(command, check):
        commands.append((command, check))

    monkeypatch.setattr(subprocess, "run", fake_run)

    module._render_pngs(tmp_path / "deck.pdf", tmp_path)

    assert len(commands) == 3
    assert all(check is True for _, check in commands)
    assert commands[0][0][:4] == ["pdftoppm", "-f", "1", "-l"]
    assert "-singlefile" in commands[0][0]
    assert commands[2][0][2] == "3"
