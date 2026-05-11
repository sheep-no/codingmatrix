"""
aicloud API 端点

包含：
- POST /api/v1/aicloud/chat - 聊天接口
- POST /api/v1/aicloud/read - 文件读取
- POST /api/v1/aicloud/write - 文件写入
- GET /api/v1/aicloud/history - 历史记录
- GET /api/v1/aicloud/audit-logs - 审计日志查询
"""

import logging
import os
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.db.database import get_db
from app.utils.security import verify_token
from app.schema.aicloud import (
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    FileReadRequest,
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
    AuditLogResponse,
    SessionResponse,
    ReviewResponse,
    ReviewActionRequest,
    MessageResponse,
    SessionExportResponse,
    SessionDeleteResponse,
    ModelInfoResponse,
    ModelsListResponse,
    CodeExecuteRequest,
    CodeExecuteResponse,
)
from app.utils.aicloud.permission import check_aicloud_permission
from app.utils.aicloud.context_isolator import is_protected_path, is_protected_file
from app.utils.aicloud.sandbox import ensure_user_sandbox
from app.utils.aicloud.sandbox_operator import SandboxFileOperator
from app.utils.aicloud.review_queue import create_review, approve_review, reject_review
from app.utils.aicloud.audit_logger import log_operation, log_file_read, log_file_write
from app.models.aicloud import AicloudSession, AicloudMessage, AicloudReview, AicloudAuditLog
from app.utils.AiCodeUtil import call_siliconflow
from app.utils.aicloud.model_registry import get_model, get_default_model, get_available_models, get_provider_info
from app.utils.aicloud.auto_executor import execute_with_llm_loop
from app.utils.aicloud.sandbox import get_sandbox_workspace_path, ensure_user_sandbox

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/aicloud", tags=["aicloud"])


async def get_current_user_id(token: dict = Depends(verify_token)) -> int:
    """从 JWT token 获取当前用户 ID"""
    user_id_str = token.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID"
        )
    return int(user_id_str)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 聊天接口

    处理用户消息并返回 AI 响应
    """
    await check_aicloud_permission(user_id, db)

    session_id = request.session_id or str(uuid4())
    model_info = get_model(request.model_id) if request.model_id else get_default_model()

    session_result = await db.execute(
        select(AicloudSession).where(AicloudSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        session = AicloudSession(id=session_id, user_id=user_id)
        db.add(session)
        await db.commit()

    messages_result = await db.execute(
        select(AicloudMessage)
        .where(AicloudMessage.session_id == session_id)
        .order_by(AicloudMessage.created_at.asc())
    )
    history_messages = messages_result.scalars().all()

    history_context = ""
    if history_messages:
        history_parts = []
        for msg in history_messages[-10:]:
            role = "用户" if msg.role == "user" else "助手"
            history_parts.append(f"{role}：{msg.content}")
        history_context = "\n".join(history_parts) + "\n\n"

    system_prompt = """你是一个智能助手，名为 aicloud。你具有以下特点：
1. 专业、友好、有耐心
2. 可以帮助用户处理各种问题，包括技术问题和生活问题
3. 你可以使用 Python 代码执行文件操作、数据分析、报告生成等任务
4. 当需要读取文件、生成文件或执行计算时，请使用 ```python ... ``` 代码块
5. 所有文件操作路径请使用绝对路径，用户沙箱路径为: {sandbox_path}
6. 注重安全，所有操作都有审计日志
7. 支持 10 天记忆持久化

**可用工具**：
- 读取文件: 使用 `with open(path, 'r') as f: content = f.read()`
- 写入文件: 使用 `with open(path, 'w') as f: f.write(content)`
- 列出目录: 使用 `import os; os.listdir(path)` 或 `os.walk(path)`
- 数据分析: 使用标准库进行数据处理

