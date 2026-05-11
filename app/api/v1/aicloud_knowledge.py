"""
AI Cloud 知识库 API 端点

包含：
- POST /api/v1/aicloud/knowledge/upload - 上传文档
- GET /api/v1/aicloud/knowledge/docs - 获取文档列表
- DELETE /api/v1/aicloud/knowledge/docs/{doc_id} - 删除文档
- POST /api/v1/aicloud/knowledge/search - 检索知识库
"""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.db.database import get_db
from app.utils.security import verify_token
from app.utils.aicloud.permission import check_aicloud_permission
from app.utils.aicloud.knowledge_processor import (
    parse_document,
    chunk_text,
    embed_chunks,
    search_similar_chunks,
    compute_content_hash,
)
from app.utils.AiCodeUtil import get_embedding
from app.models.aicloud_knowledge import AicloudKnowledgeDoc, AicloudKnowledgeChunk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/aicloud/knowledge", tags=["aicloud-knowledge"])


class KnowledgeSearchRequest(BaseModel):
    """知识库搜索请求"""
    query: str
    collection: Optional[str] = "default"
    top_k: int = 5

# 知识库存储路径
KNOWLEDGE_STORAGE_PATH = "/workspace/data/knowledge"
os.makedirs(KNOWLEDGE_STORAGE_PATH, exist_ok=True)


async def get_current_user_id(token: dict = Depends(verify_token)) -> int:
    """从 JWT token 获取当前用户 ID"""
    user_id_str = token.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID"
        )
    return int(user_id_str)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form("default"),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    上传文档到知识库
    
    自动执行：
    1. 保存文件
    2. 解析文档内容
    3. 文本分块
    4. 向量化
    5. 存储到数据库
    """
    await check_aicloud_permission(user_id, db)
    
    # 验证文件类型
    allowed_extensions = {".txt", ".md", ".pdf", ".docx", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".log"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_ext}，支持的类型: {allowed_extensions}"
        )
    
    # 生成文档 ID
    doc_id = str(uuid.uuid4())
    file_path = os.path.join(KNOWLEDGE_STORAGE_PATH, f"{user_id}_{doc_id}{file_ext}")
    
    # 保存文件
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        file_size = len(content)
    except Exception as e:
        logger.error(f"文件保存失败: {e}")
        raise HTTPException(status_code=500, detail="文件保存失败")
    
    # 创建文档记录
    doc = AicloudKnowledgeDoc(
        id=doc_id,
        user_id=user_id,
        filename=file.filename,
        file_type=file_ext,
        file_size=file_size,
        file_path=file_path,
        status="processing",
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        description=description,
        tags=tags,
    )
    db.add(doc)
    await db.commit()
    
    # 异步处理文档（解析、分块、向量化）
    try:
        # 1. 解析文档
        text_content = parse_document(file_path)
        
        # 2. 文本分块
        chunks = chunk_text(text_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        if not chunks:
            doc.status = "failed"
            doc.error_message = "文档内容为空或无法解析"
            await db.commit()
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")
        
        # 3. 向量化
        chunks_with_vectors = await embed_chunks(chunks)
        
        # 4. 存储到数据库
        for chunk, vector in chunks_with_vectors:
            chunk_record = AicloudKnowledgeChunk(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                user_id=user_id,
                content=chunk.content,
                content_hash=chunk.content_hash,
                embedding=str(vector),  # 存储为 JSON 字符串
                embedding_model="netease-youdao/bce-embedding-base_v1",
                chunk_index=chunk.chunk_index,
                collection=collection,
            )
            db.add(chunk_record)
        
        # 更新文档状态
        doc.status = "completed"
        doc.chunk_count = len(chunks)
        await db.commit()
        
        return {
            "status": "success",
            "doc_id": doc_id,
            "filename": file.filename,
            "chunk_count": len(chunks),
            "message": f"文档上传成功，已分割为 {len(chunks)} 个文本块"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文档处理失败: {e}")
        doc.status = "failed"
        doc.error_message = str(e)[:500]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)[:100]}")


@router.get("/docs")
async def list_documents(
    collection: Optional[str] = "default",
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取用户的知识库文档列表"""
    await check_aicloud_permission(user_id, db)
    
    query = select(AicloudKnowledgeDoc).where(
        AicloudKnowledgeDoc.user_id == user_id
    )
    if collection:
        # 通过关联查询过滤集合
        query = query.join(AicloudKnowledgeDoc.chunks).where(
            AicloudKnowledgeChunk.collection == collection
        ).distinct()
    
    query = query.order_by(AicloudKnowledgeDoc.created_at.desc())
    result = await db.execute(query)
    docs = result.scalars().all()
    
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "description": doc.description,
            "tags": doc.tags,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "error_message": doc.error_message,
        }
        for doc in docs
    ]


