"""Generate and cache deterministic previews for built-in PPT templates."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.utils.pptx.templates.manager import TemplateManager

SAMPLE_VERSION = "v1"
SAMPLE_ROOT = Path("./pptx_output/template_samples")


def _paths(template_id: str) -> dict[str, Path]:
    base = SAMPLE_ROOT / f"{template_id}-{SAMPLE_VERSION}"
    return {"pptx": base.with_suffix(".pptx"), "pdf": base.with_suffix(".pdf"), "png_dir": base.parent / base.name}


def _fixture(template_id: str) -> dict[str, Any]:
    return {
        "title": f"{template_id} template sample",
        "template": template_id,
        "slides": [
            {"id": "sample-cover", "title": "封面样张", "content": ["固定演示内容"]},
            {"id": "sample-body", "title": "正文样张", "content": ["结构化正文", "可验证层级"]},
            {"id": "sample-chart", "title": "图表样张", "content": ["季度趋势", "Q1 24", "Q2 36", "Q3 48"]},
        ],
    }


async def ensure_template_sample(template_id: str) -> dict[str, Any]:
    manager = TemplateManager()
    template_id = manager.select_template(template_id)
    paths = _paths(template_id)
    if paths["pptx"].is_file() and all((paths["png_dir"] / f"slide-{n}.png").is_file() for n in range(1, 4)):
        return _metadata(template_id, paths)
    paths["pptx"].parent.mkdir(parents=True, exist_ok=True)
    from app.api.v1.aiGeneratorPptx import PPTGenerationRequest, generate_pptx_file_enhanced, _convert_pptx_to_pdf
    await generate_pptx_file_enhanced(paths["pptx"], _fixture(template_id), PPTGenerationRequest(topic="template sample", slide_count=3, template=template_id, options={"auto_images": False, "enable_animation": False}))
    await _convert_pptx_to_pdf(paths["pptx"], paths["pdf"])
    paths["png_dir"].mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_render_pngs, paths["pdf"], paths["png_dir"])
    return _metadata(template_id, paths)


def _render_pngs(pdf: Path, output: Path) -> None:
    import subprocess
    for page in range(1, 4):
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-scale-to", "1280", "-png", str(pdf), str(output / f"slide-{page}")], check=True)


def _metadata(template_id: str, paths: dict[str, Path]) -> dict[str, Any]:
    return {"version": SAMPLE_VERSION, "status": "available", "slides": [f"/pptx/templates/{template_id}/preview/{n}" for n in range(1, 4)]}
