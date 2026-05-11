"""
HTTP 客户端连接池

复用 httpx AsyncClient，减少连接建立开销
"""
import httpx
from typing import Optional
from contextlib import asynccontextmanager


class HTTPClientPool:
    """
    HTTP 客户端连接池

    复用连接，减少连接建立开销
    """

    def __init__(
        self,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        timeout: float = 30.0
    ):
        self._client: Optional[httpx.AsyncClient] = None
        self._max_connections = max_connections
        self._max_keepalive = max_keepalive_connections
        self._timeout = timeout
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections
        )

    async def get_client(self) -> httpx.AsyncClient:
        """获取或创建客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                limits=self._limits,
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True
            )
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @asynccontextmanager
    async def client(self):
        """上下文管理器，获取客户端"""
        client = await self.get_client()
        try:
            yield client
        finally:
            pass

    async def __aenter__(self):
        return await self.get_client()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


_http_client_pool: Optional[HTTPClientPool] = None


def get_http_client_pool() -> HTTPClientPool:
    """获取 HTTP 客户端池单例"""
    global _http_client_pool
    if _http_client_pool is None:
        _http_client_pool = HTTPClientPool(
            max_connections=20,
            max_keepalive_connections=10,
            timeout=30.0
        )
    return _http_client_pool


async def get_http_client() -> httpx.AsyncClient:
    """获取 HTTP 客户端（便捷函数）"""
    pool = get_http_client_pool()
    return await pool.get_client()


async def close_http_client():
    """关闭 HTTP 客户端"""
    pool = get_http_client_pool()
    await pool.close()
