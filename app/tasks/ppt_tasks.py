"""Celery tasks for serializable PPT generation jobs."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import BaseTask

logger = logging.getLogger(__name__)


async def _generate_ppt(
    task_id: str,
    user_id: int,
    request_data: dict[str, Any],
    progress,
) -> dict[str, Any]:
    """Run the PPT pipeline through the recoverable stage orchestrator."""
    from app.api.v1.aiGeneratorPptx import (
        OutputFormat,
        PPTGenerationRequest,
        PPT_OUTPUT_DIR,
        generate_html_ppt,
        generate_markdown_ppt,
        generate_ppt_outline,
        generate_pptx_file_enhanced,
        _convert_pptx_to_pdf,
    )
    from app.services.ppt_generation_orchestrator import PPTGenerationOrchestrator
    from app.services.ppt_quality_orchestrator import run_quality_pipeline
    from app.utils.pptx.semantic_renderer import build_render_metadata

    request = PPTGenerationRequest.model_validate(request_data)
    output_dir = Path(PPT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = {
        OutputFormat.PPTX: "pptx",
        OutputFormat.HTML: "html",
        OutputFormat.MARKDOWN: "md",
        OutputFormat.PDF: "pdf",
    }.get(request.output_format, "pptx")
    filepath = output_dir / f"{task_id}.{extension}"
    state: dict[str, Any] = {"request": request, "quality_mode": (request.options or {}).get("quality_mode", "standard")}

    async def planning(context):
        await progress.update(20, "正在生成 PPT 大纲...")
        approved_outline = (request.options or {}).get("approved_outline")
        if approved_outline:
            from app.api.v1.aiGeneratorPptx import _normalize_approved_outline

            context["outline"] = _normalize_approved_outline(approved_outline)
        else:
            context["outline"] = await generate_ppt_outline(request, user_id=str(user_id))
        snapshot_path = output_dir / f"{task_id}_slides.json"
        snapshot_path.write_text(
            json.dumps(context["outline"].get("slides", []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return context

    async def render_current_outline(context):
        outline = context["outline"]
        if request.output_format == OutputFormat.PDF:
            pptx_filepath = output_dir / f"{task_id}.pptx"
            await generate_pptx_file_enhanced(pptx_filepath, outline, request, update_progress=progress.update)
            await _convert_pptx_to_pdf(pptx_filepath, filepath)
        elif request.output_format == OutputFormat.HTML:
            await progress.update(60, "正在生成 HTML 格式...")
            await generate_html_ppt(filepath, outline, request)
        elif request.output_format == OutputFormat.MARKDOWN:
            await progress.update(60, "正在生成 Markdown 格式...")
            await generate_markdown_ppt(filepath, outline, request)
        else:
            await generate_pptx_file_enhanced(filepath, outline, request, update_progress=progress.update)
        return context

    async def rendering(context):
        return await render_current_outline(context)

    async def rule_qa(context):
        quality_slides = [
            {
                **slide,
                "id": slide.get("id", f"slide-{index + 1}"),
                "elements": slide.get("elements", []),
                "render_metadata": build_render_metadata(slide, token_version="1.0"),
            }
            for index, slide in enumerate(context["outline"].get("slides", []))
        ]
        context["quality_slides"], context["quality_report"] = await run_quality_pipeline(
            quality_slides, context["quality_mode"]
        )
        return context

    async def reflow(context):
        context["outline"] = {**context["outline"], "slides": context["quality_slides"]}
        if context["quality_report"].reflow_attempts:
            await render_current_outline(context)
        return context

    handlers = {
        "planning": planning,
        "assets": lambda context: context,
        "rendering": rendering,
        "rule_qa": rule_qa,
        "reflow": reflow,
        "vision_qa": lambda context: context,
        "completed": lambda context: context,
    }
    await progress.update(5, "正在准备上下文...")
    orchestration = await PPTGenerationOrchestrator(handlers).run(state)
    if orchestration.status != "completed":
        raise RuntimeError(orchestration.error or f"PPT 编排失败：{orchestration.stage}")
    return {
        "filename": filepath.name,
        "ppt_id": task_id,
        "download_url": f"/api/v1/pptx/download/{task_id}?format={extension}",
        "preview_url": f"/api/v1/pptx/preview/{task_id}" if extension == "pptx" else None,
    }


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.ppt_tasks.generate_ppt",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def generate_ppt(self, task_id: str, user_id: int, request_data: dict[str, Any], **kwargs):
    """Generate a PPT from JSON-only arguments in a Celery worker."""
    progress = self._get_progress_callback(task_id, int(user_id))

    async def heartbeat() -> None:
        from app.db.database import async_session
        from app.services.unified_state_service import heartbeat_task

        async with async_session() as db:
            try:
                await heartbeat_task(
                    db,
                    task_id,
                    int(user_id),
                    worker_id=f"celery:{self.request.hostname or 'unknown'}",
                    lease_until=datetime.now(timezone.utc) + timedelta(seconds=90),
                )
                await db.commit()
            except Exception:
                await db.rollback()

    async def run() -> dict[str, Any]:
        original_update = progress.update
        last_progress = 20

        async def persist_progress(progress_value: int, message: str) -> None:
            from app.db.database import async_session
            from app.services.task_event_service import append_task_event
            from app.services.unified_state_service import transition_task

            async with async_session() as db:
                try:
                    await transition_task(
                        db,
                        task_id,
                        int(user_id),
                        "running",
                        progress=progress_value,
                        stage=message,
                    )
                    await append_task_event(
                        db,
                        task_id,
                        int(user_id),
                        "progress",
                        payload={"message": message},
                        status="running",
                        progress=progress_value,
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()

        async def update_with_heartbeat(*args, **kwargs):
            nonlocal last_progress
            await heartbeat()
            progress_value = int(args[0]) if args else int(kwargs.get("progress", last_progress))
            message = str(args[1]) if len(args) > 1 else str(kwargs.get("message", ""))
            last_progress = progress_value
            await persist_progress(progress_value, message)
            return await original_update(progress_value, message)

        progress.update = update_with_heartbeat
        await heartbeat()
        result = await _generate_ppt(task_id, int(user_id), request_data, progress)
        from app.db.database import async_session
        from app.services.task_event_service import append_task_event
        from app.services.unified_state_service import transition_task

        async with async_session() as db:
            try:
                await transition_task(db, task_id, int(user_id), "success", progress=100, result=result)
                await append_task_event(db, task_id, int(user_id), "completed", payload=result, status="success", progress=100)
                await db.commit()
            except Exception:
                await db.rollback()
        await heartbeat()
        return result

    try:
        return asyncio.run(run())
    except SoftTimeLimitExceeded:
        logger.error("PPT task timed out | task_id=%s", task_id)
        raise RuntimeError("PPT 任务执行超时")
    except Exception as exc:
        logger.exception("PPT task failed | task_id=%s", task_id)
        raise self.retry(exc=exc, countdown=60)


__all__ = ["generate_ppt"]
