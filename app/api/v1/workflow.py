"""
Workflow API - 临时工作流接口

API 端点：
- POST /api/v1/workflow/execute - 自然语言执行工作流（LLM 分解 -> 执行）
- POST /api/v1/workflow/{workflow_id}/execute - 直接执行已导入的工作流
- GET /api/v1/workflow/status/{workflow_id} - 获取工作流状态
- POST /api/v1/workflow/import - 导入工作流 JSON
- GET /api/v1/workflow/export/{workflow_id} - 导出工作流 JSON
- DELETE /api/v1/workflow/{workflow_id} - 删除工作流
- GET /api/v1/workflow/history - 获取工作流历史记录
"""

import asyncio
import json
import logging
import threading
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import WorkflowHistory
from app.schema.workflow import (
    WorkflowRequest,
    WorkflowStatusResponse,
    WorkflowStreamEvent,
    WorkflowErrorResponse,
    TaskGraph,
)
from app.utils.security import verify_token
from app.utils.workflow.task_decomposer import TaskDecomposer, TaskDecomposerError
from app.utils.workflow.graph_validator import GraphValidator, GraphValidationError
from app.utils.workflow.executor import WorkflowExecutor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])


_workflows = {}
_workflows_lock = threading.Lock()

_session_workflows = {}
_session_lock = threading.Lock()


