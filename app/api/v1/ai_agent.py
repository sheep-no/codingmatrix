"""
AI Agent API - 多模型 Agent 接口

提供统一的 Agent 调用接口，支持：
- 自动任务路由
- 多模型协作
- 文件契约验证
- AI 审查
- 流式输出
- ReAct 自我反思
- 记忆持久化
- Orchestrator 多角色协作
"""

import logging
import os
import shutil
import tempfile
import time
import zipfile
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Generator, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete, func, and_
from sqlalchemy.exc import SQLAlchemyError
from starlette.background import BackgroundTask

from app.utils.security import verify_token
from app.db.database import get_db
from app.services.agent_memory_service import AgentMemoryService
from app.agent import (
    MultiModelAgent,
    TaskType,
    ModelRegistry,
    FileContract,
    AIReviewer,
    AgentMemory,
    ReActAgent,
    ReActWithFallback,
    OrchestratorAgent,
    ProjectComplexity,
)
from app.schema.codeRequest import GenerateRequest, GenerateResponse, AgentConfig
from app.models.saved_project import SavedProject
from app.db.models import ProjectSession
from app.models.agent_memory import AgentSession, ToolExecutionLog, ModelUsageStats
from app.utils.agent_core import ProjectGeneratorAgent, ProjectFileManager
from app.utils.task_manager import task_manager
from app.schema.task_schema import TaskResponse, TaskStatusEnum
# Import database helper functions from AiProjectCode
from app.api.v1.AiProjectCode import create_agent_session, log_tool_execution, update_model_stats

# 依赖图谱与守护合约（P0）
from app.utils.guard_contracts import get_guard_contracts, get_applicable_rules, check_file_against_contracts

# Agent 认知 Skill（P2）
from app.utils.agent_skills import get_skills_manager, AgentSkillsManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["AI Agent"])

_agent_instance: Optional[MultiModelAgent] = None
_react_instance: Optional[ReActAgent] = None
_agent_lock = asyncio.Lock()


async def get_agent() -> MultiModelAgent:
    """获取 Agent 单例（线程安全）"""
    global _agent_instance
    if _agent_instance is None:
        async with _agent_lock:
            if _agent_instance is None:
                _agent_instance = MultiModelAgent(
                    default_model="deepseek-r1-qwen3-8b",
                    enable_review=True,
                    enable_file_contract=True
                )
    return _agent_instance


