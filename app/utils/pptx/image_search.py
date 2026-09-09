"""
PPT 搜图模块

图片搜索策略:
1. Bing Image Search API (需要 API Key)
2. Unsplash API (免费额度)
3. Pexels API (免费额度)
4. 占位图降级方案

优先级: Bing > Unsplash > Pexels > 占位图
"""

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import quote, urlparse

import aiohttp

logger = logging.getLogger(__name__)

# 配置
IMAGE_SEARCH_TIMEOUT = 10
IMAGE_CACHE_DIR = Path("./pptx_output/image_cache")
IMAGE_CACHE_MAX_AGE_DAYS = 7  # 缓存过期天数
IMAGE_CACHE_MAX_SIZE_MB = 500  # 缓存最大容量 MB
IMAGE_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # 单张图片最大 20MB


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否安全（非内网地址）"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                logger.warning("SSRF 阻止：内网地址 %s (%s)", hostname, ip)
                return False
    except (socket.gaierror, ValueError):
        pass
    return True

# 占位图 URL (免费使用)
PLACEHOLDER_URLS = {
    "default": "https://placehold.co/800x600/e2e8f0/475569?text={}",
    "tech": "https://placehold.co/800x600/1e293b/38bdf8?text={}",
    "business": "https://placehold.co/800x600/1e3a5f/3b82f6?text={}",
    "minimal": "https://placehold.co/800x600/f8fafc/334155?text={}",
}


