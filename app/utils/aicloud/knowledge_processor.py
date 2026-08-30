"""
知识库处理工具

包含：
- 文档解析 (PDF, TXT, MD, DOCX)
- 文本分块
- 向量化 (使用已有的 Embedding API)
- 相似度检索
"""

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """文档分块数据"""
    content: str
    chunk_index: int
    metadata: dict
    content_hash: str


def compute_content_hash(content: str) -> str:
    """计算内容哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_text_file(file_path: str) -> str:
    """解析纯文本文件 (TXT, MD, PY, JS 等)"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.error(f"文本文件解析失败: {e}")
        raise


def parse_pdf_file(file_path: str) -> str:
    """解析 PDF 文件"""
    try:
        # 尝试使用 PyPDF2
        import PyPDF2
        text = ""
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except ImportError:
        logger.warning("PyPDF2 未安装，尝试使用 pdfplumber")
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
            return text
        except ImportError:
            logger.error("PDF 解析库未安装，请安装 PyPDF2 或 pdfplumber")
            raise
    except Exception as e:
        logger.error(f"PDF 解析失败: {e}")
        raise


def parse_docx_file(file_path: str) -> str:
    """解析 Word DOCX 文件"""
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except ImportError:
        logger.error("python-docx 未安装，请安装: pip install python-docx")
        raise
    except Exception as e:
        logger.error(f"DOCX 解析失败: {e}")
        raise


def parse_document(file_path: str) -> str:
    """根据文件类型解析文档"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix in (".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".log"):
        return parse_text_file(file_path)
    elif suffix == ".pdf":
        return parse_pdf_file(file_path)
    elif suffix in (".docx", ".doc"):
        return parse_docx_file(file_path)
    else:
        # 尝试作为文本解析
        return parse_text_file(file_path)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[DocumentChunk]:
    """
    将文本分块
    
    Args:
        text: 原始文本
        chunk_size: 每块大小 (字符数)
        chunk_overlap: 块重叠大小 (字符数)
    
    Returns:
        分块列表
    """
    if not text.strip():
        return []
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        
        # 尝试在段落边界截断
        if end < text_length:
            # 查找最近的段落结束符
            for sep in ["\n\n", "\n", "。", ".", "!", "?"]:
                last_sep = text.rfind(sep, start, end + 50)
                if last_sep > start + chunk_size // 2:
                    end = last_sep + len(sep)
                    break
        
        chunk_content = text[start:end].strip()
        if chunk_content:
            chunk = DocumentChunk(
                content=chunk_content,
                chunk_index=len(chunks),
                metadata={"start": start, "end": end},
                content_hash=compute_content_hash(chunk_content)
            )
            chunks.append(chunk)
        
        # 移动起始位置，考虑重叠
        start = end - chunk_overlap
        if start <= 0:
            start = end
    
    return chunks


async def embed_chunks(
    chunks: List[DocumentChunk],
    model: str = "BAAI/bge-m3"
) -> List[Tuple[DocumentChunk, List[float]]]:
    """
    为文本块生成向量
    
    Args:
        chunks: 文本块列表
        model: Embedding 模型
    
    Returns:
        (chunk, vector) 元组列表
    """
    from app.utils.AiCodeUtil import get_embedding
    
    results = []
    for chunk in chunks:
        try:
            vector = await get_embedding(chunk.content, model=model)
            results.append((chunk, vector))
        except Exception as e:
            logger.error(f"Embedding 失败: {e}, 内容: {chunk.content[:50]}...")
            # 使用零向量作为占位
            results.append((chunk, [0.0] * 768))
    
    return results


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算余弦相似度"""
    import math
    
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def search_similar_chunks(
    query_vector: List[float],
    chunks_with_vectors: List[Tuple[DocumentChunk, List[float]]],
    top_k: int = 5
) -> List[Tuple[DocumentChunk, float]]:
    """
    检索相似文本块
    
    Args:
        query_vector: 查询向量
        chunks_with_vectors: (chunk, vector) 列表
        top_k: 返回最相似的 K 个结果
    
    Returns:
        (chunk, similarity_score) 列表
    """
    scores = []
    for chunk, vector in chunks_with_vectors:
        score = cosine_similarity(query_vector, vector)
        scores.append((chunk, score))
    
    # 按相似度降序排序
    scores.sort(key=lambda x: x[1], reverse=True)
    
    return scores[:top_k]