class AgentRequest(BaseModel):
    """Agent 请求"""
    task: str = Field(..., description="任务描述", min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    task_type: Optional[str] = Field(None, description="任务类型：general, code_generation, code_review, file_operation, visual, reasoning, fast_response")
    files: Optional[List[str]] = Field(None, description="附加文件列表", max_items=100)
    prefer_fast: bool = Field(False, description="是否优先快速模型")

    @validator('task')
    def validate_task(cls, v):
        if not v.strip():
            raise ValueError("任务描述不能为空")
        return v.strip()


class AgentResponse(BaseModel):
    """Agent 响应"""
    success: bool
    task_type: str
    model_used: str
    steps: int
    results: List[Any]
    issues: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None


class FileOperationRequest(BaseModel):
    """文件操作请求"""
    operation: str = Field(..., description="操作类型: read, write, delete, create")
    path: str = Field(..., description="文件路径", min_length=1, max_length=1000)
    content: Optional[str] = Field(None, description="文件内容（write时需要）")
    require_review: bool = Field(True, description="是否需要AI审查")

    @validator('operation')
    def validate_operation(cls, v):
        allowed = {"read", "write", "delete", "create"}
        if v not in allowed:
            raise ValueError(f"不支持的操作: {v}")
        return v

    @validator('path')
    def validate_path(cls, v):
        if ".." in v or v.startswith("/"):
            raise ValueError("路径格式不正确")
        return v


class FileContractRequest(BaseModel):
    """文件契约请求"""
    operation: str = Field(..., description="操作类型")
    path: str = Field(..., description="文件路径")
    content: Optional[str] = Field(None, description="文件内容")


class ModelListResponse(BaseModel):
    """模型列表响应"""
    models: List[Dict[str, Any]]


class ReviewRequest(BaseModel):
    """审查请求"""
    content: str = Field(..., description="待审查内容")
    content_type: str = Field(..., description="内容类型: code, plan, file")
    context: Optional[str] = Field(None, description="上下文")


class ReviewResponse(BaseModel):
    """审查响应"""
    approved: bool
    issues: List[str]
    suggestions: List[str]
    risk_level: str


class ReActRequest(BaseModel):
    """ReAct Agent 请求"""
    task: str = Field(..., description="任务描述", min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    enable_streaming: bool = Field(True, description="是否启用流式输出")
    max_iterations: int = Field(10, description="最大迭代次数", ge=1, le=50)
    use_fallback: bool = Field(True, description="失败时是否使用降级模型")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    session_type: str = Field("general", description="会话类型: general, react, code, visual")
    model_key: str = Field("deepseek-r1-qwen3-8b", description="模型键")


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    session_type: str
    model_key: str
    created_at: Optional[str] = None


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    session_id: str
    session_type: str
    model_key: str
    context_summary: Optional[str] = None
    total_steps: int
    total_tokens: int
    success: bool
    memory_entries: int
    reflections: int
    created_at: Optional[str] = None
    ended_at: Optional[str] = None


class KnowledgeRequest(BaseModel):
    """知识请求"""
    content: str = Field(..., description="知识内容", min_length=1)
    knowledge_key: Optional[str] = Field(None, description="知识关键词")
    category: str = Field("general", description="分类")
    importance: float = Field(0.5, description="重要性", ge=0.0, le=1.0)


class KnowledgeResponse(BaseModel):
    """知识响应"""
    id: str
    content: str
    knowledge_key: Optional[str]
    category: str
    importance: float
    usage_count: int
    created_at: Optional[str] = None


class ModelStatsResponse(BaseModel):
    """模型统计响应"""
    model_key: str
    model_name: Optional[str]
    request_count: int
    total_tokens: int
    success_count: int
    failure_count: int
    avg_execution_time: float
    last_used_at: Optional[str] = None


@router.post("/process", response_model=AgentResponse)
async def process_task(
    request: AgentRequest,
    token: dict = Depends(verify_token)
):
    """
    处理 AI 任务

    自动识别任务类型，选择最佳模型执行
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"Agent处理请求 | user={user_id} | task={request.task[:50]}...")

    try:
        task_type = None
        if request.task_type:
            try:
                task_type = TaskType(request.task_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的任务类型: {request.task_type}")

        agent = await get_agent()
        result = await agent.process(
            task=request.task,
            context=request.context,
            task_type=task_type,
            files=request.files
        )

        if not result.get("success"):
            return AgentResponse(
                success=False,
                task_type=result.get("task_type", "unknown"),
                model_used=result.get("model_used", "unknown"),
                steps=result.get("steps", 0),
                results=[],
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", [])
            )

        return AgentResponse(
            success=True,
            task_type=result.get("task_type"),
            model_used=result.get("model_used"),
            steps=result.get("steps"),
            results=result.get("results", [])
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/stream")
async def process_task_stream(
    request: AgentRequest,
    token: dict = Depends(verify_token)
):
    """
    处理 AI 任务（流式输出）

    返回 SSE 流式响应，实时推送任务进度
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"Agent 流式处理请求 | user={user_id} | task={request.task[:50]}...")

    queue: asyncio.Queue = asyncio.Queue()

    async def event_generator() -> AsyncIterator[str]:
        try:
            agent = await get_agent()

            async def stream_callback(event_type: str, data: Dict):
                event_data = {
                    "type": event_type,
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }
                await queue.put(f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n")

            # 创建后台任务执行 agent.process
            async def run_process():
                try:
                    result = await agent.process(
                        task=request.task,
                        context=request.context,
                        task_type=TaskType(request.task_type) if request.task_type else None,
                        files=request.files,
                        stream_callback=stream_callback
                    )
                    await queue.put(f"data: {json.dumps({'type': 'done', 'data': result}, ensure_ascii=False)}\n\n")
                except Exception as e:
                    logger.error(f"Agent 流式处理失败: {e}")
                    await queue.put(f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n")
                finally:
                    await queue.put("[DONE]")

            asyncio.create_task(run_process())

            while True:
                item = await queue.get()
                if item == "[DONE]":
                    break
                yield item

        except asyncio.CancelledError:
            logger.info("流式响应被取消")
        except Exception as e:
            logger.error(f"流式生成器异常: {e}")
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


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    token: dict = Depends(verify_token)
):
    """
    获取可用模型列表
    """
    models = []
    for info in ModelRegistry.list_all():
        models.append({
            "key": info.name.split("/")[-1].lower(),
            "name": info.display_name,
            "full_name": info.name,
            "capabilities": [c.value for c in info.capabilities],
            "max_tokens": info.max_tokens,
            "speed": info.speed
        })

    return {"models": models}


@router.post("/review", response_model=ReviewResponse)
async def review_content(
    request: ReviewRequest,
    token: dict = Depends(verify_token)
):
    """
    审查内容（代码/计划/文件）
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"审查请求 | user={user_id} | type={request.content_type}")

    reviewer = AIReviewer()

    if request.content_type == "code":
        result = await reviewer.review_code(request.content, request.context or "")
    elif request.content_type == "plan":
        try:
            plan = json.loads(request.content) if isinstance(request.content, str) else request.content
            result = await reviewer.review_plan(plan)
        except json.JSONDecodeError:
            result = await reviewer.review_plan([{"description": request.content}])
    else:
        result = await reviewer.review_file_operation(
            operation="read",
            file_path=request.context or "unknown",
            content=request.content
        )

    return ReviewResponse(
        approved=result.approved,
        issues=result.issues,
        suggestions=result.suggestions,
        risk_level=result.risk_level
    )


@router.post("/react/process")
async def react_process(
    request: ReActRequest,
    token: dict = Depends(verify_token)
):
    """
    使用 ReAct 模式处理任务（支持自我反思）

    ReAct 循环：Thought -> Action -> Observation -> Reflection
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"ReAct处理请求 | user={user_id} | task={request.task[:50]}...")

    try:
        if request.use_fallback:
            agent = ReActWithFallback()
        else:
            global _react_instance
            if _react_instance is None:
                async with _agent_lock:
                    if _react_instance is None:
                        _react_instance = ReActAgent(enable_streaming=request.enable_streaming)
            agent = _react_instance

        result = await agent.process(
            task=request.task,
            context=request.context
        )

        return {
            "success": result.success,
            "final_answer": result.final_answer,
            "total_steps": result.total_steps,
            "execution_time": result.execution_time,
            "reflection_summary": result.reflection_summary,
            "steps": [
                {
                    "type": s.step_type.value,
                    "content": s.content,
                    "tool": s.tool_name,
                    "success": s.success
                }
                for s in result.steps
            ]
        }

    except Exception as e:
        logger.error(f"ReAct处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/react/stream")
async def react_stream(
    request: ReActRequest,
    token: dict = Depends(verify_token)
):
    """
    使用 ReAct 模式处理任务（流式输出）

    返回 SSE 流式响应
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"ReAct流式请求 | user={user_id} | task={request.task[:50]}...")

    async def event_generator() -> AsyncIterator[str]:
        agent = ReActAgent(enable_streaming=True)

        async def stream_callback(text: str):
            yield f"data: {json.dumps({'type': 'stream', 'content': text}, ensure_ascii=False)}\n\n"

        agent.set_stream_callback(stream_callback)

        try:
            result = await agent.process(
                task=request.task,
                context=request.context
            )

            yield f"data: {json.dumps({'type': 'done', 'success': result.success, 'final_answer': result.final_answer}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"ReAct流式处理失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/memory/{session_id}")
async def get_memory(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    获取会话记忆上下文
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    context = await service.get_memory_context(session_id)

    return {"session_id": session_id, "context": context}


@router.post("/memory/clear")
async def clear_memory(
    session_id: str,
    clear_type: str = "session",
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    清除记忆

    clear_type: session (仅会话) / all (全部)
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)

    if clear_type == "session":
        await service.delete_session(session_id)
        message = f"会话 {session_id} 已删除"
    else:
        sessions = await service.get_user_sessions(user_id)
        for session in sessions:
            await service.delete_session(session.id)
        message = "所有会话已删除"

    return {"success": True, "message": message}


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    创建新会话
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    session = await service.create_session(
        user_id=user_id,
        session_type=request.session_type,
        model_key=request.model_key
    )

    return SessionResponse(
        session_id=session.id,
        session_type=session.session_type,
        model_key=session.model_key,
        created_at=session.created_at.isoformat() if session.created_at else None
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户会话列表
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    sessions = await service.get_user_sessions(user_id, limit=limit, offset=offset)

    return [
        SessionResponse(
            session_id=s.id,
            session_type=s.session_type,
            model_key=s.model_key,
            created_at=s.created_at.isoformat() if s.created_at else None
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    获取会话详情
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    summary = await service.get_session_summary(session_id)

    if not summary:
        raise HTTPException(status_code=404, detail="会话不存在")

    return SessionDetailResponse(**summary)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    删除会话
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    success = await service.delete_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "会话已删除"}


@router.post("/knowledge", response_model=KnowledgeResponse)
async def add_knowledge(
    request: KnowledgeRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    添加知识到知识库
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    knowledge = await service.add_knowledge(
        user_id=user_id,
        content=request.content,
        knowledge_key=request.knowledge_key,
        category=request.category,
        importance=request.importance
    )

    return KnowledgeResponse(
        id=knowledge.id,
        content=knowledge.content,
        knowledge_key=knowledge.knowledge_key,
        category=knowledge.category,
        importance=knowledge.importance,
        usage_count=knowledge.usage_count,
        created_at=knowledge.created_at.isoformat() if knowledge.created_at else None
    )


@router.get("/knowledge", response_model=List[KnowledgeResponse])
async def list_knowledge(
    category: str = Query(None, description="分类筛选"),
    limit: int = Query(50, ge=1, le=200),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户知识库
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    entries = await service.get_user_knowledge(user_id, category=category, limit=limit)

    return [
        KnowledgeResponse(
            id=e.id,
            content=e.content,
            knowledge_key=e.knowledge_key,
            category=e.category,
            importance=e.importance,
            usage_count=e.usage_count,
            created_at=e.created_at.isoformat() if e.created_at else None
        )
        for e in entries
    ]


@router.get("/knowledge/search", response_model=List[KnowledgeResponse])
async def search_knowledge(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    category: str = Query(None, description="分类筛选"),
    limit: int = Query(10, ge=1, le=50),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    搜索知识库
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    entries = await service.search_knowledge(user_id, q, category=category, limit=limit)

    return [
        KnowledgeResponse(
            id=e.id,
            content=e.content,
            knowledge_key=e.knowledge_key,
            category=e.category,
            importance=e.importance,
            usage_count=e.usage_count,
            created_at=e.created_at.isoformat() if e.created_at else None
        )
        for e in entries
    ]


@router.get("/stats/models", response_model=List[ModelStatsResponse])
async def get_model_stats(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    获取模型使用统计
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="未授权")

    service = AgentMemoryService(db)
    stats = await service.get_user_model_stats(user_id)

    return [
        ModelStatsResponse(
            model_key=s.model_key,
            model_name=s.model_name,
            request_count=s.request_count,
            total_tokens=s.total_tokens,
            success_count=s.success_count,
            failure_count=s.failure_count,
            avg_execution_time=s.avg_execution_time,
            last_used_at=s.last_used_at.isoformat() if s.last_used_at else None
        )
        for s in stats
    ]



# ========================================
# 项目生成 API 端点（从 AiProjectCode.py 迁移）
# ========================================

PROJECTS_BASE_DIR = "./projects"

ALLOWED_PACKAGES = [
    "fastapi", "pydantic", "httpx", "sqlalchemy",
    "click", "typer", "pytest", "aiofiles"
]

PROJECT_MIME_TYPES = {
    '.py': 'text/x-python',
    '.js': 'text/javascript',
    '.ts': 'text/typescript',
    '.jsx': 'text/javascript',
    '.tsx': 'text/typescript',
    '.vue': 'text/x-vue',
    '.html': 'text/html',
    '.css': 'text/css',
    '.scss': 'text/x-scss',
    '.sass': 'text/x-sass',
    '.less': 'text/x-less',
    '.md': 'text/markdown',
    '.markdown': 'text/markdown',
    '.json': 'application/json',
    '.yaml': 'application/x-yaml',
    '.yml': 'application/x-yaml',
    '.txt': 'text/plain',
    '.log': 'text/plain',
    '.sh': 'text/x-sh',
    '.bash': 'text/x-sh',
    '.env': 'text/plain',
    '.gitignore': 'text/plain',
    '.dockerfile': 'text/plain',
    '.toml': 'application/x-toml',
    '.xml': 'application/xml',
    '.sql': 'application/x-sql',
    '.graphql': 'application/graphql',
    '.mdx': 'text/mdx'
}

SKIP_DIRS = {'__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build', '.next', 'coverage'}

def _validate_project_path(project_path: str, user_id: str) -> Path:
    """
    验证项目路径安全性，返回resolved路径
    抛出 HTTPException 如果路径越界或不存在
    """
    base_dir = Path(PROJECTS_BASE_DIR).resolve()
    project_dir = (base_dir / project_path).resolve()

    if not str(project_dir).startswith(str(base_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {project_dir}")
        raise HTTPException(status_code=403, detail="无权访问该路径")

    if not project_dir.exists():
        logger.warning(f"项目不存在 | 路径: {project_dir}")
        raise HTTPException(status_code=404, detail="项目不存在")

    if not project_dir.is_dir():
        logger.warning(f"不是文件夹 | 路径: {project_dir}")
        raise HTTPException(status_code=400, detail="不是有效的项目文件夹")

    return project_dir

async def _collect_files(project_dir: Path) -> AsyncGenerator[dict, None]:
    """
    异步生成器：收集项目文件信息
    边扫描边 yield，避免大项目一次性加载到内存
    """
    try:
        for file_path in project_dir.rglob("*"):
            try:
                if any(part.startswith('.') or part in SKIP_DIRS for part in file_path.parts):
                    continue

                if not file_path.is_file():
                    continue

                rel_path = file_path.relative_to(project_dir)
                stat = file_path.stat()

                if file_path.name.startswith('.'):
                    continue

                suffix = file_path.suffix.lower()
                file_type = PROJECT_MIME_TYPES.get(suffix, 'text/plain')

                if stat.st_size > MAX_TEXT_FILE_SIZE:
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read(1024)
                except (UnicodeDecodeError, PermissionError, IOError):
                    continue

                yield {
                    'name': file_path.name,
                    'path': str(rel_path),
                    'type': file_type,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                logger.debug(f"读取文件失败 | 文件：{file_path} | 错误：{str(e)}")
                continue
    except Exception as e:
        logger.error(f"扫描目录失败 | 目录：{project_dir} | 错误：{str(e)}")

def _build_agent_config(req: GenerateRequest, stream: bool = False) -> AgentConfig:
    """
    统一创建 AgentConfig
    确保所有接口使用相同的默认配置
    """
    return AgentConfig(
        model=req.model,
        stream=stream,
        max_thinking_tokens=req.max_thinking_tokens,
        max_output_tokens=req.max_output_tokens,
        temperature=req.temperature,
        enable_validation=True,
        enable_venv_validation=req.enable_venv_validation,
        shared_base_venv="/opt/base_venv" if req.enable_venv_validation else None,
        auto_install_deps=False,
        allowed_packages=ALLOWED_PACKAGES
    )


# ==================== 依赖图谱与守护合约加载（P0） ====================

_dependency_graph_cache: Optional[Dict] = None
_guard_contracts_cache: Optional[Dict] = None


def load_dependency_graph() -> Optional[Dict]:
    """加载依赖图谱（缓存）"""
    global _dependency_graph_cache
    if _dependency_graph_cache is not None:
        return _dependency_graph_cache

    graph_path = Path(__file__).parent.parent.parent.parent / "dependency_graph.json"
    if graph_path.exists():
        try:
            _dependency_graph_cache = json.loads(graph_path.read_text(encoding='utf-8'))
            logger.info(f"依赖图谱已加载: {_dependency_graph_cache.get('file_count', 0)} 个文件, "
                       f"{_dependency_graph_cache.get('edge_count', 0)} 条边")
            return _dependency_graph_cache
        except Exception as e:
            logger.error(f"依赖图谱加载失败: {e}")
    else:
        logger.warning("依赖图谱文件不存在，请先运行: python scripts/build_dependency_graph.py")
    return None


def load_guard_contracts() -> Optional[Dict]:
    """加载守护合约规则（缓存）"""
    global _guard_contracts_cache
    if _guard_contracts_cache is not None:
        return _guard_contracts_cache

    try:
        contracts = get_guard_contracts()
        _guard_contracts_cache = contracts.to_dict()
        logger.info(f"守护合约已加载: {len(contracts.rules)} 条规则")
        return _guard_contracts_cache
    except Exception as e:
        logger.error(f"守护合约加载失败: {e}")
    return None


def get_agent_knowledge_base() -> Dict[str, Any]:
    """
    获取 Agent 知识库（会话初始化时调用）
    包含依赖图谱、守护合约和认知 Skill，让 Agent 具备完整的代码操作能力
    """
    knowledge = {
        "dependency_graph": load_dependency_graph(),
        "guard_contracts": load_guard_contracts(),
        "cognitive_skills": get_skills_manager().get_all_skills_context(),
    }
    return knowledge


async def _safe_update_progress(update_progress, **kwargs) -> bool:
    """
    带重试的进度更新
    最多重试3次，提高进度更新的可靠性
    """
    for attempt in range(3):
        try:
            await update_progress(**kwargs)
            return True
        except Exception as e:
            logger.warning(f"进度更新失败 (尝试 {attempt+1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
    return False

def _create_zip_archive_safe(source_dir: Path, zip_path: Path):
    """创建zip压缩包 - 简单版本"""
    try:
        # 直接用shutil.make_archive，它会自动创建zip
        shutil.make_archive(
            str(zip_path.with_suffix('')),  # 去掉.zip后缀
            'zip',
            source_dir
        )
        logger.info(f"压缩完成 | 文件夹: {source_dir.name} -> {zip_path.name}")
        return True
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"压缩失败 | 文件夹: {source_dir} | 错误: {str(e)}")
        return False


def _cleanup_temp_dir(temp_dir: str, project_name: str):
    """清理临时目录"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"清理完成 | 项目: {project_name} | 临时目录: {temp_dir}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.warning(f"清理失败 | 临时目录: {temp_dir} | 错误: {str(e)}")


@router.post("/generate", response_model=GenerateResponse)
async def generate_project(
        req: GenerateRequest,
        token: dict = Depends(verify_token)
):
    """
    非流式生成项目（仅返回最终结果，无日志输出）
    """
    # 从token中提取用户ID，生成时间戳
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"./projects/{timestamp}_{user_id}"

    agent_config = _build_agent_config(req)

    agent = ProjectGeneratorAgent(config=agent_config)

    # 空回调函数（不收集日志）
    def empty_callback(msg: str):
        """不执行任何操作的空白回调"""
        pass

    try:
        # 执行生成（使用空回调，不输出日志）
        result = await agent.generate_project(
            requirement=req.requirement,
            output_dir=output_dir,
            session_id=req.session_id,
            callback=empty_callback  # 使用空回调
        )

        # 只返回目录名，不暴露服务器路径
        project_name = Path(output_dir).name

        # 检查验证结果
        if not result["validation"]["runnable"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "项目生成完成但验证未通过",
                    "validation": result["validation"],
                    "output_dir": project_name
                }
            )

        # 成功返回（不包含日志）
        return GenerateResponse(
            success=True,
            output_dir=project_name,
            total_files_created=result["total_files_created"],
            steps=result["steps"],
            validation=result["validation"]
            # 不返回logs字段
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "项目生成失败",
                "error": str(e),
                "output_dir": Path(output_dir).name
            }
        )