@router.delete("/docs/{doc_id}")
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """删除知识库文档及其所有分块"""
    await check_aicloud_permission(user_id, db)
    
    # 查找文档
    result = await db.execute(
        select(AicloudKnowledgeDoc).where(
            AicloudKnowledgeDoc.id == doc_id,
            AicloudKnowledgeDoc.user_id == user_id
        )
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除文件
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"删除文件失败: {e}")
    
    # 删除数据库记录（cascade 会自动删除关联的 chunks）
    await db.delete(doc)
    await db.commit()
    
    return {"status": "success", "message": f"文档 {doc.filename} 已删除"}


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    检索知识库
    
    1. 将查询文本向量化
    2. 在用户的知识库中检索最相似的文本块
    3. 返回相关文档片段
    """
    await check_aicloud_permission(user_id, db)
    
    query = request.query
    collection = request.collection
    top_k = request.top_k
    
    if not query.strip():
        raise HTTPException(status_code=400, detail="查询文本不能为空")
    
    # 1. 查询向量化
    try:
        query_vector = await get_embedding(query)
    except Exception as e:
        logger.error(f"查询向量化失败: {e}")
        raise HTTPException(status_code=500, detail="查询向量化失败")
    
    # 2. 获取用户的所有知识库分块
    chunk_query = select(AicloudKnowledgeChunk).where(
        AicloudKnowledgeChunk.user_id == user_id,
        AicloudKnowledgeChunk.embedding.isnot(None)
    )
    if collection:
        chunk_query = chunk_query.where(AicloudKnowledgeChunk.collection == collection)
    
    result = await db.execute(chunk_query)
    all_chunks = result.scalars().all()
    
    if not all_chunks:
        return {
            "query": query,
            "results": [],
            "message": "知识库为空"
        }
    
    # 3. 解析向量并计算相似度
    import json
    chunks_with_vectors = []
    for chunk in all_chunks:
        try:
            vector = json.loads(chunk.embedding)
            # 重建 DocumentChunk 对象
            from app.utils.aicloud.knowledge_processor import DocumentChunk
            doc_chunk = DocumentChunk(
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                metadata={"doc_id": chunk.doc_id, "chunk_id": chunk.id},
                content_hash=chunk.content_hash or ""
            )
            chunks_with_vectors.append((doc_chunk, vector))
        except Exception as e:
            logger.warning(f"解析向量失败: {e}")
            continue
    
    # 4. 检索相似块
    similar_chunks = search_similar_chunks(query_vector, chunks_with_vectors, top_k=top_k)
    
    # 5. 获取文档信息
    doc_ids = list(set([chunk.metadata["doc_id"] for chunk, _ in similar_chunks]))
    docs_result = await db.execute(
        select(AicloudKnowledgeDoc).where(AicloudKnowledgeDoc.id.in_(doc_ids))
    )
    docs_map = {doc.id: doc for doc in docs_result.scalars().all()}
    
    # 6. 构建返回结果
    results = []
    for chunk, score in similar_chunks:
        doc = docs_map.get(chunk.metadata["doc_id"])
        results.append({
            "content": chunk.content,
            "similarity_score": round(score, 4),
            "filename": doc.filename if doc else "Unknown",
            "doc_id": chunk.metadata["doc_id"],
            "chunk_index": chunk.chunk_index,
        })
    
    return {
        "query": query,
        "results": results,
        "total_found": len(results)
    }
