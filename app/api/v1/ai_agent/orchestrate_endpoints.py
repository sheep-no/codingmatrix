import logging
import json
import asyncio
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, Any, List, FrozenSet

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sql_delete, and_, select

from app.utils.security import verify_token
from app.db.database import get_db, async_session
from app.db.models import ProjectSession
from app.agent import OrchestratorAgent
from app.agent.workflow_registry import build_legacy_workflow, run_workflow
from app.agent.multi_model_agent import MultiModelAgent


# SSE 透传事件类型集合：直接发送给前端（不被包装成 progress）
# 修复 v5.x → v6.x：test/validation/cost/perf/warning/file_rejected/step_detail
# 之前被错误包装成 progress 导致前端对应 UI 永远收不到数据
PASSTHROUGH_SSE_EVENTS: FrozenSet[str] = frozenset({
    # 进度类
    "thinking", "model_info", "file", "file_diff",
    # 实时统计/结果
    "test_results", "validation_results",
    "cost_update", "performance_metrics",
    # 警告/拒绝/步骤
    "warning", "file_rejected", "step_detail",
    # ReAct 反思事件
    "react_tool_call", "react_tool_result", "react_generating",
})


def resolve_sync_output_dir(
    project_path: str | None,
    output_dir: str | None,
    user_id: str,
    timestamp: str,
) -> str:
    """同步 /orchestrate 端点的 output_dir 解析

    优先级：project_path > request.output_dir > 时间戳目录
    """
    return (
        project_path
        or output_dir
        or f"./projects/orchestrator/{timestamp}_{user_id}"
    )


def resolve_stream_output_dir(
    project_path: str | None,
    session_id: str | None,
    project_name: str | None,
    user_id: str,
    timestamp: str,
) -> tuple[str, str, str]:
    """流式 /orchestrate/stream 端点的 (output_dir, project_name, session_id) 解析

    优先级：
      1. project_path（增量模式：前端明确指定） → 取 Path 最后一段当 project_name
      2. session_id（续传） → 从 session_id 推导 project_name
      3. 全 new → 用 project_name 或时间戳

    Returns:
        (output_dir, project_name, session_id)
    """
    from app.api.v1.ai_agent.project_config import PROJECTS_BASE_DIR

    if project_path:
        resolved_name = Path(project_path).name
        resolved_session = (
            session_id
            if session_id
            else f"{user_id}_{resolved_name}"
        )
        # 确保是相对于 PROJECTS_BASE_DIR 的路径
        output_dir = project_path
        if output_dir.startswith(PROJECTS_BASE_DIR + "/"):
            output_dir = output_dir[len(PROJECTS_BASE_DIR) + 1:]
        return output_dir, resolved_name, resolved_session

    if session_id:
        resolved_name = (
            session_id.replace(f"{user_id}_", "", 1)
            if session_id.startswith(f"{user_id}_")
            else session_id
        )
        output_dir = f"{user_id}/{resolved_name}"
        return output_dir, resolved_name, session_id

    resolved_name = project_name or f"untitled_{timestamp}"
    resolved_session = f"{user_id}_{resolved_name}"
    output_dir = f"{user_id}/{resolved_name}"
    return output_dir, resolved_name, resolved_session
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
    SearchSessionsRequest, SearchSessionsResponse, SessionMatch,
)
from .helpers import (
    get_session_manager, get_spec_cache, get_feedback_learner,
    _approval_queues, _create_project_session, _update_project_session_status,
    verify_admin_token, get_user_recent_session,
    detect_resume_intent, resolve_resume_session, analyze_files_to_regenerate,
    _detect_and_clean_zombie_sessions, cleanup_session_files,
)
from app.agent.conversation_store import get_conversation_store
from app.utils.guardrails import (
    check_disk_space, check_rate_limit, validate_session_id
)

_decision_queues: Dict[str, asyncio.Queue] = {}
_cancel_events: Dict[str, asyncio.Event] = {}
# 运行中的生成任务，用于浏览器重连
_active_tasks: Dict[str, dict] = {}
_user_creation_locks: Dict[str, asyncio.Lock] = {}

logger = logging.getLogger(__name__)


