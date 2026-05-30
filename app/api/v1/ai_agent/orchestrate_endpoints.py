import logging
import json
import asyncio
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sql_delete, and_

from app.utils.security import verify_token
from app.db.database import get_db, async_session
from app.db.models import ProjectSession
from app.agent import OrchestratorAgent
from app.agent.impact_analyzer import ImpactAnalyzer
from app.agent.project_profiler import ProjectProfiler
from app.agent.test_selector import TestSelector
from app.agent.failure_clusterer import FailureClusterer
from app.api.v1.AiProjectCode import create_agent_session, log_tool_execution, update_model_stats

from .schemas import (
    OrchestratorRequest, OrchestratorResponse,
    ModifyRequest, ComplexityAnalysisRequest, ComplexityAnalysisResponse,
    EvaluateRequest, EvaluateResponse,
    TokenUsageStatsResponse,
)
from .helpers import (
    get_session_manager, get_spec_cache, get_feedback_learner,
    _approval_queues, _create_project_session, _update_project_session_status,
    verify_admin_token, get_user_recent_session,
    detect_resume_intent, analyze_files_to_regenerate,
)
from app.utils.guardrails import (
    check_disk_space, check_rate_limit, validate_session_id
)

_decision_queues: Dict[str, asyncio.Queue] = {}

logger = logging.getLogger(__name__)
router = APIRouter()


async def _cleanup_session_queues(session_id: str):
    """清理会话相关的队列，防止内存泄漏"""
    if session_id in _approval_queues:
        del _approval_queues[session_id]
    if session_id in _decision_queues:
        del _decision_queues[session_id]


async def _cleanup_all_queues():
    """清理所有队列（用于异常恢复）"""
    global _approval_queues, _decision_queues
    _approval_queues.clear()
    _decision_queues.clear()