当前用户请求："""

    # 确保沙箱目录存在
    try:
        sandbox_path = await ensure_user_sandbox(user_id)
        workspace_path = get_sandbox_workspace_path(user_id)
    except Exception as e:
        logger.error(f"沙箱初始化失败: {e}")
        sandbox_path = f"/sandbox/{user_id}"
        workspace_path = f"/sandbox/{user_id}/workspace"

    # RAG 知识库检索
    knowledge_context = ""
    try:
        from app.utils.AiCodeUtil import get_embedding
        from app.utils.aicloud.knowledge_processor import search_similar_chunks, cosine_similarity
        from app.models.aicloud_knowledge import AicloudKnowledgeChunk
        import json

        # 查询向量化
        query_vector = await get_embedding(request.message)

        # 检索知识库
        chunk_query = select(AicloudKnowledgeChunk).where(
            AicloudKnowledgeChunk.user_id == user_id,
            AicloudKnowledgeChunk.embedding.isnot(None)
        )
        chunk_result = await db.execute(chunk_query)
        all_chunks = chunk_result.scalars().all()

        if all_chunks:
            chunks_with_vectors = []
            for chunk in all_chunks:
                try:
                    vector = json.loads(chunk.embedding)
                    from app.utils.aicloud.knowledge_processor import DocumentChunk
                    doc_chunk = DocumentChunk(
                        content=chunk.content,
                        chunk_index=chunk.chunk_index,
                        metadata={"doc_id": chunk.doc_id, "filename": chunk.collection},
                        content_hash=chunk.content_hash or ""
                    )
                    chunks_with_vectors.append((doc_chunk, vector))
                except Exception:
                    continue

            # 获取最相关的 3 个文本块
            similar_chunks = search_similar_chunks(query_vector, chunks_with_vectors, top_k=3)
            
            if similar_chunks:
                knowledge_parts = []
                for chunk, score in similar_chunks:
                    if score > 0.6:  # 相似度阈值
                        knowledge_parts.append(f"[知识库参考] (相似度: {score:.2f})\n{chunk.content}")
                
                if knowledge_parts:
                    knowledge_context = "\n\n---\n\n**相关知识库内容**:\n" + "\n\n---\n\n".join(knowledge_parts) + "\n\n---\n"
    except Exception as e:
        logger.warning(f"知识库检索失败: {e}")

    formatted_system_prompt = system_prompt.format(sandbox_path=sandbox_path)

    # 组合完整提示
    full_prompt = f"{history_context}{knowledge_context}{formatted_system_prompt}{request.message}"

    user_message = AicloudMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    await db.commit()

    try:
        # 使用自动执行循环
        ai_response_content = await execute_with_llm_loop(
            initial_prompt=request.message,
            history_context=history_context,
            system_prompt=formatted_system_prompt,
            model_key=model_info.model_key,
            max_tokens=model_info.max_tokens,
            call_siliconflow_func=call_siliconflow,
            user_id=user_id,
            workspace_path=workspace_path
        )

    except Exception as e:
        logger.error(f"AI 调用失败: {e}")
        ai_response_content = f"抱歉，AI 服务暂时不可用: {str(e)[:100]}"
        await log_operation(
            db=db,
            user_id=user_id,
            operation="chat",
            status="error",
            details={"session_id": session_id, "error": str(e)}
        )
        raise HTTPException(status_code=503, detail="AI service unavailable")

    ai_message = AicloudMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response_content
    )
    db.add(ai_message)

    session.last_active_at = datetime.utcnow()
    await db.commit()

    await log_operation(
        db=db,
        user_id=user_id,
        operation="chat",
        status="success",
        details={"session_id": session_id, "model_id": model_info.id, "message_length": len(request.message)}
    )

    return ChatResponse(
        session_id=session_id,
        message=ai_response_content,
        model_id=model_info.id,
        created_at=datetime.utcnow()
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 聊天接口（流式输出）

    处理用户消息并实时返回 AI 响应片段
    """
    from fastapi.responses import StreamingResponse

    await check_aicloud_permission(user_id, db)

    session_id = request.session_id or str(uuid4())
    model_info = get_model(request.model_id) if request.model_id else get_default_model()

    session_result = await db.execute(
        select(AicloudSession).where(AicloudSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        session = AicloudSession(id=session_id, user_id=user_id)
        db.add(session)
        await db.commit()

    messages_result = await db.execute(
        select(AicloudMessage)
        .where(AicloudMessage.session_id == session_id)
        .order_by(AicloudMessage.created_at.asc())
    )
    history_messages = messages_result.scalars().all()

    history_context = ""
    if history_messages:
        history_parts = []
        for msg in history_messages[-10:]:
            role = "用户" if msg.role == "user" else "助手"
            history_parts.append(f"{role}：{msg.content}")
        history_context = "\n".join(history_parts) + "\n\n"

    system_prompt = """你是一个智能助手，名为 aicloud。你具有以下特点：
1. 专业、友好、有耐心
2. 可以帮助用户处理各种问题，包括技术问题和生活问题
3. 可以进行文件操作（在沙箱环境中）
4. 注重安全，所有操作都有审计日志
5. 支持 10 天记忆持久化

当前用户请求："""

    full_prompt = f"{history_context}{system_prompt}{request.message}"

    user_message = AicloudMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    await db.commit()

    async def generate():
        """流式生成生成器"""
        import json
        full_content = []

        try:
            stream_gen = await call_siliconflow(
                prompt=full_prompt,
                model=model_info.model_key,
                stream=True,
                max_tokens=model_info.max_tokens
            )

            async for chunk_str in stream_gen:
                try:
                    chunk = json.loads(chunk_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content.append(content)
                        yield f"data: {json.dumps({'delta': content, 'session_id': session_id})}\n\n"
                except json.JSONDecodeError:
                    continue

            # 保存完整回复
            ai_response_content = "".join(full_content)
            ai_message = AicloudMessage(
                session_id=session_id,
                role="assistant",
                content=ai_response_content
            )
            db.add(ai_message)
            session.last_active_at = datetime.utcnow()
            await db.commit()

            await log_operation(
                db=db,
                user_id=user_id,
                operation="chat",
                status="success",
                details={"session_id": session_id, "model_id": model_info.id, "stream": True}
            )

            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

        except Exception as e:
            logger.error(f"流式 AI 调用失败: {e}")
            yield f"data: {json.dumps({'error': str(e), 'session_id': session_id})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/read", response_model=FileReadResponse)
async def read_file(
    request: FileReadRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 文件读取接口

    读取沙箱中的文件内容
    """
    await check_aicloud_permission(user_id, db)

    if is_protected_path(request.file_path) or is_protected_file(request.file_path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"access to {request.file_path} is not allowed"
        )

    operator = SandboxFileOperator(user_id)

    try:
        result = await operator.read_with_review(
            path=request.file_path,
            require_review=request.require_review,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    except PathSecurityError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        await log_file_read(db, user_id, request.file_path, False, str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if request.require_review and not result.get("ai_passed", True):
        review = await create_review(
            db=db,
            operation_type="read",
            file_path=operator.get_absolute_path(request.file_path),
            content=result.get("raw_content", ""),
            requested_by=user_id,
            ai_filter_passed=result.get("ai_passed", False)
        )

        await log_file_read(db, user_id, operator.get_absolute_path(request.file_path), True)

        return FileReadResponse(
            content=result.get("content", ""),
            review_status="pending",
            filtered_content=result.get("content", ""),
            review_id=review.id
        )

    await log_file_read(db, user_id, operator.get_absolute_path(request.file_path), True)

    return FileReadResponse(
        content=result.get("content", ""),
        review_status="approved",
        filtered_content=result.get("content", "")
    )


@router.post("/write", response_model=FileWriteResponse)
async def write_file(
    request: FileWriteRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 文件写入接口

    写入内容到沙箱中的文件
    """
    await check_aicloud_permission(user_id, db)

    await ensure_user_sandbox(user_id)

    operator = SandboxFileOperator(user_id)

    try:
        result = await operator.write_with_review(
            path=request.file_path,
            content=request.content,
        )
    except PathSecurityError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        await log_file_write(db, user_id, request.file_path, False, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if result.get("review_status") == "approved":
        await log_file_write(
            db, user_id, operator.get_absolute_path(request.file_path),
            True, len(request.content)
        )
        return FileWriteResponse(
            success=True,
            review_status="approved",
            review_id=result.get("review", {}).get("id"),
            message="File written successfully"
        )

    review = await create_review(
        db=db,
        operation_type="write",
        file_path=operator.get_absolute_path(request.file_path),
        content=request.content,
        requested_by=user_id,
        ai_filter_passed=result.get("analysis", {}).get("passed", False),
        details={
            "warnings": result.get("analysis", {}).get("warnings", []),
            "risk_level": result.get("analysis", {}).get("risk_level", "unknown")
        }
    )

    await log_file_write(
        db, user_id, operator.get_absolute_path(request.file_path),
        False, error="pending_review"
    )

    return FileWriteResponse(
        success=False,
        review_status="pending",
        review_id=review.id,
        message="Content pending human review"
    )


@router.get("/history", response_model=SessionResponse)
async def get_history(
    days: int = 10,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 历史记录查询

    获取用户最近的消息历史
    """
    await check_aicloud_permission(user_id, db)

    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(AicloudSession)
        .where(
            AicloudSession.user_id == user_id,
            AicloudSession.last_active_at >= cutoff_date
        )
        .order_by(AicloudSession.last_active_at.desc())
    )
    sessions = result.scalars().all()

    sessions_data = []
    for session in sessions:
        messages_result = await db.execute(
            select(AicloudMessage)
            .where(AicloudMessage.session_id == session.id)
            .order_by(AicloudMessage.created_at.asc())
        )
        messages = messages_result.scalars().all()

        sessions_data.append(SessionResponse(
            id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
            messages=[
                MessageResponse(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at
                )
                for m in messages
            ]
        ))

    return sessions_data[0] if sessions_data else None


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    user_id: Optional[int] = None,
    operation: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    aicloud 审计日志查询

    查询用户的操作审计日志
    """
    await check_aicloud_permission(current_user_id, db)

    query = select(AicloudAuditLog)

    if user_id:
        query = query.where(AicloudAuditLog.user_id == user_id)
    else:
        query = query.where(AicloudAuditLog.user_id == current_user_id)

    if operation:
        query = query.where(AicloudAuditLog.operation == operation)

    if start_date:
        query = query.where(AicloudAuditLog.created_at >= start_date)

    if end_date:
        query = query.where(AicloudAuditLog.created_at <= end_date)

    query = query.order_by(AicloudAuditLog.created_at.desc()).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            operation=log.operation,
            file_path=log.file_path,
            url=log.url,
            status=log.status,
            details=log.details,
            created_at=log.created_at
        )
        for log in logs
    ]


@router.get("/reviews", response_model=list[ReviewResponse])
async def get_reviews(
    status_filter: Optional[str] = "pending",
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    获取审查队列

    获取待处理的审查列表
    """
    await check_aicloud_permission(user_id, db)

    query = select(AicloudReview)

    if status_filter:
        query = query.where(AicloudReview.status == status_filter)

    query = query.order_by(AicloudReview.created_at.desc()).limit(50)

    result = await db.execute(query)
    reviews = result.scalars().all()

    return [
        ReviewResponse(
            id=r.id,
            operation_type=r.operation_type,
            file_path=r.file_path,
            status=r.status,
            requested_by=r.requested_by,
            reviewed_by=r.reviewed_by,
            ai_filter_passed=r.ai_filter_passed,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at
        )
        for r in reviews
    ]


@router.post("/reviews/approve")
async def approve_review_endpoint(
    request: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    批准审查

    批准一个待处理的审查请求
    """
    await check_aicloud_permission(user_id, db)

    review = await approve_review(db, request.review_id, user_id)

    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")

    if review.operation_type == "write" and review.content:
        sandbox_path = review.file_path
        try:
            import os
            os.makedirs(os.path.dirname(sandbox_path), exist_ok=True)
            with open(sandbox_path, "w", encoding="utf-8") as f:
                f.write(review.content)

            await log_file_write(db, user_id, sandbox_path, True, len(review.content))
        except Exception as e:
            await log_file_write(db, user_id, sandbox_path, False, error=str(e))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {"status": "approved", "review_id": review.id}


@router.post("/reviews/reject")
async def reject_review_endpoint(
    request: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    拒绝审查

    拒绝一个待处理的审查请求
    """
    await check_aicloud_permission(user_id, db)

    review = await reject_review(db, request.review_id, user_id, request.reason)

    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")

    return {"status": "rejected", "review_id": review.id}


@router.get("/history/search", response_model=list[SessionExportResponse])
async def search_history(
    keyword: str,
    days: int = 10,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    搜索历史记录

    在用户的历史消息中搜索关键词
    """
    await check_aicloud_permission(user_id, db)

    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(AicloudSession)
        .where(
            AicloudSession.user_id == user_id,
            AicloudSession.last_active_at >= cutoff_date
        )
        .order_by(AicloudSession.last_active_at.desc())
    )
    sessions = result.scalars().all()

    matching_sessions = []
    for session in sessions:
        messages_result = await db.execute(
            select(AicloudMessage)
            .where(AicloudMessage.session_id == session.id)
            .order_by(AicloudMessage.created_at.asc())
        )
        messages = messages_result.scalars().all()

        matching_messages = [
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at
            )
            for msg in messages
            if keyword.lower() in msg.content.lower()
        ]

        if matching_messages:
            matching_sessions.append(SessionExportResponse(
                session_id=session.id,
                exported_at=datetime.utcnow(),
                message_count=len(matching_messages),
                messages=matching_messages
            ))

    return matching_sessions


@router.get("/history/export/{session_id}", response_model=SessionExportResponse)
async def export_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    导出会话

    将指定的会话导出为 JSON 格式
    """
    await check_aicloud_permission(user_id, db)

    result = await db.execute(
        select(AicloudSession).where(
            AicloudSession.id == session_id,
            AicloudSession.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages_result = await db.execute(
        select(AicloudMessage)
        .where(AicloudMessage.session_id == session_id)
        .order_by(AicloudMessage.created_at.asc())
    )
    messages = messages_result.scalars().all()

    return SessionExportResponse(
        session_id=session.id,
        exported_at=datetime.utcnow(),
        message_count=len(messages),
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at
            )
            for msg in messages
        ]
    )


@router.delete("/history/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    删除会话

    删除指定的会话及其所有消息
    """
    await check_aicloud_permission(user_id, db)

    result = await db.execute(
        select(AicloudSession).where(
            AicloudSession.id == session_id,
            AicloudSession.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await db.execute(
        delete(AicloudMessage).where(AicloudMessage.session_id == session_id)
    )
    await db.execute(
        delete(AicloudSession).where(AicloudSession.id == session_id)
    )
    await db.commit()

    try:
        from app.utils.cache_decorator import invalidate_cache_by_prefix
        await invalidate_cache_by_prefix("history")
        await invalidate_cache_by_prefix("conversations")
    except Exception as e:
        logger.warning(f"缓存失效失败: {e}")

    return SessionDeleteResponse(
        success=True,
        deleted_session_id=session_id
    )


@router.get("/models", response_model=ModelsListResponse)
async def list_models(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取可用模型列表"""
    await check_aicloud_permission(user_id, db)
    models = get_available_models()
    default = get_default_model()
    provider = get_provider_info()

    return ModelsListResponse(
        models=[
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "max_tokens": m.max_tokens,
                "max_context": m.max_context,
                "capabilities": [c.value for c in m.capabilities],
                "is_default": m.is_default,
                "cost_per_1m_input": m.cost_per_1m_input,
                "cost_per_1m_output": m.cost_per_1m_output,
                "tags": m.tags,
            }
            for m in models
        ],
        default_model=default.id,
        provider=provider,
    )


@router.post("/execute", response_model=CodeExecuteResponse)
async def execute_code(
    request: CodeExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    在沙箱中执行代码片段

    支持 Python, JavaScript, Go 的安全执行。
    """
    await check_aicloud_permission(user_id, db)

    from app.utils.aicloud.code_executor import CodeExecutor
    from app.utils.aicloud.sandbox import get_sandbox_workspace_path

    workspace = get_sandbox_workspace_path(user_id)
    os.makedirs(workspace, exist_ok=True)

    executor = CodeExecutor(workspace_path=workspace)
    result = await executor.execute(
        code=request.code,
        language=request.language,
        timeout=request.timeout
    )

    await log_operation(
        db=db,
        user_id=user_id,
        operation="code_execute",
        status="success" if result.success else "error",
        details={
            "language": result.language,
            "exit_code": result.exit_code,
            "execution_time": result.execution_time
        }
    )

    return CodeExecuteResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        exit_code=result.exit_code,
        execution_time=result.execution_time,
        language=result.language,
    )