def _skill_context_for_user(user_id: str) -> str:
    """Build a bounded, namespaced Skill context for the Web Agent."""
    from app.api.v1.agent_host import get_latest_session_skills
    from app.services.custom_skill_manager import get_skill_manager

    sections = []
    manager = get_skill_manager()
    for skill in manager.list_skills(owner_user_id=str(user_id)):
        detail = manager.get_skill(skill["name"], owner_user_id=str(user_id))
        if detail:
            sections.append(f"[user:{skill['name']}]\n{detail['content']}")
    for name, skill in get_latest_session_skills(str(user_id)).items():
        content = skill.get("content") if isinstance(skill, dict) else None
        if isinstance(content, str):
            sections.append(f"[{name}]\n{content}")
    if not sections:
        return ""
    return "\n\n[Available Skills]\n" + "\n\n".join(sections)[:200_000]
router = APIRouter()

# 分析类意图关键词
_ANALYZE_KEYWORDS = [
    "分析", "改进", "优化", "建议", "review", "审查", "评估", "怎么样",
    "有什么", "哪些", "如何改进", "代码质量", "架构", "安全", "性能",
    "帮我看看", "帮我分析", "帮我review", "帮我评估",
    "analyze", "improve", "optimize", "suggest", "evaluate", "assess",
    "what do you think", "how to improve", "code review",
]


def _is_analyze_intent(requirement: str) -> bool:
    """判断用户意图是分析还是修改"""
    req_lower = requirement.lower()
    for keyword in _ANALYZE_KEYWORDS:
        if keyword in req_lower:
            return True
    return False


async def _cleanup_session_queues(session_id: str, expected_cancel_event: asyncio.Event = None):
    """清理会话相关的队列，防止内存泄漏。
    
    Args:
        session_id: 会话 ID
        expected_cancel_event: 如果提供，只在 cancel_event 仍是同一个对象时才删除（防止旧任务清理新任务的资源）
    """
    if session_id in _approval_queues:
        del _approval_queues[session_id]
    if session_id in _decision_queues:
        del _decision_queues[session_id]
    if session_id in _cancel_events:
        if expected_cancel_event is None or _cancel_events.get(session_id) is expected_cancel_event:
            del _cancel_events[session_id]


async def _cleanup_all_queues():
    """清理所有队列（用于异常恢复）"""
    global _approval_queues, _decision_queues, _cancel_events
    _approval_queues.clear()
    _decision_queues.clear()
    _cancel_events.clear()


