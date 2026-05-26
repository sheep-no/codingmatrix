import asyncio
import httpx
import json
import hashlib
import os
import time
from pathlib import Path
from httpx import Timeout
from fastapi import HTTPException

from app.core.config import settings


# Embedding 本地缓存
_embedding_cache_dir = Path("./cache/embedding_cache")
_embedding_cache_dir.mkdir(parents=True, exist_ok=True)
_embedding_memory_cache: dict = {}  # 内存缓存 {text_hash: vector}
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
            # 检查是否过期（24 小时）
            if time.time() - data.get("timestamp", 0) < 86400:
                return data["vector"]
        except Exception:
            pass
    return None


def _save_embedding_to_disk(cache_key: str, vector: list):
    """保存 embedding 到磁盘"""
    cache_file = _embedding_cache_dir / f"{cache_key}.json"
    try:
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


async def call_siliconflow(prompt: str, model: str,
                           stream: bool = False,
                           timeout:Timeout=Timeout(360.0, connect=10.0),
                           max_tokens:int =4096,
                           thinking_budget:int =4096,
                           temperature: float = 0.7,
                           system_prompt: str = "",
                           cancel_event: asyncio.Event = None,
                           api_key_token: str = None
                           ):
    # 获取 API Key：优先使用用户自定义 Key，否则使用系统默认 Key
    api_key = settings.SILICONFLOW_API_KEY
    if api_key_token:
        from app.services.apikey_manager import get_apikey_manager
        try:
            apikey_manager = get_apikey_manager()
            user_key = apikey_manager.get_key("default_user", api_key_token)
            if user_key:
                api_key = user_key
        except Exception as e:
            logger.warning(f"获取用户 API Key 失败，使用系统默认 Key: {e}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建 messages 列表，支持 system prompt
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 清理 prompt 中的 【SYSTEM】/【USER】 标记（向后兼容）
    cleaned_prompt = prompt
    if "【SYSTEM】" in cleaned_prompt:
        import re
        match = re.search(r'【SYSTEM】\s*(.*?)\s*【USER】\s*(.*)', cleaned_prompt, re.DOTALL)
        if match:
            # 如果之前已经组合了 system+user，提取出来
            system_part = match.group(1).strip()
            user_part = match.group(2).strip()
            if not system_prompt:
                messages.insert(0, {"role": "system", "content": system_part})
            cleaned_prompt = user_part

    if model=="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B":
        data = {
            "model": model,
            "messages": messages + [{"role": "user", "content": cleaned_prompt}],
            "stream": stream,
            "max_tokens":max_tokens,
            "thinking_budget": thinking_budget,
            "temperature": temperature
        }
    else:
        data = {
            "model": model,
            "messages": messages + [{"role": "user", "content": cleaned_prompt}],
            "stream": stream
        }

    if stream:
        async def generate():
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                        "POST",
                        f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
                        headers=headers,
                        json=data
                ) as response:
                    async for line in response.aiter_lines():
                        if cancel_event and cancel_event.is_set():
                            await response.aclose()
                            raise asyncio.CancelledError("LLM 调用被取消")
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            yield f"{chunk}\n"

        return generate()
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("LLM 调用被取消")
            resp = await client.post(
                f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
                headers=headers,
                json=data
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()


async def get_embedding(text: str, model: str = "netease-youdao/bce-embedding-base_v1") -> list:
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
    _embedding_memory_expiry[cache_key] = time.time() + _embedding_memory_ttl
    _save_embedding_to_disk(cache_key, vector)

    # 定期清理过期磁盘缓存（每 100 次调用清理一次）
    if len(_embedding_memory_cache) % 100 == 0:
        _clean_expired_disk_cache()

    return vector