# 流式接口（保持原样，用于实时进度展示）

@router.post("/generate_stream")
async def generate_project_stream(
        req: GenerateRequest,
        token: dict = Depends(verify_token)
):
    """
    流式生成项目（Server-Sent Events）
    实时推送所有进度信息
    """
    # 从token中提取用户ID，生成时间戳
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"./projects/{timestamp}_{user_id}"

    agent_config = _build_agent_config(req, stream=True)

    agent = ProjectGeneratorAgent(config=agent_config)

    async def event_generator():
        # 创建异步队列
        queue = asyncio.Queue()

        # 回调函数：处理结构化进度数据
        def progress_callback(msg: str):
            try:
                # 解析JSON进度数据
                progress_data = json.loads(msg)
                # 将整个进度数据推入队列
                queue.put_nowait(json.dumps(progress_data, ensure_ascii=False))
            except json.JSONDecodeError:
                # 如果不是JSON，按原样处理（兼容旧格式）
                queue.put_nowait(json.dumps({
                    'type': 'log',
                    'message': msg,
                }, ensure_ascii=False))

        # 后台任务：执行生成
        async def run_generation():
            try:
                result = await agent.generate_project(
                    requirement=req.requirement,
                    output_dir=output_dir,
                    session_id=req.session_id,
                    callback=progress_callback  # 使用进度回调
                )

                # 发送最终结果（只返回目录名，不暴露服务器路径）
                await queue.put(json.dumps({
                    'type': 'complete',
                    'result': {
                        'success': result['success'],
                        'output_dir': Path(result['output_dir']).name,
                        'total_files_created': result['total_files_created'],
                        'validation': result['validation']
                    }
                }, ensure_ascii=False))

            except HTTPException as e:
                await queue.put(json.dumps({
                    'type': 'error',
                    'message': str(e.detail),
                    'status_code': e.status_code
                }, ensure_ascii=False))
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                await queue.put(json.dumps({
                    'type': 'error',
                    'message': str(e),
                }, ensure_ascii=False))
            finally:
                await queue.put("[DONE]")
        asyncio.create_task(run_generation())
        while True:
            item = await queue.get()
            if item == "[DONE]":
                yield "data: [DONE]\n\n"
                break
            yield f"data: {item}\n\n"

    # 返回SSE响应
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/generate/download/{project_path:path}")
async def download_project(
        project_path: str,
        token: dict = Depends(verify_token)
):
    """
    下载项目目录
    - project_path: 项目文件夹路径，直接使用原文件夹名
    """
    # 获取用户信息
    user_id = token.get("sub", "anonymous")

    # 记录开始
    logger.info(f"下载请求 | 用户: {user_id} | 项目: {project_path}")
    start_time = time.time()

    # 路径验证
    project_dir = _validate_project_path(project_path, user_id)

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()

    # 直接用原文件夹名作为zip文件名
    zip_filename = f"{project_dir.name}.zip"
    zip_filepath = Path(temp_dir) / zip_filename

    logger.info(f"开始压缩 | 文件夹: {project_dir.name} | 目标: {zip_filename}")

    # 创建zip文件
    success = await asyncio.to_thread(_create_zip_archive_safe, project_dir, zip_filepath)

    if not success or not zip_filepath.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="创建压缩包失败")

    # 记录完成
    zip_size = zip_filepath.stat().st_size
    elapsed = time.time() - start_time
    logger.info(f"下载准备就绪 | 项目: {project_dir.name} | 大小: {zip_size / 1024:.1f}KB | 耗时: {elapsed:.2f}s")

    # 返回文件 - 使用原文件夹名
    return FileResponse(
        path=str(zip_filepath),
        filename=zip_filename,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        },
        background=BackgroundTask(
            lambda: _cleanup_temp_dir(temp_dir, project_dir.name)
        )
    )