async def _handle_analyze_request(request: ModifyRequest, project_dir: Path, user_id: str) -> dict:
    """处理分析类请求 — 只读代码，返回自然语言分析"""
    from app.agent.backend_engineer import BackendEngineer
    from app.agent.dynamic_model_router import get_dynamic_router

    # 获取模型配置
    dynamic_router = await get_dynamic_router()
    model_name = await dynamic_router.get_best_model(
        ["THUDM/GLM-Z1-9B-0414", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"],
        task_type="analyze"
    )

    # 创建工程师实例
    engineer = BackendEngineer(
        role_name="代码分析师",
        model_name=model_name,
        task_type="generate",
    )

    # 读取项目上下文
    project_context = {}
    dep_graph_path = project_dir / ".dep_graph.json"
    if dep_graph_path.exists():
        try:
            from app.agent.dependency_graph import DependencyGraph
            dep_graph = DependencyGraph.load(str(dep_graph_path))
            # 尝试从节点推断语言
            language = "python"  # 默认
            for node in dep_graph.nodes.values():
                if hasattr(node, 'file_type') and node.file_type == "frontend":
                    language = "javascript"
                    break
            project_context["architecture"] = {
                "language": language,
            }
        except Exception:
            pass

    # 调用分析模式
    try:
        logger.info(f"开始分析: {request.requirement[:50]}...")
        result = await engineer.analyze(
            question=request.requirement,
            project_path=str(project_dir),
            project_context=project_context,
        )
        logger.info(f"分析完成: {type(result)}, 长度: {len(result) if result else 0}")
        
        # 确保 result 是字符串
        if not isinstance(result, str):
            result = str(result)
        
        return {
            "code": 0,
            "type": "analysis",
            "data": {
                "analysis": result,
                "project_path": str(project_dir),
            }
        }
    except Exception as e:
        logger.error(f"分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/modify")
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

    # 支持 project_path 或 output_dir
    project_path = request.project_path or request.output_dir
    if not project_path:
        raise HTTPException(status_code=400, detail="需要提供 project_path 或 output_dir")

    # 解析项目目录
    if Path(project_path).is_absolute():
        project_dir = Path(project_path).resolve()
    else:
        # 支持两种相对路径格式：
        # 1. "projects/1/untitled_xxx" - 相对于工作区根目录
        # 2. "1/untitled_xxx" - 相对于 projects 目录
        workspace_dir = Path(".").resolve()
        projects_dir = workspace_dir / "projects"
        candidate = (workspace_dir / project_path).resolve()
        if candidate.exists() and candidate.is_dir():
            project_dir = candidate
        else:
            # 尝试相对于 projects 目录
            project_dir = (projects_dir / project_path).resolve()

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_path}")
    if not project_dir.is_dir():
        raise HTTPException(status_code=400, detail="不是有效的项目文件夹")

    # 意图判断：分析类请求走 analyze 逻辑
    if request.requirement and _is_analyze_intent(request.requirement):
        logger.info(f"检测到分析类意图: {request.requirement[:50]}...")
        return await _handle_analyze_request(request, project_dir, user_id)

    session_id = request.session_id or f"modify_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 多轮会话：读取历史并拼接到 requirement
    conversation_store = get_conversation_store()
    history = await conversation_store.get_history_async(session_id, user_id)
    if history:
        # 截断历史（保留最近 10 轮，最多 4000 token）
        history = conversation_store.truncate_history(history)
        # 构建上下文
        history_text = "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in history
        )
        enhanced_requirement = f"[历史对话]\n{history_text}\n\n[当前需求]\n{request.requirement}"
        logger.info(f"多轮会话: 加载 {len(history)} 条历史消息")
    else:
        enhanced_requirement = request.requirement

    # 保存用户消息到历史（先写数据库，再写 Redis）
    await conversation_store.append_message(session_id, user_id, "user", request.requirement)

    sm = await get_session_manager()
    cache = await get_spec_cache()
    learner = await get_feedback_learner()

    # 更新 DB session 状态
    result = await db.execute(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    existing_session = result.scalar_one_or_none()
    if existing_session:
        existing_session.status = "running"
        existing_session.requirement = request.requirement
        await db.commit()
    else:
        await _create_project_session(db, int(user_id), session_id, request.requirement, str(project_dir))

    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = asyncio.Event()

    async def event_generator() -> AsyncIterator[str]:
        logger.info(f"[SSE] modify event_generator 开始 | session={session_id}")
        try:
            async def stream_callback(msg: str):
                try:
                    progress_data = json.loads(msg)
                    msg_type = progress_data.get("type", "")
                    if msg_type in PASSTHROUGH_SSE_EVENTS:
                        await queue.put(f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n")
                    else:
                        await queue.put(f"data: {json.dumps({'type': 'progress', 'data': progress_data}, ensure_ascii=False)}\n\n")
                except json.JSONDecodeError:
                    await queue.put(f"data: {json.dumps({'type': 'log', 'data': {'message': msg}}, ensure_ascii=False)}\n\n")

            orchestrator = OrchestratorAgent(
                output_dir=str(project_dir),
                enable_review=request.enable_review,
                enable_validation=request.enable_validation,
                enable_error_recovery=request.enable_error_recovery,
                memory_enabled=request.enable_memory,
                spec_first=True,
                dependency_graph=True,
                callback=stream_callback,
                session_manager=sm,
                session_id=session_id,
                incremental=True,
                spec_cache=cache,
                feedback_learner=learner,
                api_key_token=request.api_key_token,
                cancel_event=cancel_event,
            )

            async def run_generation():
                try:
                    logger.info(f"[SSE] 开始增量修改 | session={session_id}")
                    workflow = build_legacy_workflow(
                        "modify",
                        "/modify",
                        lambda _state: orchestrator.generate_incremental(
                            requirement=enhanced_requirement
                        ),
                    )
                    graph_state = await run_workflow(
                        workflow,
                        session_id=session_id,
                        task_id=session_id,
                        metadata={"project_path": str(project_dir)},
                    )
                    gen_result = graph_state.metadata["legacy_result"]
                    files_generated = gen_result.get("total_files_created", 0)
                    files_total = gen_result.get("total_files", 0)
                    await sm.complete_session(session_id, files_generated=files_generated, files_total=files_total)
                    await queue.put(f"data: {json.dumps({'type': 'done', 'data': gen_result}, ensure_ascii=False)}\n\n")

                    # 保存助手回复到历史（先写数据库，再写 Redis）
                    summary = f"修改完成: 生成 {files_generated} 个文件"
                    if gen_result.get("errors"):
                        summary += f", {len(gen_result['errors'])} 个错误"
                    await conversation_store.append_message(session_id, user_id, "assistant", summary)

                    # 记录到 DB
                    execution_time = gen_result.get("elapsed_time", 0)
                    await log_tool_execution(
                        db, session_id, "orchestrator_modify",
                        {"requirement": request.requirement, "project_path": request.project_path},
                        json.dumps(gen_result, ensure_ascii=False)[:5000],
                        success=gen_result.get("success", False),
                        execution_time=execution_time
                    )
                except Exception as e:
                    logger.error(f"[SSE] 增量修改失败: {e}", exc_info=True)
                    await sm.complete_session(session_id, errors=[str(e)])
                    await queue.put(f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n")
                finally:
                    await queue.put("[DONE]")

            gen_task = asyncio.create_task(run_generation())

            # 心跳
            async def heartbeat_sender():
                while not cancel_event.is_set():
                    await asyncio.sleep(5)
                    try:
                        await queue.put(f": heartbeat\n\n")
                    except Exception:
                        break

            heartbeat_task = asyncio.create_task(heartbeat_sender())

            # SSE 流输出
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=60.0)
                    if item == "[DONE]":
                        break
                    yield item
                except asyncio.TimeoutError:
                    if gen_task.done():
                        break
                    continue

            heartbeat_task.cancel()
            logger.info(f"[SSE] modify event_generator 结束 | session={session_id}")

        except Exception as e:
            logger.error(f"[SSE] modify event_generator 异常: {e}", exc_info=True)
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


@router.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate_project(
    request: OrchestratorRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 优先级：前端传来的 project_path > request.output_dir > 时间戳目录
    output_dir = resolve_sync_output_dir(
        request.project_path, request.output_dir, user_id, timestamp
    )

    logger.info(f"Orchestrator 生成请求 | user={user_id} | requirement={request.requirement[:50]}...")

    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    skill_context = _skill_context_for_user(user_id)

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
        
        workflow = build_legacy_workflow(
            "orchestrate",
            "/orchestrate",
            lambda _state: orchestrator.generate(requirement=request.requirement + skill_context),
        )
        graph_state = await run_workflow(
            workflow,
            session_id=str(session_id or output_dir),
            task_id=str(session_id or output_dir),
            metadata={"requirement": request.requirement, "output_dir": output_dir},
        )
        result = graph_state.metadata["legacy_result"]

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
    skill_context = _skill_context_for_user(user_id)

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
    
    # 每用户锁：防止并发请求的 TOCTOU 竞争
    lock = _user_creation_locks.setdefault(user_id, asyncio.Lock())
    
    async with lock:
        # 僵尸会话检测：清理 DB 中 status=running 但内存中无状态的会话
        await _detect_and_clean_zombie_sessions(db, user_id)
        
        # DB 并发检查：每用户最多一个 running 会话
        result = await db.execute(
            select(ProjectSession).where(
                ProjectSession.user_id == int(user_id),
                ProjectSession.status == "running"
            )
        )
        running_session = result.scalar_one_or_none()
        if running_session:
            # 检查是否有活跃的生成任务（浏览器重连场景）
            active_task = _active_tasks.get(running_session.session_id)
            if active_task and not active_task["gen_task"].done():
                # 重连到现有任务
                logger.info(f"[SSE] 检测到活跃任务，允许重连 | session={running_session.session_id}")
                # 直接返回重连响应，使用现有 queue
                async def reconnect_generator():
                    queue = active_task["queue"]
                    try:
                        while True:
                            try:
                                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                                if item == "[DONE]":
                                    yield item
                                    break
                                yield item
                            except asyncio.TimeoutError:
                                if active_task["gen_task"].done():
                                    break
                                continue
                    except asyncio.CancelledError:
                        logger.info(f"[SSE] 重连客户端断开 | session={running_session.session_id}")

                return StreamingResponse(
                    reconnect_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"
                    }
                )
            raise HTTPException(
                status_code=429,
                detail={
                    "message": f"已有运行中的项目 '{running_session.session_id}'。请先完成或停止现有项目后再创建新项目。",
                    "session_id": running_session.session_id,
                    "created_at": running_session.created_at.isoformat() if running_session.created_at else None
                }
            )

        # ========== 意图检测：处理"继续"语义 ==========
        resume_intent = await detect_resume_intent(request.requirement)
        is_resume = resume_intent.get("is_resume", False)
        has_changes = resume_intent.get("has_changes", False)
        additional_requirement = resume_intent.get("additional_requirement", "")
        
        if is_resume:
            # 方案 2：智能解析要恢复的 session
            target_session = await resolve_resume_session(db, user_id, request.requirement)
            
            if target_session:
                # 恢复已有会话
                session_id = target_session.session_id
                output_dir = target_session.output_dir
                original_requirement = target_session.requirement
                
                # 智能匹配结果：检查是否匹配到最近 session
                recent_session = await get_user_recent_session(db, user_id, status_filter="running")
                used_recent = recent_session is not None and target_session.session_id == recent_session.session_id
                logger.info(f"继续会话 | session={session_id} | has_changes={has_changes} | matched_recent={used_recent}")
                
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
            else:
                # 没有找到可恢复的会话，创建新会话
                logger.info(f"没有找到可恢复的会话，创建新会话")
                is_resume = False
        
        if not is_resume:
            # 优先级：前端传来的 project_path > session_id 推导 > 全新生成
            output_dir, project_name, session_id = resolve_stream_output_dir(
                request.project_path,
                request.session_id,
                request.project_name,
                user_id,
                datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
        # ========== 意图检测结束 ==========

        logger.info(f"Orchestrator 流式生成请求 | user={user_id} session={session_id}")

        if not is_resume:
            # Check if session already exists (e.g., incremental mode on completed session)
            result = await db.execute(
                select(ProjectSession).where(ProjectSession.session_id == session_id)
            )
            existing_session = result.scalar_one_or_none()
            if existing_session:
                # Update existing session for incremental generation
                existing_session.status = "running"
                existing_session.requirement = request.requirement
                existing_session.error_message = None
                await db.commit()
                logger.info(f"增量模式：更新已有会话 {session_id}")
            else:
                await _create_project_session(db, int(user_id), session_id, request.requirement, output_dir)
        else:
            # 继续时更新已有 session 状态为 running
            try:
                result = await db.execute(
                    select(ProjectSession).where(ProjectSession.session_id == session_id)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.status = "running"
                    existing.requirement = request.requirement
                    await db.commit()
                else:
                    await _create_project_session(db, int(user_id), session_id, request.requirement, output_dir)
            except Exception:
                await db.rollback()
                await _create_project_session(db, int(user_id), session_id, request.requirement, output_dir)

    # 注册并发计数
    from app.utils.dynamic_concurrent import ConcurrentLimitManager
    concurrent_mgr = ConcurrentLimitManager()
    concurrent_mgr.register_session(user_role)

    queue: asyncio.Queue = asyncio.Queue()
    approval_queue: asyncio.Queue = asyncio.Queue()
    decision_queue: asyncio.Queue = asyncio.Queue()
    cancel_event = asyncio.Event()

    _approval_queues[session_id] = approval_queue
    _decision_queues[session_id] = decision_queue
    _cancel_events[session_id] = cancel_event

    async def approval_callback(file_path: str) -> bool:
        await queue.put(f"data: {json.dumps({'type': 'pause_for_approval', 'data': {'file_path': file_path, 'session_id': session_id}}, ensure_ascii=False)}\n\n")
        try:
            # 使用两个独立任务明确判断哪个先完成
            approval_task = asyncio.create_task(approval_queue.get())
            cancel_task = asyncio.create_task(cancel_event.wait())
            
            done, pending = await asyncio.wait(
                [approval_task, cancel_task],
                timeout=300,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
            
            # 检查是否因为取消而完成
            if cancel_event.is_set() or cancel_task in done:
                return False
            
            # 检查是否超时 - 超时视为拒绝，避免意外的 token 消耗
            if not done:
                logger.warning(f"审批超时: {file_path}，自动拒绝")
                return False
            
            # 获取审批结果
            result = approval_task.result()
            return result.get("approved", False) if isinstance(result, dict) else False
        except Exception as e:
            logger.error(f"审批回调异常: {file_path} - {e}")
            return False

    sm = await get_session_manager()
    cache = await get_spec_cache()
    learner = await get_feedback_learner()

    async def event_generator() -> AsyncIterator[str]:
        logger.info(f"[SSE] event_generator 开始 | session={session_id}")
        try:
            async def decision_callback(questions):
                """等待用户决策的回调"""
                await queue.put(f"data: {json.dumps({'type': 'critical_decisions', 'data': {'session_id': session_id, 'decisions': questions}}, ensure_ascii=False)}\n\n")
                decision_task = asyncio.create_task(decision_queue.get())
                cancel_task = asyncio.create_task(cancel_event.wait())
                pending = set()
                try:
                    done, pending = await asyncio.wait(
                        [decision_task, cancel_task],
                        timeout=120,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    if cancel_event.is_set():
                        return None
                    for task in done:
                        result = task.result()
                        if result is not None:
                            return result
                    return None
                finally:
                    for task in pending:
                        task.cancel()

            async def stream_callback(msg: str):
                try:
                    progress_data = json.loads(msg)
                    # 决策已通过 decision_callback 处理，不再重复等待
                    msg_type = progress_data.get("type", "")
                    if msg_type in PASSTHROUGH_SSE_EVENTS:
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
                provider_id=request.provider_id,
                cancel_event=cancel_event,
                decision_callback=decision_callback
            )

            async def run_generation():
                try:
                    logger.info(f"[SSE] 开始生成任务 | session={session_id}")
                    workflow = build_legacy_workflow(
                        "orchestrate_stream",
                        "/orchestrate/stream",
                        lambda _state: orchestrator.generate(
                            requirement=request.requirement + skill_context
                        ),
                    )
                    graph_state = await run_workflow(
                        workflow,
                        session_id=session_id,
                        task_id=session_id,
                        metadata={"output_dir": output_dir},
                    )
                    result = graph_state.metadata["legacy_result"]
                    # 检查是否在生成完成后被取消（stop_project 竞态保护）
                    if cancel_event.is_set():
                        logger.info(f"[SSE] 生成完成后检测到取消信号，跳过 complete_session | session={session_id}")
                        await queue.put(f"data: {json.dumps({'type': 'cancelled', 'data': {'message': '项目已停止'}}, ensure_ascii=False)}\n\n")
                        return
                    files_generated = result.get("total_files_created", 0)
                    files_total = result.get("total_files", 0)
                    logger.info(f"[SSE] 生成完成 | session={session_id} files={files_generated}/{files_total}")
                    await sm.complete_session(session_id, files_generated=files_generated, files_total=files_total)
                    await queue.put(f"data: {json.dumps({'type': 'done', 'data': result}, ensure_ascii=False)}\n\n")
                except Exception as e:
                    logger.error(f"[SSE] Orchestrator 流式生成失败: {e}", exc_info=True)
                    await sm.complete_session(session_id, errors=[str(e)])
                    await queue.put(f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n")
                finally:
                    await _cleanup_session_queues(session_id, cancel_event)
                    concurrent_mgr.unregister_session(user_role)
                    await queue.put("[DONE]")

            logger.info(f"[SSE] 创建生成任务 | session={session_id}")
            gen_task = asyncio.create_task(run_generation())

            # 存储活跃任务，支持浏览器重连
            _active_tasks[session_id] = {
                "gen_task": gen_task,
                "queue": queue,
                "cancel_event": cancel_event,
            }

            # 心跳 task：每 5 秒发送一次心跳，防止浏览器/proxy 断连
            async def heartbeat_sender():
                while not cancel_event.is_set():
                    await asyncio.sleep(5)
                    try:
                        await queue.put("data: {\"type\": \"heartbeat\"}\n\n")
                    except Exception:
                        break

            heartbeat_task = asyncio.create_task(heartbeat_sender())

            try:
                logger.info(f"[SSE] 开始等待队列消息 | session={session_id}")
                generation_completed = False
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=30.0)
                        logger.info(f"[SSE] 从队列获取消息 | session={session_id} type={item[:30] if len(item) > 30 else item}")
                        if item == "[DONE]":
                            generation_completed = True
                            break
                        yield item
                    except asyncio.TimeoutError:
                        # Check if generation task is still running
                        if gen_task.done():
                            logger.info(f"[SSE] 生成任务已完成 | session={session_id}")
                            generation_completed = True
                            break
                        continue
                logger.info(f"[SSE] 队列消息处理完成 | session={session_id}")
            except asyncio.CancelledError:
                logger.info(f"[SSE] 客户端断开连接，生成任务继续在后台运行 | session={session_id}")
            finally:
                heartbeat_task.cancel()
                # 不设置 cancel_event，不取消 gen_task
                # 生成任务在服务端独立运行，用户重新连接后可查看进度
                if not gen_task.done():
                    logger.info(f"[SSE] 生成任务仍在运行，转为后台模式 | session={session_id}")
                # 关键：判定"是否真正成功"必须看 gen_task 状态，而不是 generation_completed
                # generation_completed 可能在客户端断开的瞬间还没被置为 True
                # 但 gen_task 已完成且无异常 → 生成实际上已成功 → 不可标 cancelled
                gen_succeeded = (
                    not generation_completed
                    and gen_task.done()
                    and gen_task.exception() is None
                )
                if generation_completed or gen_succeeded:
                    logger.info(f"[SSE] 生成已成功完成 | session={session_id}")
                    # 清理活跃任务
                    _active_tasks.pop(session_id, None)
                else:
                    logger.info(f"[SSE] 生成未完成，任务继续在后台运行 | session={session_id}")
                    concurrent_mgr.unregister_session(user_role)
                    # 注册完成回调，任务结束后清理 _active_tasks
                    def _on_task_done(t):
                        _active_tasks.pop(session_id, None)
                        logger.info(f"[SSE] 后台任务完成，清理活跃任务 | session={session_id}")
                    gen_task.add_done_callback(_on_task_done)

        except asyncio.CancelledError:
            logger.info("[SSE] Orchestrator 流式响应被取消")
            await _cleanup_session_queues(session_id, cancel_event)
        except Exception as e:
            logger.error(f"[SSE] Orchestrator 流式生成器异常：{e}")
            await _cleanup_session_queues(session_id, cancel_event)
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


# ==================== 停止项目 ====================


@router.post("/stop/{session_id}")
async def stop_project(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    用户停止项目：取消运行中的生成任务 + 删除项目文件 + 释放资源
    
    用户已看到下载按钮和确认提示仍选择停止，说明已做好决定。
    后端应释放资源并删除文件，保护用户隐私。
    """
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    
    # 查找会话
    result = await db.execute(
        select(ProjectSession).where(
            ProjectSession.session_id == session_id,
            ProjectSession.user_id == int(user_id)
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if session.status != "running":
        raise HTTPException(status_code=400, detail=f"项目不在运行中，当前状态: {session.status}")
    
    # 1. 设置 cancel_event 通知生成任务停止
    cancel_ev = _cancel_events.get(session_id)
    if cancel_ev:
        cancel_ev.set()
    
    # 2. 清理活跃任务
    _active_tasks.pop(session_id, None)
    
    # 3. 删除项目文件（用户已确认停止，保护隐私）
    files_deleted = False
    if session.output_dir:
        files_deleted = cleanup_session_files(session.output_dir)
        logger.info(f"停止项目 - 清理文件: {session.output_dir} | 成功={files_deleted}")
    
    # 4. 更新 SessionManager 状态，释放内存
    sm = await get_session_manager()
    await sm.cancel_session(session_id)
    # 从内存中移除会话状态
    async with sm._lock:
        sm._active_sessions.pop(session_id, None)
    
    # 5. 更新 DB 状态
    session.status = "cancelled"
    session.error_message = "用户停止" if files_deleted else "用户停止（文件清理失败）"
    await db.commit()
    
    logger.info(f"用户停止项目 | user={user_id} session={session_id} files_deleted={files_deleted}")
    
    return {
        "message": "项目已停止，资源已释放",
        "session_id": session_id,
        "status": "cancelled",
        "files_deleted": files_deleted
    }


# ==================== 完成项目 ====================


@router.post("/complete/{session_id}")
async def complete_project(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    用户表示项目完成：清理文件 + 更新状态为 completed
    
    Args:
        session_id: 会话 ID
        token: 用户 token
        db: 数据库会话
    """
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    
    # 查找会话
    result = await db.execute(
        select(ProjectSession).where(
            ProjectSession.session_id == session_id,
            ProjectSession.user_id == int(user_id)
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if session.status != "running":
        raise HTTPException(status_code=400, detail=f"项目不在运行中，当前状态: {session.status}")
    
    # 清理文件
    if session.output_dir:
        cleanup_session_files(session.output_dir)
    
    # 更新状态
    session.status = "completed"
    session.completed_at = datetime.now()
    await db.commit()
    
    logger.info(f"用户完成项目 | user={user_id} session={session_id}")
    
    return {
        "message": "项目已完成",
        "session_id": session_id,
        "status": "completed"
    }


# ==================== 方案 3：Agent 工具 - 搜索历史会话 ====================


@router.post("/search_sessions", response_model=SearchSessionsResponse)
async def search_sessions(
    request: SearchSessionsRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    方案 3：Agent 工具 - 按语义搜索历史会话
    
    支持 agent 在多轮对话中查找对应的历史 session，
    适用于"修复上上轮的登录 bug"、"合并轮1的登录模块和轮3的支付模块"等场景。
    """
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    
    try:
        query = select(ProjectSession).where(
            ProjectSession.user_id == user_id
        )
        query = query.order_by(ProjectSession.created_at.desc()).limit(request.limit)
        
        result = await db.execute(query)
        sessions = list(result.scalars().all())
        
        # 让 LLM 评估每个 session 的相关性
        from app.utils import call_llm
        
        session_summaries = []
        for s in sessions:
            req_preview = s.requirement[:150] + ("..." if len(s.requirement) > 150 else "")
            session_summaries.append(
                f"- ID: {s.session_id}\n"
                f"  需求: {req_preview}\n"
                f"  状态: {s.status}"
            )
        
        summaries_text = "\n".join(session_summaries)
        
        prompt = f"""你是会话匹配助手。根据用户的搜索查询，为历史会话列表中的每个会话打分。

搜索查询："{request.query}"

历史会话列表（按时间倒序）：
{summaries_text}

请为每个会话返回一个匹配分数（0-1 之间，表示与该查询的相关性）。
严格使用以下 JSON 格式返回，不要其他文字：
{{"scores": {{"session_id_1": 0.9, "session_id_2": 0.3, ...}}}}"""

        scores = {}
        try:
            result_llm = await call_llm(
                model="Qwen/Qwen3-8B",
                prompt=prompt,
                temperature=0.1,
                max_tokens=1000
            )

            content = result_llm.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.info(f"LLM 评分原始输出: {content[:200]}...")

            # 尝试多种解析方式
            import re
            # 尝试 JSON 格式
            json_match = re.search(r'\{[^{}]*"scores"[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                scores_dict = data.get("scores", {})
                for sid, score in scores_dict.items():
                    scores[sid] = max(0, min(1, float(score)))
            else:
                # 尝试简单键值对格式
                for line in content.strip().split("\n"):
                    if ":" in line:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            session_id = parts[0].strip()
                            try:
                                score = float(parts[-1].strip())
                                scores[session_id] = max(0, min(1, score))
                            except ValueError:
                                pass
        except Exception as e:
            logger.warning(f"LLM 评分失败: {e}")
        
        # 构建结果
        matches = []
        for s in sessions:
            matches.append(SessionMatch(
                session_id=s.session_id,
                requirement_preview=s.requirement[:100] + "..." if len(s.requirement) > 100 else s.requirement,
                status=s.status,
                created_at=s.created_at.isoformat() if s.created_at else "",
                files_generated=s.files_generated,
                files_total=s.files_total,
                relevance_score=scores.get(s.session_id, 0.0)
            ))
        
        # 按相关性排序
        matches.sort(key=lambda m: m.relevance_score, reverse=True)
        
        return SearchSessionsResponse(
            query=request.query,
            matches=matches
        )
        
    except Exception as e:
        logger.error(f"搜索会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


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
    await _verify_session_ownership_or_queue(session_id, user_id, db)

    sm = await get_session_manager()

    if action == "cancel":
        # 设置 cancel_event 通知正在运行的生成任务停止
        cancel_ev = _cancel_events.get(session_id)
        if cancel_ev:
            cancel_ev.set()
        
        # 清理活跃任务
        _active_tasks.pop(session_id, None)
        
        # 删除项目文件（用户已确认取消，释放资源）
        result = await db.execute(
            select(ProjectSession).where(ProjectSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        files_deleted = False
        if session and session.output_dir:
            files_deleted = cleanup_session_files(session.output_dir)
            logger.info(f"取消会话 - 清理文件: {session.output_dir} | 成功={files_deleted}")
        
        await sm.cancel_session(session_id)
        
        # 从内存中移除会话状态
        async with sm._lock:
            sm._active_sessions.pop(session_id, None)
        
        # 更新 DB
        if session:
            session.status = "cancelled"
            session.error_message = "用户取消" if files_deleted else "用户取消（文件清理失败）"
            await db.commit()
        
        # 释放并发计数
        user_role = token.get("role", "user")
        from app.utils.dynamic_concurrent import ConcurrentLimitManager
        ConcurrentLimitManager().unregister_session(user_role)
        return {"status": "cancelled", "session_id": session_id, "files_deleted": files_deleted}
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
        await verify_session_ownership(db, session_id, user_id)


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
                ProjectSession.session_id == session_id,
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