class ImageSearchProvider:
    """图片搜索提供者基类"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def search(self, keyword: str) -> Optional[str]:
        raise NotImplementedError


class BingImageSearch(ImageSearchProvider):
    """Bing 图片搜索"""

    ENDPOINT = "https://api.bing.microsoft.com/v7.0/images/search"

    async def search(self, keyword: str) -> Optional[str]:
        if not self.api_key:
            return None

        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {
            "q": keyword,
            "count": 3,
            "imageType": "Photo",
            "size": "Medium",
            "safeSearch": "Strict",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.ENDPOINT, headers=headers, params=params,
                    timeout=IMAGE_SEARCH_TIMEOUT
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        images = data.get("value", [])
                        if images:
                            return images[0].get("contentUrl")
        except Exception as e:
            logger.warning(f"Bing 搜索失败 [{keyword}]: {e}")

        return None


class UnsplashSearch(ImageSearchProvider):
    """Unsplash 图片搜索"""

    ENDPOINT = "https://api.unsplash.com/search/photos"

    async def search(self, keyword: str) -> Optional[str]:
        if not self.api_key:
            return None

        headers = {"Authorization": f"Client-ID {self.api_key}"}
        params = {"query": keyword, "per_page": 3, "orientation": "landscape"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.ENDPOINT, headers=headers, params=params,
                    timeout=IMAGE_SEARCH_TIMEOUT
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        if results:
                            return results[0].get("urls", {}).get("regular")
        except Exception as e:
            logger.warning(f"Unsplash 搜索失败 [{keyword}]: {e}")

        return None


class PexelsSearch(ImageSearchProvider):
    """Pexels 图片搜索"""

    ENDPOINT = "https://api.pexels.com/v1/search"

    async def search(self, keyword: str) -> Optional[str]:
        if not self.api_key:
            return None

        headers = {"Authorization": self.api_key}
        params = {"query": keyword, "per_page": 3, "orientation": "landscape"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.ENDPOINT, headers=headers, params=params,
                    timeout=IMAGE_SEARCH_TIMEOUT
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        photos = data.get("photos", [])
                        if photos:
                            return photos[0].get("src", {}).get("large")
        except Exception as e:
            logger.warning(f"Pexels 搜索失败 [{keyword}]: {e}")

        return None


class FallbackImageSearch(ImageSearchProvider):
    """占位图降级方案"""

    async def search(self, keyword: str) -> Optional[str]:
        template = PLACEHOLDER_URLS.get("default")
        return template.format(quote(keyword[:20]))


class ImageSearchManager:
    """图片搜索管理器 - 多源聚合 + 缓存"""

    def __init__(
        self,
        bing_key: Optional[str] = None,
        unsplash_key: Optional[str] = None,
        pexels_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.providers: List[ImageSearchProvider] = []

        if bing_key:
            self.providers.append(BingImageSearch(bing_key))
        if unsplash_key:
            self.providers.append(UnsplashSearch(unsplash_key))
        if pexels_key:
            self.providers.append(PexelsSearch(pexels_key))

        # 始终添加降级方案
        self.providers.append(FallbackImageSearch())

        self.cache_dir = cache_dir or IMAGE_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def search_image(self, keyword: str) -> Optional[str]:
        """
        搜索图片，按优先级尝试各提供者
        
        Returns:
            图片 URL 或 None
        """
        for provider in self.providers:
            try:
                url = await provider.search(keyword)
                if url:
                    logger.info(f"图片搜索成功 [{keyword}]: {type(provider).__name__}")
                    return url
            except Exception as e:
                logger.debug(f"{type(provider).__name__} 搜索失败 [{keyword}]: {e}")
                continue

        logger.warning(f"所有图片搜索源均失败 [{keyword}]")
        return None

    async def search_images(self, keywords: List[str]) -> Dict[str, str]:
        """批量搜索图片（限制并发数）"""
        results = {}
        semaphore = asyncio.Semaphore(3)

        async def _search_one(kw: str):
            async with semaphore:
                return kw, await self.search_image(kw)

        tasks = [_search_one(kw) for kw in keywords]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in outcomes:
            if isinstance(outcome, Exception):
                continue
            kw, url = outcome
            if url:
                results[kw] = url

        return results

    async def get_cached_image(self, keyword: str) -> Optional[Path]:
        """获取缓存的图片路径"""
        cache_key = hashlib.md5(keyword.encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.jpg"

        if cache_path.exists():
            return cache_path

        return None

    async def download_and_cache(self, keyword: str, url: str) -> Optional[Path]:
        """下载图片并缓存（SSRF 防护 + 大小限制）"""
        cache_key = hashlib.md5(keyword.encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.jpg"

        if cache_path.exists():
            return cache_path

        if not _is_safe_url(url):
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=IMAGE_SEARCH_TIMEOUT) as resp:
                    if resp.status == 200:
                        content_length = resp.headers.get("Content-Length")
                        if content_length and int(content_length) > IMAGE_DOWNLOAD_MAX_BYTES:
                            logger.warning("图片过大，跳过：%s (%s bytes)", url, content_length)
                            return None
                        data = b""
                        async for chunk in resp.content.iter_chunked(8192):
                            data += chunk
                            if len(data) > IMAGE_DOWNLOAD_MAX_BYTES:
                                logger.warning("图片下载超过大小限制：%s", url)
                                return None
                        cache_path.write_bytes(data)
                        logger.info(f"图片已缓存 [{keyword}]: {cache_path}")
                        return cache_path
        except Exception as e:
            logger.warning(f"图片下载失败 [{keyword}]: {e}")

        return None

    def cleanup_cache(
        self,
        max_age_days: int = IMAGE_CACHE_MAX_AGE_DAYS,
        max_size_mb: float = IMAGE_CACHE_MAX_SIZE_MB,
    ):
        """
        清理过期和超量缓存
        
        Args:
            max_age_days: 最大缓存天数
            max_size_mb: 最大缓存容量 (MB)
        """
        import time
        now = time.time()
        max_age_seconds = max_age_days * 86400
        cleaned = 0

        # 1. 清理过期缓存
        for cache_file in self.cache_dir.glob("*.jpg"):
            if now - cache_file.stat().st_mtime > max_age_seconds:
                cache_file.unlink()
                cleaned += 1

        if cleaned > 0:
            logger.info(f"已清理 {cleaned} 个过期图片缓存")

        # 2. 检查容量，按时间排序删除最旧的
        current_size = self.get_cache_size_mb()
        if current_size > max_size_mb:
            files = sorted(
                self.cache_dir.glob("*.jpg"),
                key=lambda f: f.stat().st_mtime
            )
            for cache_file in files:
                if current_size <= max_size_mb:
                    break
                file_size_mb = cache_file.stat().st_size / (1024 * 1024)
                cache_file.unlink()
                current_size -= file_size_mb
                cleaned += 1

            logger.info(f"缓存超限，已清理 {cleaned} 个文件，当前大小: {current_size:.1f}MB")

    def get_cache_size_mb(self) -> float:
        """获取缓存大小 (MB)"""
        total = sum(f.stat().st_size for f in self.cache_dir.glob("*") if f.is_file())
        return total / (1024 * 1024)

    def get_cache_stats(self) -> Dict[str, any]:
        """获取缓存统计信息"""
        files = list(self.cache_dir.glob("*.jpg"))
        return {
            "count": len(files),
            "size_mb": self.get_cache_size_mb(),
            "cache_dir": str(self.cache_dir),
        }