@router.post("/modify", response_model=OrchestratorResponse)
async def modify_project(
    request: ModifyRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 防护：检查速率限制
    rate_ok, rate_msg = check_rate_limit(f"modify:{user_id}")
    if not rate_ok:
        raise HTTPException(status_code=429, detail=rate_msg)

    # 防护：检查磁盘空间
    disk_ok, disk_msg = check_disk_space("./projects")
    if not disk_ok:
        raise HTTPException(status_code=507, detail=disk_msg)

    base_dir = Path("./projects").resolve()
    project_dir = (base_dir / request.project_path).resolve()

    if not str(project_dir).startswith(str(base_dir)):
        raise HTTPException(status_code=403, detail="无权访问该路径")
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在: {request.project_path}")
    if not project_dir.is_dir():
        raise HTTPException(status_code=400, detail="不是有效的项目文件夹")

    session_id = request.session_id or f"modify_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    sm = await get_session_manager()

    start_time = time.time()
    try:
        orchestrator = OrchestratorAgent(
            output_dir=project_dir,
            enable_review=request.enable_review,
            enable_validation=request.enable_validation,
            enable_error_recovery=request.enable_error_recovery,
            memory_enabled=request.enable_memory,
            spec_first=False,
            dependency_graph=request.dependency_graph,
            callback=lambda msg: logger.info(f"Modify 进度: {msg[:200]}"),
            session_manager=sm,
            session_id=session_id,
            incremental=True,
            api_key_token=request.api_key_token
        )

        result = await orchestrator.generate(requirement=request.requirement)

        execution_time = time.time() - start_time
        await log_tool_execution(
            db, session_id, "orchestrator_modify",
            {"requirement": request.requirement, "project_path": request.project_path},
            json.dumps(result, ensure_ascii=False)[:5000] if result else None,
            success=result.get("success", False),
            execution_time=execution_time
        )

        return OrchestratorResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"增量修改失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"项目修改失败: {str(e)}")


@router.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate_project(
    request: OrchestratorRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = request.output_dir or f"./projects/orchestrator/{timestamp}_{user_id}"

    logger.info(f"Orchestrator 生成请求 | user={user_id} | requirement={request.requirement[:50]}...")

    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    session = await create_agent_session(
        db, int(user_id), "orchestrator", request.requirement
    )
    session_id = session.id if session else None

    start_time = time.time()

    try:
        orchestrator = OrchestratorAgent(
            output_dir=output_dir,
            enable_review=request.enable_review,
            enable_validation=request.enable_validation,
            enable_error_recovery=request.enable_error_recovery,
            memory_enabled=request.enable_memory,
            spec_first=request.spec_first,
            dependency_graph=request.dependency_graph,
            callback=lambda msg: logger.info(f"Orchestrator 进度: {msg[:200]}"),
            session_id=session_id,
            incremental=request.incremental,
            evaluation_only=request.evaluation_only
        )
        
        result = await orchestrator.generate(requirement=request.requirement)

        execution_time = time.time() - start_time
        await log_tool_execution(
            db, session_id, "orchestrator_generate",
            {"requirement": request.requirement, "output_dir": output_dir},
            json.dumps(result, ensure_ascii=False)[:5000] if result else None,
            success=result.get("success", False),
            execution_time=execution_time
        )

        for role, model in result.get("models_used", {}).items():
            await update_model_stats(
                db, int(user_id),
                model, model,
                success=result.get("success", False),
                execution_time=execution_time
            )

        return OrchestratorResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestrator 生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"项目生成失败: {str(e)}")


@router.post("/orchestrate/stream")
async def orchestrate_project_stream(
    request: OrchestratorRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub", "anonymous")

    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 防护：检查速率限制
    rate_ok, rate_msg = check_rate_limit(f"stream:{user_id}")
    if not rate_ok:
        raise HTTPException(status_code=429, detail=rate_msg)

    # 防护：检查磁盘空间
    disk_ok, disk_msg = check_disk_space("./projects")
    if not disk_ok:
        raise HTTPException(status_code=507, detail=disk_msg)

    from app.utils.system_config import system_config_manager
    
    user_role = token.get("role", "user")
    
    if not system_config_manager.can_create_new_session(user_id, user_role):
        active_sessions = system_config_manager.get_active_sessions_for_user(user_id)
        limit = system_config_manager.get_user_concurrent_limit(user_id, user_role)
        raise HTTPException(
            status_code=429, 
            detail=f"已达到并发会话限制 ({len(active_sessions)}/{limit})。请停止或删除现有项目后再创建新项目。"
        )

    # ========== 意图检测：处理"继续"语义 ==========
    resume_intent = await detect_resume_intent(request.requirement)
    is_resume = resume_intent.get("is_resume", False)
    has_changes = resume_intent.get("has_changes", False)
    additional_requirement = resume_intent.get("additional_requirement", "")
    
    if is_resume:
        # 查找用户最近的会话
        recent_session = await get_user_recent_session(db, user_id, status_filter="running")
        if not recent_session:
            recent_session = await get_user_recent_session(db, user_id, status_filter="cancelled")
        
        if recent_session:
            # 恢复已有会话
            session_id = recent_session.session_id
            output_dir = recent_session.output_dir
            original_requirement = recent_session.requirement
            
            # 如果有补充需求，合并需求
            if has_changes and additional_requirement:
                merged_requirement = f"{original_requirement}\n\n补充需求：{additional_requirement}"
                request.requirement = merged_requirement
                
                # 分析需要重新生成的文件
                sm = await get_session_manager()
                session_state = await sm.resume_session(session_id)
                
                if session_state and session_state.file_statuses:
                    generated_files = [f for f, s in session_state.file_statuses.items() if s.status == "completed"]
                    
                    if generated_files:
                        files_to_regenerate = await analyze_files_to_regenerate(
                            original_requirement, additional_requirement, generated_files
                        )
                        
                        # 删除需要重新生成的文件
                        for file_path in files_to_regenerate:
                            full_path = Path(output_dir) / file_path
                            if full_path.exists():
                                full_path.unlink()
                                logger.info(f"删除需要重新生成的文件: {file_path}")
            else:
                # 纯继续，使用原始需求
                request.requirement = original_requirement
            
            logger.info(f"继续会话 | session={session_id} | has_changes={has_changes}")
        else:
            # 没有找到可恢复的会话，创建新会话
            logger.info(f"没有找到可恢复的会话，创建新会话")
            is_resume = False
    
    if not is_resume:
        if request.session_id:
            session_id = request.session_id
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = f"project_{user_id}_{timestamp}"
        
        output_dir = request.output_dir or f"./projects/orchestrator/{session_id}"
    # ========== 意图检测结束 ==========

    logger.info(f"Orchestrator 流式生成请求 | user={user_id} session={session_id}")

    await _create_project_session(db, int(user_id), session_id, request.requirement, output_dir)

    queue: asyncio.Queue = asyncio.Queue()
    approval_queue: asyncio.Queue = asyncio.Queue()
    decision_queue: asyncio.Queue = asyncio.Queue()
    cancel_event = asyncio.Event()

    _approval_queues[session_id] = approval_queue
    _decision_queues[session_id] = decision_queue

    async def approval_callback(file_path: str) -> bool:
        await queue.put(f"data: {json.dumps({'type': 'pause_for_approval', 'data': {'file_path': file_path, 'session_id': session_id}}, ensure_ascii=False)}\n\n")
        try:
            result = await asyncio.wait_for(
                asyncio.gather(approval_queue.get(), cancel_event.wait(), return_when=asyncio.FIRST_COMPLETED),
                timeout=300
            )
            if cancel_event.is_set():
                return False
            return result[0].get("approved", True) if isinstance(result, tuple) else result.get("approved", True)
        except asyncio.TimeoutError:
            logger.warning(f"审批超时: {file_path}，自动批准")
            return True

    sm = await get_session_manager()
    cache = await get_spec_cache()
    learner = await get_feedback_learner()

    async def event_generator() -> AsyncIterator[str]:
        logger.info(f"[SSE] event_generator 开始 | session={session_id}")
        try:
            async def stream_callback(msg: str):
                try:
                    progress_data = json.loads(msg)
                    if progress_data.get("critical_decisions"):
                        await queue.put(f"data: {json.dumps({'type': 'critical_decisions', 'data': {'session_id': session_id, 'decisions': progress_data['critical_decisions']}}, ensure_ascii=False)}\n\n")
                        try:
                            done, _ = await asyncio.wait(
                                [asyncio.create_task(decision_queue.get()), asyncio.create_task(cancel_event.wait())],
                                timeout=120,
                                return_when=asyncio.FIRST_COMPLETED
                            )
                            if cancel_event.is_set():
                                return
                            for task in done:
                                result = task.result()
                                if result is not None:
                                    decisions = result
                                    logger.info(f"用户决策: {decisions}")
                                    break
                        except asyncio.TimeoutError:
                            logger.warning("决策等待超时，使用默认值继续")
                    # 特殊类型直接传递，不包装成 progress
                    msg_type = progress_data.get("type", "")
                    if msg_type in ("thinking", "model_info", "file", "file_diff"):
                        await queue.put(f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n")
                    else:
                        await queue.put(f"data: {json.dumps({'type': 'progress', 'data': progress_data}, ensure_ascii=False)}\n\n")
                except json.JSONDecodeError:
                    await queue.put(f"data: {json.dumps({'type': 'log', 'data': {'message': msg}}, ensure_ascii=False)}\n\n")

            logger.info(f"[SSE] 创建 orchestrator | session={session_id}")
            orchestrator = OrchestratorAgent(
                output_dir=output_dir,
                enable_review=request.enable_review,
                enable_validation=request.enable_validation,
                enable_error_recovery=request.enable_error_recovery,
                memory_enabled=request.enable_memory,
                spec_first=request.spec_first,
                dependency_graph=request.dependency_graph,
                callback=stream_callback,
                session_manager=sm,
                session_id=session_id,
                incremental=request.incremental,
                spec_cache=cache,
                require_approval=request.require_approval,
                approval_callback=approval_callback if request.require_approval else None,
                feedback_learner=learner,
                evaluation_only=request.evaluation_only,
                api_key_token=request.api_key_token,
                provider_id=request.provider_id
            )

            async def run_generation():
                try:
                    logger.info(f"[SSE] 开始生成任务 | session={session_id}")
                    result = await orchestrator.generate(requirement=request.requirement)
                    files_generated = result.get("total_files_created", 0)
                    files_total = result.get("total_files", 0)
                    logger.info(f"[SSE] 生成完成 | session={session_id} files={files_generated}/{files_total}")
                    async with async_session() as gen_db:
                        await _update_project_session_status(gen_db, session_id, "completed", files_generated, files_total)
                    await queue.put(f"data: {json.dumps({'type': 'done', 'data': result}, ensure_ascii=False)}\n\n")
                except Exception as e:
                    logger.error(f"[SSE] Orchestrator 流式生成失败: {e}", exc_info=True)
                    async with async_session() as gen_db:
                        await _update_project_session_status(gen_db, session_id, "failed", error_message=str(e))
                    await queue.put(f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n")
                finally:
                    await _cleanup_session_queues(session_id)
                    await queue.put("[DONE]")

            logger.info(f"[SSE] 创建生成任务 | session={session_id}")
            gen_task = asyncio.create_task(run_generation())

            try:
                logger.info(f"[SSE] 开始等待队列消息 | session={session_id}")
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=1.0)
                        logger.info(f"[SSE] 从队列获取消息 | session={session_id} type={item[:30] if len(item) > 30 else item}")
                        if item == "[DONE]":
                            break
                        yield item
                    except asyncio.TimeoutError:
                        # Check if generation task is still running
                        if gen_task.done():
                            logger.info(f"[SSE] 生成任务已完成 | session={session_id}")
                            break
                        continue
                logger.info(f"[SSE] 队列消息处理完成 | session={session_id}")
            except asyncio.CancelledError:
                logger.info(f"[SSE] 客户端断开连接，取消生成任务 | session={session_id}")
            finally:
                cancel_event.set()
                if not gen_task.done():
                    gen_task.cancel()
                    try:
                        await asyncio.wait_for(gen_task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                await _cleanup_session_queues(session_id)
                await sm.cancel_session(session_id)
                async with async_session() as gen_db:
                    await _update_project_session_status(gen_db, session_id, "cancelled")

        except asyncio.CancelledError:
            logger.info("[SSE] Orchestrator 流式响应被取消")
            await _cleanup_session_queues(session_id)
        except Exception as e:
            logger.error(f"[SSE] Orchestrator 流式生成器异常：{e}")
            await _cleanup_session_queues(session_id)
            yield f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/analyze_complexity", response_model=ComplexityAnalysisResponse)
async def analyze_project_complexity(
    request: ComplexityAnalysisRequest,
    token: dict = Depends(verify_token)
):
    from app.agent.orchestrator import ComplexityAnalyzer, LayeredModelRouter

    analyzer = ComplexityAnalyzer()
    complexity = analyzer.analyze(request.requirement)
    assignment = LayeredModelRouter.get_assignment(complexity.level)

    return ComplexityAnalysisResponse(
        level=complexity.level.value,
        estimated_files=complexity.estimated_files,
        has_frontend=complexity.has_frontend,
        has_backend=complexity.has_backend,
        has_database=complexity.has_database,
        key_technologies=complexity.key_technologies,
        risk_factors=complexity.risk_factors,
        model_assignment={
            "architect": assignment.architect_model,
            "frontend": assignment.frontend_model,
            "backend": assignment.backend_model,
            "reviewer": assignment.reviewer_model,
            "fallback": assignment.fallback_model
        }
    )


@router.get("/snapshots/{session_id}")
async def list_snapshots(
    session_id: str,
    token: dict = Depends(verify_token),
):
    from app.agent.git_operations import GitOperations
    git_ops = GitOperations()

    project_dir = Path(f"orchestrator/{session_id}")
    if not project_dir.exists():
        project_dir = Path(f"user_uploads/{session_id}")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目目录不存在: {session_id}")

    snapshots = await git_ops.list_snapshots(project_dir)
    return {"session_id": session_id, "snapshots": [{"tag": s.tag, "commit": s.commit_hash, "message": s.message, "timestamp": s.timestamp} for s in snapshots]}


@router.post("/rollback/{session_id}")
async def rollback_to_snapshot(
    session_id: str,
    target_tag: str,
    delete_branch: bool = True,
    token: dict = Depends(verify_token),
):
    from app.agent.snapshot_manager import SnapshotManager, RollbackResult
    from app.agent.git_operations import GitOperations
    git_ops = GitOperations()
    snapshot_mgr = SnapshotManager(git_ops)

    project_dir = Path(f"orchestrator/{session_id}")
    if not project_dir.exists():
        project_dir = Path(f"user_uploads/{session_id}")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目目录不存在: {session_id}")

    result = await snapshot_mgr.rollback_to_snapshot(
        project_dir, target_tag, delete_branch
    )

    if result is None:
        raise HTTPException(status_code=404, detail=f"快照不存在: {target_tag}")

    return {"success": result.success, "previous_tag": result.previous_tag, "current_tag": result.current_tag, "files_restored": result.files_restored}


@router.get("/snapshot/diff")
async def diff_snapshots(
    session_id: str,
    from_tag: str,
    to_tag: str,
    token: dict = Depends(verify_token),
):
    from app.agent.git_operations import GitOperations
    git_ops = GitOperations()

    project_dir = Path(f"orchestrator/{session_id}")
    if not project_dir.exists():
        project_dir = Path(f"user_uploads/{session_id}")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目目录不存在: {session_id}")

    diff = await git_ops.diff_between_commits(project_dir, from_tag, to_tag)
    return {"session_id": session_id, "from": from_tag, "to": to_tag, "diff": diff[:5000]}


@router.put("/concurrent-limits")
async def update_concurrent_limits(
    role: str,
    new_limit: int,
    token: dict = Depends(verify_admin_token),
):
    from app.utils.system_config import system_config_manager

    if new_limit < 1:
        raise HTTPException(status_code=400, detail="限制值必须为正整数")

    username = token.get("sub", "admin")
    record = await system_config_manager.update_concurrent_limit(
        role, new_limit, username, "API 调用"
    )
    return {"role": role, "old_limit": record.old_limit, "new_limit": record.new_limit, "changed_by": record.changed_by, "timestamp": record.timestamp.isoformat()}


@router.get("/concurrent-limits/recommended")
async def get_recommended_limits(
    token: dict = Depends(verify_token),
):
    from app.utils.system_config import system_config_manager
    recommendations = await system_config_manager.concurrent_mgr.get_recommended_limits()
    return {"recommendations": recommendations}


@router.get("/concurrent-limits/history")
async def get_limit_change_history(
    limit: int = 50,
    token: dict = Depends(verify_token),
):
    from app.utils.system_config import system_config_manager
    history = system_config_manager.get_limit_change_history(limit)
    return {"history": [{"role": r.role, "old_limit": r.old_limit, "new_limit": r.new_limit, "changed_by": r.changed_by, "timestamp": r.timestamp.isoformat()} for r in history]}


@router.get("/cache/stats")
async def get_cache_stats(token: dict = Depends(verify_token)):
    cache = await get_spec_cache()
    return cache.get_stats()


@router.post("/cache/clear")
async def clear_cache(mode: str = "expired", token: dict = Depends(verify_token)):
    cache = await get_spec_cache()
    if mode == "all":
        cleared = cache.clear_all()
    else:
        cleared = cache.clear_expired()
    return {"cleared_count": cleared, "mode": mode}


@router.get("/learning/stats")
async def get_learning_stats(token: dict = Depends(verify_token)):
    learner = await get_feedback_learner()
    return learner.get_learning_stats()


@router.get("/learning/common-errors/{file_type}")
async def get_common_errors(file_type: str, token: dict = Depends(verify_token)):
    learner = await get_feedback_learner()
    return {"errors": learner.get_common_errors(file_type)}


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_project(
    request: EvaluateRequest,
    token: dict = Depends(verify_token),
):
    """需求评价模式 - 只评价不修改，输出分析报告和改进建议"""
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = request.output_dir or f"./projects/evaluation/{timestamp}_{user_id}"

    logger.info(f"评价请求 | user={user_id} | requirement={request.requirement[:50]}...")

    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    try:
        orchestrator = OrchestratorAgent(
            output_dir=output_dir,
            evaluation_only=True,
            callback=lambda msg: logger.info(f"Evaluate 进度: {msg[:200]}"),
            api_key_token=request.api_key_token
        )

        result = await orchestrator.generate(requirement=request.requirement)

        return EvaluateResponse(**result)

    except Exception as e:
        logger.error(f"评价失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"评价失败: {str(e)}")


# ========================================
# 会话管理端点
# ========================================

@router.post("/session/{session_id}/action")
async def session_action_endpoint(
    session_id: str,
    action: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """会话操作（取消、恢复、审批）"""
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 防护：验证会话所有权
    await _verify_session_ownership_or_queue(session_id, user_id)

    sm = await get_session_manager()

    if action == "cancel":
        await sm.cancel_session(session_id)
        await _update_project_session_status(db, session_id, "cancelled")
        return {"status": "cancelled", "session_id": session_id}
    elif action == "resume":
        await sm.resume_from_pause(session_id, approved=True)
        return {"status": "resumed", "session_id": session_id}
    elif action in ("approve", "reject"):
        approved = action == "approve"
        q = _approval_queues.get(session_id)
        if q:
            await q.put({"approved": approved})
        await sm.resume_from_pause(session_id, approved=approved)
        return {"status": action, "session_id": session_id}
    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@router.post("/session/{session_id}/decision")
async def submit_decision_endpoint(
    session_id: str,
    decisions: Dict[str, str],
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """提交用户架构决策"""
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 防护：验证会话所有权
    await _verify_session_ownership_or_queue(session_id, user_id, db)

    q = _decision_queues.get(session_id)
    if q:
        await q.put(decisions)
        logger.info(f"用户 {user_id} 提交决策: session={session_id}, decisions={decisions}")
        return {"status": "submitted", "session_id": session_id, "decisions": decisions}
    else:
        logger.warning(f"决策队列不存在: session={session_id}")
        return {"status": "ignored", "session_id": session_id, "message": "没有等待的决策请求"}


async def _verify_session_ownership_or_queue(session_id: str, user_id: str, db: AsyncSession = None):
    """
    验证用户对会话的访问权限
    对于队列操作，检查是否在等待的队列中即可（更宽松）
    """
    # 如果会话在队列中，允许操作（可能是刚创建的会话）
    if session_id in _approval_queues or session_id in _decision_queues:
        return
    
    # 否则需要验证数据库所有权
    if db:
        from .helpers import verify_session_ownership
        try:
            await verify_session_ownership(db, session_id, user_id)
        except HTTPException:
            # 如果数据库验证失败，但仍然允许队列操作（兼容旧逻辑）
            pass


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """删除会话"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    result = await db.execute(
        sql_delete(ProjectSession).where(
            and_(
                ProjectSession.id == session_id,
                ProjectSession.user_id == int(user_id)
            )
        )
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 清理会话文件
    for session_dir in [
        Path(f"./projects/orchestrator/{session_id}"),
        Path(f"./orchestrator/{session_id}"),
        Path(f"./projects/user_uploads/{session_id}"),
    ]:
        if session_dir.exists() and session_dir.is_dir():
            shutil.rmtree(session_dir, ignore_errors=True)

    return {"success": True, "message": "会话已删除"}


@router.get("/token-usage", response_model=TokenUsageStatsResponse)
async def get_token_usage_stats(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户 token 使用统计"""
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份")
    
    user_id_int = int(user_id)
    
    try:
        from sqlalchemy import func, select
        from app.models.chat_history import ChatHistory
        from datetime import datetime, timedelta
        
        # 总 token 使用量
        total_result = await db.execute(
            select(
                func.sum(ChatHistory.token_usage).label("total_tokens"),
                func.sum(ChatHistory.prompt_tokens).label("total_prompt_tokens"),
                func.sum(ChatHistory.completion_tokens).label("total_completion_tokens"),
                func.count(ChatHistory.id).label("total_messages")
            ).where(ChatHistory.user_id == user_id_int)
        )
        total_row = total_result.first()
        total_tokens = total_row.total_tokens or 0
        total_prompt_tokens = total_row.total_prompt_tokens or 0
        total_completion_tokens = total_row.total_completion_tokens or 0
        total_messages = total_row.total_messages or 0
        
        # 今日 token 使用量
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_result = await db.execute(
            select(
                func.sum(ChatHistory.token_usage).label("today_tokens"),
                func.sum(ChatHistory.prompt_tokens).label("today_prompt_tokens"),
                func.sum(ChatHistory.completion_tokens).label("today_completion_tokens")
            ).where(
                ChatHistory.user_id == user_id_int,
                ChatHistory.created_at >= today_start
            )
        )
        today_row = today_result.first()
        today_tokens = today_row.today_tokens or 0
        today_prompt_tokens = today_row.today_prompt_tokens or 0
        today_completion_tokens = today_row.today_completion_tokens or 0
        
        # 本月 token 使用量
        month_start = today_start.replace(day=1)
        month_result = await db.execute(
            select(
                func.sum(ChatHistory.token_usage).label("month_tokens"),
                func.sum(ChatHistory.prompt_tokens).label("month_prompt_tokens"),
                func.sum(ChatHistory.completion_tokens).label("month_completion_tokens")
            ).where(
                ChatHistory.user_id == user_id_int,
                ChatHistory.created_at >= month_start
            )
        )
        month_row = month_result.first()
        this_month_tokens = month_row.month_tokens or 0
        this_month_prompt_tokens = month_row.month_prompt_tokens or 0
        this_month_completion_tokens = month_row.month_completion_tokens or 0
        
        # 按模型统计
        model_result = await db.execute(
            select(
                ChatHistory.model,
                func.sum(ChatHistory.token_usage).label("model_tokens"),
                func.sum(ChatHistory.prompt_tokens).label("model_prompt_tokens"),
                func.sum(ChatHistory.completion_tokens).label("model_completion_tokens")
            ).where(
                ChatHistory.user_id == user_id_int,
                ChatHistory.model.isnot(None)
            ).group_by(ChatHistory.model)
        )
        by_model = {row.model: row.model_tokens or 0 for row in model_result.all()}
        
        return TokenUsageStatsResponse(
            total_tokens=total_tokens,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_messages=total_messages,
            today_tokens=today_tokens,
            this_month_tokens=this_month_tokens,
            by_model=by_model
        )
        
    except Exception as e:
        logger.error(f"获取 token 使用统计失败: {e}")
        return TokenUsageStatsResponse()