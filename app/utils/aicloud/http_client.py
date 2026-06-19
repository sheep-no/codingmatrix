"""
aicloud 共享 HTTP 客户端模块

提供：
- 连接池复用
- 并发限制
- 重试机制（指数退避）
"""

import asyncio
import logging
import httpx
from typing import Optional
from httpx import Timeout

logger = logging.getLogger(__name__)

# 并发限制
_max_concurrent_calls = asyncio.Semaphore(20)

# 共享 HTTP 客户端
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """获取或创建共享的 HTTP 客户端（连接池复用，双重检查锁）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_client_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=Timeout(300.0, connect=10.0),
                    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
                )
    return _http_client


async def close_http_client():
    """关闭 HTTP 客户端"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def call_with_retry(
    request_func,
    max_retries: int = 3,
    retry_on_status: tuple = (429, 500, 502, 503, 504)
):
    """
    带重试机制的 API 调用
    
    Args:
        request_func: 异步请求函数
        max_retries: 最大重试次数
        retry_on_status: 需要重试的 HTTP 状态码（默认包含 429 限流）
    
    Returns:
        响应结果
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            result = await request_func()
            if hasattr(result, 'status_code'):
                if result.status_code == 200:
                    return result
                if result.status_code in retry_on_status:
                    # 429 优先使用 Retry-After header
                    if result.status_code == 429:
                        retry_after = result.headers.get('Retry-After')
                        if retry_after and retry_after.isdigit():
                            wait_time = min(int(retry_after), 60)
                        else:
                            wait_time = (2 ** attempt) * 2.0  # 429 用更长退避
                    elif result.status_code == 503:
                        # 503 模型过载，使用更长退避时间
                        wait_time = (2 ** attempt) * 3.0  # 3s, 6s, 12s
                        logger.warning(f"API 503 模型过载, 重试 {attempt + 1}/{max_retries}, 等待 {wait_time}s")
                    else:
                        wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"API 失败 (状态码 {result.status_code}), 重试 {attempt + 1}/{max_retries}, 等待 {wait_time}s")
                    await asyncio.sleep(wait_time)
                    last_error = result
                    continue
            return result
        except httpx.TimeoutException as e:
            last_error = e
            wait_time = (2 ** attempt) * 1.0
            logger.warning(f"API 超时, 重试 {attempt + 1}/{max_retries}, 等待 {wait_time}s")
            await asyncio.sleep(wait_time)
        except httpx.HTTPError as e:
            last_error = e
            wait_time = (2 ** attempt) * 1.0
            logger.warning(f"API 网络错误: {e}, 重试 {attempt + 1}/{max_retries}")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"API 异常: {e}", exc_info=True)
            raise
    
    raise last_error


class RateLimitedClient:
    """带并发限制的 HTTP 客户端封装"""
    
    def __init__(self, max_concurrent: int = 20):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
    
    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        timeout=Timeout(60.0, connect=10.0),
                        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
                    )
        return self._client
    
    async def request(self, method: str, url: str, **kwargs):
        async with self.semaphore:
            client = await self.get_client()
            return await client.request(method, url, **kwargs)
    
    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)
    
    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