@router.post("/generate_task", response_model=TaskResponse)
async def generate_project_task(
    req: GenerateRequest,
    token: dict = Depends(verify_token)
):
    """
    使用任务队列生成项目（适合长时间运行的任务）
    - 立即返回 task_id
    - 通过 /task/{task_id} 查询进度
    - 支持后台异步执行
    """
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"./projects/{timestamp}_{user_id}"

    agent_config = _build_agent_config(req)

    async def run_generation(task_id: str, update_progress):
        """异步执行项目生成任务"""
        agent = ProjectGeneratorAgent(config=agent_config)

        def progress_callback(msg: str):
            """进度回调，使用 _safe_update_progress 确保可靠性"""
            try:
                progress_data = json.loads(msg)
                if 'progress' in progress_data:
                    asyncio.create_task(_safe_update_progress(
                        update_progress,
                        progress=progress_data['progress'],
                        message=progress_data.get('message', msg)
                    ))
                else:
                    asyncio.create_task(_safe_update_progress(
                        update_progress,
                        message=msg
                    ))
            except json.JSONDecodeError:
                asyncio.create_task(_safe_update_progress(
                    update_progress,
                    message=msg
                ))
        
        try:
            result = await agent.generate_project(
                requirement=req.requirement,
                output_dir=output_dir,
                session_id=req.session_id,
                callback=progress_callback
            )
            
            await update_progress(
                progress=100,
                message="项目生成完成",
                status="completed",
                result_data=json.dumps({
                    "success": result["success"],
                    "output_dir": Path(result["output_dir"]).name,
                    "total_files_created": result["total_files_created"],
                    "validation": result["validation"]
                })
            )
            
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            await update_progress(
                status="failed",
                message=f"生成失败：{str(e)}",
                error_message=str(e)
            )
            logger.error(f"项目生成任务失败 | task_id: {task_id} | error: {str(e)}")
    
    task_response = await task_manager.create_task(
        task_type="project_generation",
        user_id=user_id,
        run_task=run_generation,
        metadata={
            "requirement": req.requirement[:100],
            "model": req.model,
            "output_dir": Path(output_dir).name
        }
    )
    
    logger.info(f"创建项目生成任务 | task_id: {task_response.task_id} | user: {user_id}")
    return task_response