@router.post("/execute")
async def execute_workflow(
    request: WorkflowRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    执行临时工作流

    1. 使用 LLM 将自然语言请求分解为任务图
    2. 验证任务图
    3. 执行工作流
    4. 返回流式结果

    支持继续生成：
    - 如果提供了 session_id，会查找之前的工作流
    - 新请求会覆盖/修改之前的工作流
    """
    user_id = token.get("sub") or token.get("user_id")
    session_id = request.session_id

    history_record = None

    async def generate_events():
        nonlocal history_record
        try:
            previous_workflow = None
            if session_id:
                with _session_lock:
                    previous_workflow = _session_workflows.get(session_id)

            yield json.dumps({
                "event": "workflow_started",
                "workflow_id": "pending",
                "session_id": session_id,
                "is_continuation": previous_workflow is not None,
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

            if previous_workflow:
                previous_request = previous_workflow.get("request", "")
                yield json.dumps({
                    "event": "continuation_context",
                    "previous_request": previous_request,
                    "previous_workflow_id": previous_workflow.get("workflow_id"),
                    "message": "继续之前的工作流",
                    "timestamp": datetime.now().isoformat(),
                }) + "\n"

                modified_request = f"""【继续工作流】请在之前的工作流基础上进行修改/扩展。

之前的需求：
{previous_request}

新的/修改的需求：
{request.natural_language_request}

请根据新的需求，重新生成任务图。如果之前的任务仍然有效，保留它们。"""
                decompose_request = modified_request
            else:
                decompose_request = request.natural_language_request

            decomposer = TaskDecomposer()
            task_graph = await decomposer.decompose(decompose_request)

            validator = GraphValidator()
            is_valid, errors = validator.validate(task_graph)

            if not is_valid:
                error_response = WorkflowErrorResponse(
                    error="invalid_task_graph",
                    message=f"任务图验证失败: {', '.join(errors)}",
                    workflow_id=task_graph.workflow_id,
                )
                yield json.dumps({
                    "event": "workflow_error",
                    "error": error_response.error,
                    "message": error_response.message,
                    "workflow_id": task_graph.workflow_id,
                    "timestamp": datetime.now().isoformat(),
                }) + "\n"
                return

            with _workflows_lock:
                _workflows[task_graph.workflow_id] = {
                    "task_graph": task_graph,
                    "request": request,
                    "user_id": user_id,
                }

            yield json.dumps({
                "event": "task_graph_generated",
                "workflow_id": task_graph.workflow_id,
                "nodes": [
                    {
                        "id": node.id,
                        "type": node.type.value,
                        "params": node.params,
                        "depends_on": node.depends_on,
                    }
                    for node in task_graph.nodes
                ],
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

            if request.export_workflow:
                yield json.dumps({
                    "event": "workflow_exported",
                    "workflow_id": task_graph.workflow_id,
                    "export_data": task_graph.model_dump() if hasattr(task_graph, 'model_dump') else {
                        "workflow_id": task_graph.workflow_id,
                        "version": task_graph.version,
                        "nodes": [
                            {
                                "id": node.id,
                                "type": node.type.value,
                                "params": node.params,
                                "depends_on": node.depends_on,
                            }
                            for node in task_graph.nodes
                        ],
                    },
                    "timestamp": datetime.now().isoformat(),
                }) + "\n"

            executor = WorkflowExecutor(
                task_graph=task_graph,
                timeout=request.timeout,
                node_timeout=min(300, request.timeout // 2),
                max_concurrent=3,
            )

            event_queue = asyncio.Queue()

            def on_node_start(node_id: str):
                event_queue.put_nowait(json.dumps({
                    "event": "node_started",
                    "node_id": node_id,
                    "timestamp": datetime.now().isoformat(),
                }) + "\n")

            def on_node_complete(node_id: str, result):
                event_data = {
                    "event": "node_completed",
                    "node_id": node_id,
                    "success": getattr(result, 'success', True),
                    "timestamp": datetime.now().isoformat(),
                }
                if getattr(result, 'data', None):
                    event_data["data"] = result.data
                if getattr(result, 'error', None):
                    event_data["error"] = result.error
                event_queue.put_nowait(json.dumps(event_data) + "\n")

            async def drain_events():
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                        yield event
                    except asyncio.TimeoutError:
                        break

            executor_task = asyncio.create_task(executor.execute(
                on_node_start=on_node_start,
                on_node_complete=on_node_complete,
            ))

            async for event in drain_events():
                yield event

            while not executor_task.done():
                async for event in drain_events():
                    yield event
                await asyncio.sleep(0.05)

            async for event in drain_events():
                yield event

            result = await executor_task

            yield json.dumps({
                "event": "workflow_completed",
                "workflow_id": task_graph.workflow_id,
                "status": result["status"],
                "summary": result["summary"],
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

            try:
                history_record = WorkflowHistory(
                    workflow_id=task_graph.workflow_id,
                    user_id=user_id,
                    request=request.natural_language_request,
                    task_graph=task_graph.model_dump() if hasattr(task_graph, 'model_dump') else {
                        "workflow_id": task_graph.workflow_id,
                        "nodes": [
                            {"id": n.id, "type": n.type.value, "params": n.params, "depends_on": n.depends_on}
                            for n in task_graph.nodes
                        ],
                    },
                    status=result["status"],
                    nodes_count=len(task_graph.nodes),
                    completed_nodes=result.get("summary", {}).get("completed_nodes", 0),
                    result_summary=json.dumps(result.get("summary", {}), ensure_ascii=False)[:1000],
                )
                db.add(history_record)
                await db.commit()
                logger.info(f"工作流历史记录已保存: {task_graph.workflow_id}")
            except Exception as e:
                logger.error(f"保存工作流历史记录失败: {e}")

            if session_id:
                with _session_lock:
                    _session_workflows[session_id] = {
                        "workflow_id": task_graph.workflow_id,
                        "request": request.natural_language_request,
                        "task_graph": task_graph.model_dump() if hasattr(task_graph, 'model_dump') else None,
                        "user_id": user_id,
                        "updated_at": datetime.now().isoformat(),
                    }

        except TaskDecomposerError as e:
            logger.error(f"任务分解失败: {e}")
            yield json.dumps({
                "event": "workflow_error",
                "error": "decomposition_failed",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }) + "\n"
        except Exception as e:
            logger.error(f"工作流执行失败: {e}", exc_info=True)
            yield json.dumps({
                "event": "workflow_error",
                "error": "execution_failed",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

    return StreamingResponse(
        generate_events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/status/{workflow_id}")
async def get_workflow_status(
    workflow_id: str,
    token: dict = Depends(verify_token),
):
    """
    获取工作流状态

    Args:
        workflow_id: 工作流 ID
    """
    with _workflows_lock:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_data = _workflows[workflow_id]
        task_graph = workflow_data["task_graph"]

        aggregator = None
        executor = None

        try:
            from app.utils.workflow.executor import WorkflowExecutor
            executor = WorkflowExecutor(task_graph=task_graph)
            aggregator = executor.get_aggregator()
        except:
            pass

        if aggregator:
            summary = aggregator.get_workflow_summary()
            status = "running" if not aggregator.is_complete() else summary.get("status", "unknown")
        else:
            status = "unknown"

        return {
            "workflow_id": workflow_id,
            "status": status,
            "task_graph": {
            "workflow_id": task_graph.workflow_id,
            "version": task_graph.version,
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type.value,
                    "params": node.params,
                    "depends_on": node.depends_on,
                }
                for node in task_graph.nodes
            ],
        },
        "summary": aggregator.get_workflow_summary() if aggregator else None,
    }


@router.post("/import")
async def import_workflow(
    task_graph: TaskGraph,
    token: dict = Depends(verify_token),
):
    """
    导入工作流 JSON

    Args:
        task_graph: 任务图
    """
    user_id = token.get("sub") or token.get("user_id")

    validator = GraphValidator()
    is_valid, errors = validator.validate(task_graph)

    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"任务图验证失败: {', '.join(errors)}"
        )

    workflow_id = task_graph.workflow_id
    with _workflows_lock:
        _workflows[workflow_id] = {
            "task_graph": task_graph,
            "request": None,
            "user_id": user_id,
        }

    return {
        "workflow_id": workflow_id,
        "status": "imported",
        "node_count": len(task_graph.nodes),
        "message": "工作流导入成功",
    }


@router.post("/{workflow_id}/execute")
async def execute_imported_workflow(
    workflow_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    直接执行已导入的工作流

    不需要自然语言分解，直接执行已存在的任务图
    """
    user_id = token.get("sub") or token.get("user_id")
    history_record = None

    with _workflows_lock:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        workflow_data = _workflows[workflow_id]
        task_graph = workflow_data["task_graph"]

    async def generate_events():
        nonlocal history_record
        try:
            yield json.dumps({
                "event": "workflow_started",
                "workflow_id": workflow_id,
                "session_id": None,
                "is_continuation": False,
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

            executor = WorkflowExecutor(
                task_graph=task_graph,
                timeout=task_graph.timeout if hasattr(task_graph, 'timeout') else 3600,
                node_timeout=300,
                max_concurrent=3,
            )

            event_queue = asyncio.Queue()

            def on_node_start(node_id: str):
                event_queue.put_nowait(json.dumps({
                    "event": "node_started",
                    "node_id": node_id,
                    "timestamp": datetime.now().isoformat(),
                }) + "\n")

            def on_node_complete(node_id: str, result):
                event_data = {
                    "event": "node_completed",
                    "node_id": node_id,
                    "success": getattr(result, 'success', True),
                    "timestamp": datetime.now().isoformat(),
                }
                if getattr(result, 'data', None):
                    event_data["data"] = result.data
                if getattr(result, 'error', None):
                    event_data["error"] = result.error
                event_queue.put_nowait(json.dumps(event_data) + "\n")

            async def drain_events():
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                        yield event
                    except asyncio.TimeoutError:
                        break

            executor_task = asyncio.create_task(executor.execute(
                on_node_start=on_node_start,
                on_node_complete=on_node_complete,
            ))

            async for event in drain_events():
                yield event

            while not executor_task.done():
                async for event in drain_events():
                    yield event
                await asyncio.sleep(0.05)

            async for event in drain_events():
                yield event

            result = await executor_task

            yield json.dumps({
                "event": "workflow_completed",
                "workflow_id": workflow_id,
                "status": result["status"],
                "summary": result["summary"],
                "session_id": None,
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

            try:
                graph_dump = task_graph.model_dump() if hasattr(task_graph, 'model_dump') else {
                    "workflow_id": task_graph.workflow_id,
                    "nodes": [
                        {"id": n.id, "type": n.type.value, "params": n.params, "depends_on": n.depends_on}
                        for n in task_graph.nodes
                    ],
                }
                history_record = WorkflowHistory(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    request="直接执行工作流",
                    task_graph=graph_dump,
                    status=result["status"],
                    nodes_count=len(task_graph.nodes),
                    completed_nodes=result.get("summary", {}).get("completed_nodes", 0),
                    result_summary=json.dumps(result.get("summary", {}), ensure_ascii=False)[:1000],
                )
                db.add(history_record)
                await db.commit()
                logger.info(f"工作流直接执行历史记录已保存: {workflow_id}")
            except Exception as e:
                logger.error(f"保存工作流历史记录失败: {e}")

        except Exception as e:
            logger.error(f"直接执行工作流失败: {e}", exc_info=True)
            yield json.dumps({
                "event": "workflow_error",
                "error": "execution_failed",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }) + "\n"

    return StreamingResponse(
        generate_events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/export/{workflow_id}")
async def export_workflow(
    workflow_id: str,
    token: dict = Depends(verify_token),
):
    """
    导出工作流 JSON

    Args:
        workflow_id: 工作流 ID
    """
    with _workflows_lock:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_data = _workflows[workflow_id]
        task_graph = workflow_data["task_graph"]

        if hasattr(task_graph, 'model_dump'):
            export_data = task_graph.model_dump()
        else:
            export_data = {
                "workflow_id": task_graph.workflow_id,
                "version": task_graph.version,
                "nodes": [
                    {
                        "id": node.id,
                        "type": node.type.value,
                        "params": node.params,
                        "depends_on": node.depends_on,
                    }
                    for node in task_graph.nodes
                ],
                "timeout": task_graph.timeout,
                "exportable": task_graph.exportable,
            }

        return {
            "workflow_id": workflow_id,
            "export_data": export_data,
        }


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    token: dict = Depends(verify_token),
):
    """
    删除工作流

    Args:
        workflow_id: 工作流 ID
    """
    with _workflows_lock:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        del _workflows[workflow_id]

    return {
        "workflow_id": workflow_id,
        "status": "deleted",
        "message": "工作流已删除",
    }


@router.get("/history")
async def get_workflow_history(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取当前用户的工作流历史记录"""
    user_id = token.get("sub") or token.get("user_id")

    query = (
        select(WorkflowHistory)
        .where(WorkflowHistory.user_id == user_id)
        .order_by(WorkflowHistory.created_at.desc())
    )

    total_result = await db.execute(
        select(WorkflowHistory).where(WorkflowHistory.user_id == user_id)
    )
    total = len(total_result.all())

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    records = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [r.to_dict() for r in records],
    }


@router.get("/history/{workflow_id}")
async def get_workflow_history_detail(
    workflow_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """获取工作流历史详情"""
    user_id = token.get("sub") or token.get("user_id")

    result = await db.execute(
        select(WorkflowHistory)
        .where(WorkflowHistory.workflow_id == workflow_id)
        .where(WorkflowHistory.user_id == user_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="工作流历史记录不存在")

    return record.to_dict()


@router.delete("/history/{workflow_id}")
async def delete_workflow_history(
    workflow_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """删除工作流历史记录"""
    user_id = token.get("sub") or token.get("user_id")

    result = await db.execute(
        select(WorkflowHistory)
        .where(WorkflowHistory.workflow_id == workflow_id)
        .where(WorkflowHistory.user_id == user_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="工作流历史记录不存在")

    await db.delete(record)
    await db.commit()

    return {
        "workflow_id": workflow_id,
        "status": "deleted",
        "message": "工作流历史记录已删除",
    }

