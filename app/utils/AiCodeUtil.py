import asyncio
import httpx
import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Optional
from httpx import Timeout
from collections import OrderedDict
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

# 连接池（复用 HTTP 客户端）
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """获取或创建共享的 HTTP 客户端（连接池复用）"""
    global _http_client
    async with _http_client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=Timeout(360.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return _http_client


async def close_http_client():
    """关闭 HTTP 客户端"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


# Embedding 本地缓存
_embedding_cache_dir = Path("./cache/embedding_cache")
_embedding_cache_dir.mkdir(parents=True, exist_ok=True)
_EMBEDDING_CACHE_MAXSIZE = 512
_embedding_memory_cache: OrderedDict = OrderedDict()  # {text_hash: vector}
_embedding_memory_ttl = 3600  # 1 小时 TTL
_embedding_memory_expiry: dict = {}  # {text_hash: expire_time}


def _get_embedding_cache_key(text: str, model: str) -> str:
    """计算 embedding 缓存键"""
    raw = f"{model}:{text}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def _load_embedding_from_disk(cache_key: str) -> list:
    """从磁盘加载 embedding 缓存"""
    cache_file = _embedding_cache_dir / f"{cache_key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if time.time() - data.get("timestamp", 0) < 86400:
                return data.get("vector")
        except Exception:
            pass
    return None


def _save_embedding_to_disk(cache_key: str, vector: list):
    """保存 embedding 到磁盘"""
    try:
        cache_file = _embedding_cache_dir / f"{cache_key}.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({"vector": vector, "timestamp": time.time()}, f)
    except Exception:
        pass


def _clean_expired_disk_cache():
    """清理过期的磁盘缓存"""
    now = time.time()
    for cache_file in _embedding_cache_dir.glob("*.json"):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if now - data.get("timestamp", 0) > 86400:
                cache_file.unlink()
        except Exception:
            pass


async def get_embedding(text: str, model: str = "BAAI/bge-m3") -> list:
    """
    获取文本的嵌入向量（用于语义相似度计算）
    默认使用 BCE embedding base v1，支持中文/英文双语
    
    优化：
    - 内存缓存（1 小时 TTL）
    - 磁盘缓存（24 小时 TTL）
    - 避免重复 API 调用
    """
    cache_key = _get_embedding_cache_key(text, model)

    # 1. 检查内存缓存
    if cache_key in _embedding_memory_cache:
        if time.time() < _embedding_memory_expiry.get(cache_key, 0):
            _embedding_memory_cache.move_to_end(cache_key)
            return _embedding_memory_cache[cache_key]
        else:
            del _embedding_memory_cache[cache_key]
            if cache_key in _embedding_memory_expiry:
                del _embedding_memory_expiry[cache_key]

    # 2. 检查磁盘缓存
    disk_vector = _load_embedding_from_disk(cache_key)
    if disk_vector is not None:
        # 加载到内存缓存
        _embedding_memory_cache[cache_key] = disk_vector
        _embedding_memory_expiry[cache_key] = time.time() + _embedding_memory_ttl
        return disk_vector

    # 3. 调用 API
    headers = {
        "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "input": text
    }
    async with httpx.AsyncClient(timeout=Timeout(30.0, connect=10.0)) as client:
        resp = await client.post(
            f"{settings.SILICONFLOW_BASE_URL}/embeddings",
            headers=headers,
            json=data
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Embedding 失败: {resp.text}")
        result = resp.json()
        vector = result["data"][0]["embedding"]

    # 4. 保存到缓存
    _embedding_memory_cache[cache_key] = vector
    _embedding_memory_cache.move_to_end(cache_key)
    _embedding_memory_expiry[cache_key] = time.time() + _embedding_memory_ttl
    # 淘汰最久未使用的过期条目
    while len(_embedding_memory_cache) > _EMBEDDING_CACHE_MAXSIZE:
        oldest_key = next(iter(_embedding_memory_cache))
        if time.time() >= _embedding_memory_expiry.get(oldest_key, 0):
            del _embedding_memory_cache[oldest_key]
            _embedding_memory_expiry.pop(oldest_key, None)
        else:
            break
    _save_embedding_to_disk(cache_key, vector)

    # 定期清理过期磁盘缓存（每 100 次调用清理一次）
    if len(_embedding_memory_cache) % 100 == 0:
        _clean_expired_disk_cache()

    return vector