@router.get("/generate/status/{task_id}")
async def get_generation_status(
    task_id: str,
    token: dict = Depends(verify_token)
):
    """
    查询项目生成任务状态
    """
    task_info = await task_manager.get_task_info_async(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task_info["task_id"],
        "status": task_info["status"],
        "progress": task_info["progress"],
        "progress_message": task_info["progress_message"],
        "result": task_info.get("result"),
        "error_message": task_info.get("error_message"),
        "created_at": task_info.get("created_at"),
        "started_at": task_info.get("started_at"),
        "completed_at": task_info.get("completed_at"),
    }

@router.get("/generate/files")
async def get_project_files(
    project_path: str,
    token: dict = Depends(verify_token)
):
    """
    获取项目文件列表（用于预览）
    - project_path: 项目文件夹路径
    """
    user_id = token.get("sub", "anonymous")
    start_time = time.time()
    logger.info(f"获取项目文件列表 | 用户：{user_id} | 项目：{project_path}")
    
    project_dir = _validate_project_path(project_path, user_id)

    files = []
    skipped_dirs = 0
    skipped_files = 0

    async for file_info in _collect_files(project_dir):
        files.append(file_info)
    
    # 智能排序：README 和入口文件优先，然后按路径和文件名
    priority_files = ['README.md', 'index.html', 'main.py', 'package.json', 'requirements.txt']
    
    def sort_key(file):
        path = file['path']
        name = file['name']
        # 优先级文件排在前面
        for i, priority in enumerate(priority_files):
            if path == priority or name == priority:
                return (0, i, path, name)
        # 其他文件按路径和名称排序
        return (1, 0, path, name)
    
    files.sort(key=sort_key)
    
    elapsed = time.time() - start_time
    logger.info(f"返回文件列表 | 文件数：{len(files)} | 跳过目录：{skipped_dirs} | 跳过文件：{skipped_files} | 耗时：{elapsed:.3f}s")
    
    return {
        'project': project_path,
        'total': len(files),
        'skipped_dirs': skipped_dirs,
        'skipped_files': skipped_files,
        'files': files
    }

@router.get("/generate/read")
async def read_project_file(
    project_path: str,
    file_path: str,
    token: dict = Depends(verify_token)
):
    """
    读取项目指定文件内容
    - project_path: 项目文件夹路径
    - file_path: 文件路径（相对于项目根目录）
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"读取项目文件 | 用户：{user_id} | 项目：{project_path} | 文件：{file_path}")

    project_dir = _validate_project_path(project_path, user_id)

    target_file = (project_dir / file_path).resolve()

    if not str(target_file).startswith(str(project_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {target_file}")
        raise HTTPException(status_code=403, detail="无权访问该文件")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="不是有效的文件")

    suffix = target_file.suffix.lower()
    mime_type = PROJECT_MIME_TYPES.get(suffix, 'text/plain')

    try:
        content = target_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = "[二进制文件，无法显示]"
    except Exception as e:
        logger.error(f"读取文件失败 | 文件：{target_file} | 错误：{str(e)}")
        raise HTTPException(status_code=500, detail=f"读取文件失败：{str(e)}")

    stat = target_file.stat()

    return {
        'project': project_path,
        'file_path': file_path,
        'name': target_file.name,
        'mime_type': mime_type,
        'size': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'content': content
    }

@router.delete("/generate/file")
async def delete_project_file(
    project_path: str,
    file_path: str,
    token: dict = Depends(verify_token)
):
    """
    删除项目指定文件
    - project_path: 项目文件夹路径
    - file_path: 文件路径（相对于项目根目录）
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"删除项目文件 | 用户：{user_id} | 项目：{project_path} | 文件：{file_path}")

    project_dir = _validate_project_path(project_path, user_id)

    target_file = (project_dir / file_path).resolve()

    if not str(target_file).startswith(str(project_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {target_file}")
        raise HTTPException(status_code=403, detail="无权访问该文件")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="不是有效的文件")

    try:
        target_file.unlink()
        logger.info(f"文件已删除 | 文件：{target_file}")
        return {'status': 'deleted', 'file_path': file_path}
    except Exception as e:
        logger.error(f"删除文件失败 | 文件：{target_file} | 错误：{str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件失败：{str(e)}")


MAX_SAVED_PROJECTS_PER_USER = 3


class SaveProjectRequest(BaseModel):
    name: str = Field(..., max_length=200, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    project_data: str = Field(..., description="项目数据(JSON字符串)")


class SaveProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    message: str


class ProjectListResponse(BaseModel):
    projects: list
    total: int
    max_allowed: int


class LoadProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    project_data: str
    created_at: datetime
    updated_at: Optional[datetime]

@router.post("/save", response_model=SaveProjectResponse)
async def save_project(
    request: SaveProjectRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    保存项目（每个用户最多保存3个项目）

    - **name**: 项目名称（必填，最多200字符）
    - **description**: 项目描述（可选）
    - **project_data**: 项目数据（JSON字符串）
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    logger.info(f"保存项目 | user_id={user_id} | name={request.name}")

    try:
        count_result = await db.execute(
            select(func.count()).select_from(SavedProject).where(
                SavedProject.user_id == user_id
            )
        )
        current_count = count_result.scalar() or 0

        if current_count >= MAX_SAVED_PROJECTS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"已达到保存项目上限（{MAX_SAVED_PROJECTS_PER_USER}个）。请先删除不需要的项目后再保存。"
            )

        saved_project = SavedProject(
            user_id=user_id,
            name=request.name,
            description=request.description,
            project_data=request.project_data
        )
        db.add(saved_project)
        await db.commit()
        await db.refresh(saved_project)

        logger.info(f"项目保存成功 | user_id={user_id} | project_id={saved_project.id}")

        return SaveProjectResponse(
            id=saved_project.id,
            name=saved_project.name,
            description=saved_project.description,
            created_at=saved_project.created_at,
            message="项目保存成功"
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"保存项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="保存项目失败")

@router.get("/saved", response_model=ProjectListResponse)
async def list_saved_projects(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户保存的项目列表"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        result = await db.execute(
            select(SavedProject)
            .where(SavedProject.user_id == user_id)
            .order_by(SavedProject.updated_at.desc())
        )
        projects = result.scalars().all()

        project_list = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            }
            for p in projects
        ]

        logger.info(f"获取保存项目列表 | user_id={user_id} | count={len(project_list)}")

        return ProjectListResponse(
            projects=project_list,
            total=len(project_list),
            max_allowed=MAX_SAVED_PROJECTS_PER_USER
        )

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"获取项目列表异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取项目列表失败")

@router.get("/saved/{project_id}", response_model=LoadProjectResponse)
async def load_saved_project(
    project_id: int,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """加载指定保存的项目"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        result = await db.execute(
            select(SavedProject).where(
                and_(
                    SavedProject.id == project_id,
                    SavedProject.user_id == user_id
                )
            )
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        logger.info(f"加载保存项目 | user_id={user_id} | project_id={project_id}")

        return LoadProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            project_data=project.project_data,
            created_at=project.created_at,
            updated_at=project.updated_at
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"加载项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="加载项目失败")

@router.delete("/saved/{project_id}")
async def delete_saved_project(
    project_id: int,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除指定保存的项目"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        result = await db.execute(
            delete(SavedProject).where(
                and_(
                    SavedProject.id == project_id,
                    SavedProject.user_id == user_id
                )
            )
        )
        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目不存在")

        logger.info(f"删除保存项目 | user_id={user_id} | project_id={project_id}")

        return {"status": "deleted", "project_id": project_id}

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"删除项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除项目失败")


# ========================================
# Orchestrator Agent - 多角色协作项目生成
# ========================================


class OrchestratorRequest(BaseModel):
    """Orchestrator Agent 请求"""
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=5000)
    output_dir: Optional[str] = Field(None, description="输出目录")
    enable_review: bool = Field(True, description="是否启用代码审查")
    enable_validation: bool = Field(True, description="是否启用代码验证")
    enable_error_recovery: bool = Field(True, description="是否启用错误恢复")
    enable_memory: bool = Field(True, description="是否启用记忆系统")
    # 增量生成
    session_id: Optional[str] = Field(None, description="会话ID（用于增量生成/续传）")
    incremental: bool = Field(False, description="是否启用增量生成")
    # 人机协作
    require_approval: bool = Field(False, description="是否要求关键文件人工审批")


class SessionActionRequest(BaseModel):
    """会话操作请求"""
    action: str = Field(..., description="操作类型: resume, cancel, approve, reject")
    approved: bool = Field(True, description="是否批准（用于 approve/reject 操作）")


class OrchestratorResponse(BaseModel):
    """Orchestrator Agent 响应"""
    success: bool
    output_dir: str
    total_files_created: int
    complexity: str
    models_used: Dict[str, str]
    files: List[Dict[str, Any]]
    validation: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    elapsed_time: float
    fix_attempts: List[Dict[str, Any]]


@router.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate_project(
    request: OrchestratorRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    使用 Orchestrator Agent 生成项目

    多角色协作架构：
    - 架构师：负责技术选型和整体架构设计
    - 前端工程师：专注前端代码生成
    - 后端工程师：专注后端代码生成
    - 审查员：负责代码质量和安全审查
    - 验证器：语法、依赖、运行时验证
    - 错误恢复：自动修复循环

    模型分配策略：
    - 简单项目：Qwen 系列（快速响应）
    - 中小项目：GLM-Z1 (架构) + Qwen3.5-4B (前端) + DeepSeek-R1 (后端)
    - 大型项目：GLM-Z1 (架构) + Qwen3.5-4B (前端) + DeepSeek-R1 (后端/审查)
    """
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = request.output_dir or f"./projects/orchestrator/{timestamp}_{user_id}"

    logger.info(f"Orchestrator 生成请求 | user={user_id} | requirement={request.requirement[:50]}...")

    # 验证 user_id 格式
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 创建会话记录
    session = await create_agent_session(
        db, int(user_id), "orchestrator", request.requirement
    )
    session_id = session.id if session else None

    start_time = time.time()

    try:
        # 创建 Orchestrator Agent
        orchestrator = OrchestratorAgent(
            output_dir=output_dir,
            enable_review=request.enable_review,
            enable_validation=request.enable_validation,
            enable_error_recovery=request.enable_error_recovery,
            memory_enabled=request.enable_memory,
            callback=lambda msg: logger.info(f"Orchestrator 进度: {msg[:200]}")
        )

        # 执行生成
        result = await orchestrator.generate(requirement=request.requirement)

        # 记录工具执行
        execution_time = time.time() - start_time
        await log_tool_execution(
            db, session_id, "orchestrator_generate",
            {"requirement": request.requirement, "output_dir": output_dir},
            json.dumps(result, ensure_ascii=False)[:5000] if result else None,
            success=result.get("success", False),
            execution_time=execution_time
        )

        # 更新模型统计
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
    """
    使用 Orchestrator Agent 生成项目（流式输出）

    每用户仅允许一个活跃会话。新会话会清理旧会话的资源（项目文件、会话状态、历史记录）。
    """
    user_id = token.get("sub", "anonymous")

    # 验证 user_id 格式
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")

    # 每用户仅允许一个会话：清理旧会话资源
    await _cleanup_old_session(user_id, db)

    # 生成新的 session_id（不允许用户指定）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"project_{user_id}_{timestamp}"
    output_dir = request.output_dir or f"./projects/orchestrator/{timestamp}_{user_id}"

    logger.info(f"Orchestrator 流式生成请求 | user={user_id} session={session_id}")

    # 创建项目会话记录
    await _create_project_session(db, int(user_id), session_id, request.requirement, output_dir)

    queue: asyncio.Queue = asyncio.Queue()
    approval_queue: asyncio.Queue = asyncio.Queue()
    cancel_event = asyncio.Event()  # 用于在 SSE 断开时取消后台任务

    # 注册审批队列到全局（供 session action 端点使用）
    _approval_queues[session_id] = approval_queue

    # 审批回调
    async def approval_callback(file_path: str) -> bool:
        await queue.put(f"data: {json.dumps({'type': 'pause_for_approval', 'data': {'file_path': file_path, 'session_id': session_id}}, ensure_ascii=False)}\n\n")
        # 等待用户响应（带超时 5 分钟），如果客户端断开则立即返回
        try:
            result = await asyncio.wait_for(
                asyncio.gather(approval_queue.get(), cancel_event.wait(), return_when=asyncio.FIRST_COMPLETED),
                timeout=300
            )
            if cancel_event.is_set():
                return False  # 客户端断开，拒绝
            return result[0].get("approved", True) if isinstance(result, tuple) else result.get("approved", True)
        except asyncio.TimeoutError:
            logger.warning(f"审批超时: {file_path}，自动批准")
            return True

    # 懒加载全局单例
    sm = await get_session_manager()
    cache = await get_spec_cache()
    learner = await get_feedback_learner()

    async def event_generator() -> AsyncIterator[str]:
        try:
            async def stream_callback(msg: str):
                try:
                    progress_data = json.loads(msg)
                    await queue.put(f"data: {json.dumps({'type': 'progress', 'data': progress_data}, ensure_ascii=False)}\n\n")
                except json.JSONDecodeError:
                    await queue.put(f"data: {json.dumps({'type': 'log', 'data': {'message': msg}}, ensure_ascii=False)}\n\n")

            orchestrator = OrchestratorAgent(
                output_dir=output_dir,
                enable_review=request.enable_review,
                enable_validation=request.enable_validation,
                enable_error_recovery=request.enable_error_recovery,
                memory_enabled=request.enable_memory,
                callback=stream_callback,
                # 增量生成
                session_manager=sm,
                session_id=session_id,
                incremental=False,
                # 缓存
                spec_cache=cache,
                # 人机协作
                require_approval=request.require_approval,
                approval_callback=approval_callback if request.require_approval else None,
                # 反馈学习
                feedback_learner=learner
            )

            async def run_generation():
                try:
                    result = await orchestrator.generate(requirement=request.requirement)
                    files_generated = result.get("total_files_created", 0)
                    files_total = result.get("total_files", 0)
                    await _update_project_session_status(db, session_id, "completed", files_generated, files_total)
                    await queue.put(f"data: {json.dumps({'type': 'done', 'data': result}, ensure_ascii=False)}\n\n")
                except Exception as e:
                    logger.error(f"Orchestrator 流式生成失败: {e}")
                    await _update_project_session_status(db, session_id, "failed", error_message=str(e))
                    await queue.put(f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n")
                finally:
                    # 清理审批队列
                    if session_id in _approval_queues:
                        del _approval_queues[session_id]
                    await queue.put("[DONE]")

            gen_task = asyncio.create_task(run_generation())

            try:
                while True:
                    item = await queue.get()
                    if item == "[DONE]":
                        break
                    yield item
            except asyncio.CancelledError:
                # SSE 断开：取消后台生成任务
                logger.info(f"客户端断开连接，取消生成任务 | session={session_id}")
                cancel_event.set()
                gen_task.cancel()
                try:
                    await asyncio.wait_for(gen_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            finally:
                # 始终清理资源
                if not gen_task.done():
                    cancel_event.set()
                    gen_task.cancel()
                    try:
                        await asyncio.wait_for(gen_task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                if session_id in _approval_queues:
                    del _approval_queues[session_id]
                await sm.cancel_session(session_id)
                await _update_project_session_status(db, session_id, "cancelled")

        except asyncio.CancelledError:
            logger.info("Orchestrator 流式响应被取消")
        except Exception as e:
            logger.error(f"Orchestrator 流式生成器异常: {e}")
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


class ComplexityAnalysisRequest(BaseModel):
    """复杂度分析请求"""
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=5000)


class ComplexityAnalysisResponse(BaseModel):
    """复杂度分析响应"""
    level: str
    estimated_files: int
    has_frontend: bool
    has_backend: bool
    has_database: bool
    key_technologies: List[str]
    risk_factors: List[str]
    model_assignment: Dict[str, str]


@router.post("/analyze_complexity", response_model=ComplexityAnalysisResponse)
async def analyze_project_complexity(
    request: ComplexityAnalysisRequest,
    token: dict = Depends(verify_token)
):
    """
    分析项目复杂度并推荐模型分配方案

    返回：
    - 复杂度等级 (simple/small/medium/large/enterprise)
    - 预估文件数
    - 技术栈识别
    - 风险因素
    - 推荐的模型分配方案
    """
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


# ========================================
# 会话管理端点
# ========================================

_session_manager = None
_session_manager_lock = asyncio.Lock()
_approval_queues: Dict[str, asyncio.Queue] = {}


async def _cleanup_old_session(user_id: str, db: AsyncSession):
    """清理用户旧的项目会话资源（数据库记录 + 会话文件 + 输出目录）

    根据 MAX_PROJECT_SESSIONS_PER_USER 配置决定保留多少个活跃会话。
    默认 1（单会话模式），后期管理员可通过环境变量调整。
    """
    import shutil
    from app.core.config import settings

    max_sessions = settings.MAX_PROJECT_SESSIONS_PER_USER

    # 查询当前活跃会话数量
    result = await db.execute(
        select(ProjectSession).where(
            ProjectSession.user_id == str(user_id),
            ProjectSession.status.in_(["running", "completed", "failed"])
        ).order_by(ProjectSession.created_at.desc())
    )
    all_sessions = result.scalars().all()

    # 如果未超过限制，无需清理
    if len(all_sessions) <= max_sessions:
        return

    # 保留最新的 max_sessions 个，清理其余的
    sessions_to_keep = set(s.session_id for s in all_sessions[:max_sessions])
    sessions_to_cleanup = [s for s in all_sessions if s.session_id not in sessions_to_keep]

    for old_sess in sessions_to_cleanup:
        # 1. 清理会话文件（session_manager 存储的 JSON）
        sm = await get_session_manager()
        session_file = sm._session_file(old_sess.session_id)
        if session_file.exists():
            try:
                session_file.unlink()
                logger.info(f"已删除旧会话文件: {session_file}")
            except OSError as e:
                logger.warning(f"删除会话文件失败: {e}")

        # 2. 清理输出目录（项目文件）
        if old_sess.output_dir:
            output_path = Path(old_sess.output_dir)
            if output_path.exists():
                try:
                    shutil.rmtree(output_path)
                    logger.info(f"已删除旧项目目录: {output_path}")
                except OSError as e:
                    logger.warning(f"删除项目目录失败: {e}")

        # 3. 清理 AI 对话历史记录（History 表中关联该 session 的记录）
        from app.models.history import History
        await db.execute(
            sql_delete(History).where(
                History.user_id == user_id,
                History.metadata_json.contains(f'"session_id": "{old_sess.session_id}"')
            )
        )

        # 4. 更新数据库状态
        old_sess.status = "cancelled"
        old_sess.completed_at = datetime.now()

    await db.commit()

    if sessions_to_cleanup:
        logger.info(f"已清理用户 {user_id} 的 {len(sessions_to_cleanup)} 个旧会话资源（保留最新 {max_sessions} 个）")


async def _create_project_session(db: AsyncSession, user_id: int, session_id: str, requirement: str, output_dir: str):
    """创建新的项目会话记录"""
    session = ProjectSession(
        session_id=session_id,
        user_id=str(user_id),
        requirement=requirement,
        output_dir=output_dir,
        status="running"
    )
    db.add(session)
    await db.commit()
    return session


async def _update_project_session_status(db: AsyncSession, session_id: str, status: str, files_generated: int = 0, files_total: int = 0, error_message: str = None):
    """更新项目会话状态"""
    result = await db.execute(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.status = status
        session.files_generated = files_generated
        session.files_total = files_total
        if error_message:
            session.error_message = error_message
        if status in ("completed", "failed", "cancelled"):
            session.completed_at = datetime.now()
        await db.commit()

async def get_session_manager():
    global _session_manager
    if _session_manager is None:
        async with _session_manager_lock:
            if _session_manager is None:
                from app.agent.session_manager import SessionManager
                _session_manager = SessionManager()
    return _session_manager


@router.get("/session/{session_id}")
async def get_session_status_endpoint(session_id: str, token: dict = Depends(verify_token)):
    """获取会话状态"""
    sm = await get_session_manager()
    status = await sm.get_session_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="会话不存在")
    return status


@router.get("/project/session")
async def get_current_project_session(token: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取当前用户的项目会话状态"""
    user_id = token.get("sub", "anonymous")
    if not user_id or user_id == "anonymous" or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份")

    result = await db.execute(
        select(ProjectSession)
        .where(
            ProjectSession.user_id == str(user_id),
            ProjectSession.status == "running"
        )
        .order_by(ProjectSession.created_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        return {"has_active_session": False}

    sm = await get_session_manager()
    session_status = await sm.get_session_status(session.session_id)

    return {
        "has_active_session": True,
        "session_id": session.session_id,
        "requirement": session.requirement,
        "status": session.status,
        "files_generated": session.files_generated,
        "files_total": session.files_total,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "details": session_status
    }


@router.post("/session/{session_id}/action")
async def session_action_endpoint(
    session_id: str,
    action: SessionActionRequest,
    token: dict = Depends(verify_token)
):
    """会话操作（恢复、取消、批准、拒绝）"""
    sm = await get_session_manager()

    if action.action == "cancel":
        await sm.cancel_session(session_id)
        return {"status": "cancelled", "session_id": session_id}
    elif action.action == "resume":
        await sm.resume_from_pause(session_id, approved=True)
        return {"status": "resumed", "session_id": session_id}
    elif action.action in ("approve", "reject"):
        # 发送审批结果到等待中的队列
        approved = action.action == "approve"
        q = _approval_queues.get(session_id)
        if q:
            await q.put({"approved": approved})
        await sm.resume_from_pause(session_id, approved=approved)
        return {"status": action.action, "session_id": session_id}
    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action.action}")


# ========================================
# 缓存管理端点
# ========================================

_spec_cache = None
_spec_cache_lock = asyncio.Lock()

async def get_spec_cache():
    global _spec_cache
    if _spec_cache is None:
        async with _spec_cache_lock:
            if _spec_cache is None:
                from app.agent.spec_cache import SpecCache
                _spec_cache = SpecCache()
    return _spec_cache


@router.get("/cache/stats")
async def get_cache_stats(token: dict = Depends(verify_token)):
    """获取缓存统计"""
    cache = await get_spec_cache()
    return cache.get_stats()


@router.post("/cache/clear")
async def clear_cache(mode: str = "expired", token: dict = Depends(verify_token)):
    """清理缓存

    - mode=expired: 仅清理过期缓存（默认 7 天）
    - mode=all: 清理所有缓存
    """
    cache = await get_spec_cache()
    if mode == "all":
        cleared = cache.clear_all()
    else:
        cleared = cache.clear_expired()
    return {"cleared_count": cleared, "mode": mode}


# ========================================
# 反馈学习端点
# ========================================

_feedback_learner = None
_feedback_learner_lock = asyncio.Lock()

async def get_feedback_learner():
    global _feedback_learner
    if _feedback_learner is None:
        async with _feedback_learner_lock:
            if _feedback_learner is None:
                from app.agent.feedback_learner import FeedbackLearner
                _feedback_learner = FeedbackLearner()
    return _feedback_learner


@router.get("/learning/stats")
async def get_learning_stats(token: dict = Depends(verify_token)):
    """获取学习统计"""
    learner = await get_feedback_learner()
    return learner.get_learning_stats()


@router.get("/learning/common-errors/{file_type}")
async def get_common_errors(file_type: str, token: dict = Depends(verify_token)):
    """获取常见错误"""
    learner = await get_feedback_learner()
    return {"errors": learner.get_common_errors(file_type)}


# ========================================
# 管理员配置端点（后期可扩展为完整的管理员面板）
# ========================================

class ProjectSessionConfigRequest(BaseModel):
    """项目会话配置请求"""
    max_sessions_per_user: int = Field(..., ge=1, le=100, description="每用户最大活跃项目会话数")


@router.get("/admin/project-session/config")
async def get_project_session_config(token: dict = Depends(verify_token)):
    """获取项目会话配置（管理员）"""
    from app.core.config import settings
    return {
        "max_sessions_per_user": settings.MAX_PROJECT_SESSIONS_PER_USER,
        "description": "每用户最大活跃项目会话数（1=单会话模式，>1=多会话模式）"
    }


@router.post("/admin/project-session/config")
async def update_project_session_config(
    request: ProjectSessionConfigRequest,
    token: dict = Depends(verify_token)
):
    """更新项目会话配置（管理员）

    设置每用户最大活跃项目会话数：
    - 1：单会话模式（默认），新会话会清理旧资源
    - >1：多会话模式，保留最多 N 个活跃会话
    """
    from app.core.config import settings

    # 更新运行时配置
    settings.MAX_PROJECT_SESSIONS_PER_USER = request.max_sessions_per_user

    logger.info(f"管理员更新项目会话配置: max_sessions_per_user={request.max_sessions_per_user}")

    return {
        "status": "updated",
        "max_sessions_per_user": request.max_sessions_per_user,
        "mode": "single-session" if request.max_sessions_per_user == 1 else "multi-session"
    }

