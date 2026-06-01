"""
PPT 并发图像获取器

使用 asyncio.gather 实现并发搜图功能：
- 多源聚合（Bing/Unsplash/Pexels）
- 并发控制（Semaphore）
- 源降级策略
- 超时处理
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# 图片搜索源
IMAGE_SOURCES = ["bing", "unsplash", "pexels"]

# 默认配置
DEFAULT_TIMEOUT = 10  # 秒
DEFAULT_MAX_CONCURRENT = 5  # 最大并发数


@dataclass
class ImageResult:
    """图片搜索结果"""
    url: str
    source: str
    width: int = 1920
    height: int = 1080
    thumbnail_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ImageSearchRequest:
    """图片搜索请求"""
    keywords: List[str]
    source: str
    width: int = 1920
    height: int = 1080


class ImageFetchError(Exception):
    """图片获取异常"""
    pass


class ImageSourceError(ImageFetchError):
    """图片源错误"""
    pass


class ConcurrentImageFetcher:
    """
    并发图像获取器
    
    使用 asyncio.gather 和 Semaphore 实现高效并发搜图。
    """
    
    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        timeout: int = DEFAULT_TIMEOUT,
        cache_dir: Optional[Path] = None,
    ):
        """
        初始化并发图像获取器
        
        Args:
            max_concurrent: 最大并发搜图数
            timeout: 单个图片下载超时（秒）
            cache_dir: 图片缓存目录
        """
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._cache_dir = cache_dir or Path("./static/images/ppt-cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 信号量控制并发数
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # HTTP 客户端
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        )
    
    async def fetch_images(
        self,
        queries: List[List[str]],
        sources: Optional[List[str]] = None,
        max_concurrent: Optional[int] = None,
    ) -> List[Optional[ImageResult]]:
        """
        并发搜索多组关键词的图片
        
        Args:
            queries: 关键词列表，每个元素是一组关键词
            sources: 搜索源列表，默认使用内置源
            max_concurrent: 覆盖最大并发数
            
        Returns:
            图片结果列表，与 queries 一一对应
        """
        if not queries:
            return []
        
        sources = sources or IMAGE_SOURCES
        concurrency = max_concurrent or self._max_concurrent
        
        # 更新信号量
        self._semaphore = asyncio.Semaphore(concurrency)
        
        # 创建任务列表
        tasks = [
            self._fetch_with_fallback(idx, keywords, sources)
            for idx, keywords in enumerate(queries)
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        processed_results: List[Optional[ImageResult]] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"图片搜索失败 | idx={idx} | error={result}")
                processed_results.append(None)
            else:
                processed_results.append(result)
        
        # 关闭 HTTP 客户端
        await self._client.aclose()
        
        return processed_results
    
    async def fetch_single(
        self,
        keywords: List[str],
        sources: Optional[List[str]] = None,
    ) -> Optional[ImageResult]:
        """
        搜索单组关键词的图片
        
        Args:
            keywords: 关键词列表
            sources: 搜索源列表
            
        Returns:
            图片结果，失败时返回 None
        """
        if not keywords:
            return None
        
        sources = sources or IMAGE_SOURCES
        
        return await self._fetch_with_fallback(0, keywords, sources)
    
    async def _fetch_with_fallback(
        self,
        idx: int,
        keywords: List[str],
        sources: List[str],
    ) -> Optional[ImageResult]:
        """
        带降级策略的图片搜索
        
        依次尝试多个搜索源，直到成功或全部失败。
        
        Args:
            idx: 任务索引
            keywords: 关键词列表
            sources: 搜索源列表
            
        Returns:
            图片结果
        """
        async with self._semaphore:
            for source in sources:
                try:
                    result = await self._search_from_source(source, keywords)
                    
                    if result and result.url:
                        logger.info(
                            f"图片搜索成功 | idx={idx} | source={source} | "
                            f"keywords={keywords[:2]}..."
                        )
                        return result
                    else:
                        logger.debug(f"搜索源 {source} 返回空结果")
                        
                except Exception as e:
                    logger.warning(f"搜索源 {source} 失败 | error={e}")
                    continue
            
            # 所有源都失败，返回占位图
            logger.warning(f"所有搜索源失败 | idx={idx} | keywords={keywords}")
            return self._create_placeholder(keywords)
    
    async def _search_from_source(
        self,
        source: str,
        keywords: List[str],
    ) -> Optional[ImageResult]:
        """
        从指定搜索源获取图片
        
        Args:
            source: 搜索源名称
            keywords: 关键词列表
            
        Returns:
            图片结果
        """
        search_methods = {
            "bing": self._search_bing,
            "unsplash": self._search_unsplash,
            "pexels": self._search_pexels,
        }
        
        method = search_methods.get(source)
        
        if method is None:
            raise ImageSourceError(f"不支持的搜索源：{source}")
        
        return await method(keywords)
    
    async def _search_bing(self, keywords: List[str]) -> Optional[ImageResult]:
        """从 Bing 搜索图片（模拟实现）"""
        # TODO: 实际实现需要 Bing Image Search API
        query = " ".join(keywords)
        logger.debug(f"Bing 搜索 | query={query}")
        
        # 模拟实现：返回占位 URL
        return ImageResult(
            url=f"https://via.placeholder.com/1920x1080?text={query}",
            source="bing",
        )
    
    async def _search_unsplash(self, keywords: List[str]) -> Optional[ImageResult]:
        """从 Unsplash 搜索图片（模拟实现）"""
        # TODO: 实际实现需要 Unsplash API Key
        query = "-".join(keywords)
        logger.debug(f"Unsplash 搜索 | query={query}")
        
        # 模拟实现
        return ImageResult(
            url=f"https://source.unsplash.com/1920x1080/?{query}",
            source="unsplash",
        )
    
    async def _search_pexels(self, keywords: List[str]) -> Optional[ImageResult]:
        """从 Pexels 搜索图片（模拟实现）"""
        # TODO: 实际实现需要 Pexels API Key
        query = " ".join(keywords)
        logger.debug(f"Pexels 搜索 | query={query}")
        
        # 模拟实现
        return ImageResult(
            url=f"https://images.pexels.com/search/{query}",
            source="pexels",
        )
    
    def _create_placeholder(self, keywords: List[str]) -> ImageResult:
        """创建占位图结果"""
        text = "+".join(keywords[:3]) if keywords else "placeholder"
        
        return ImageResult(
            url=f"https://via.placeholder.com/1920x1080?text={text}",
            source="placeholder",
            error="All search sources failed",
        )
    
    async def download_image(
        self,
        url: str,
        dest_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        下载图片到本地
        
        Args:
            url: 图片 URL
            dest_path: 目标路径，不传则使用缓存目录
            
        Returns:
            本地文件路径，失败时返回 None
        """
        if dest_path is None:
            # 生成缓存文件名（基于 URL 的 MD5）
            url_hash = hashlib.md5(url.encode()).hexdigest()
            ext = url.split('.')[-1].split('?')[0] or 'jpg'
            dest_path = self._cache_dir / f"{url_hash}.{ext}"
        
        # 检查缓存
        if dest_path.exists():
            logger.debug(f"使用缓存图片 | path={dest_path}")
            return dest_path
        
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            
            # 保存到本地
            dest_path.write_bytes(response.content)
            
            logger.info(f"图片下载成功 | url={url[:50]}... | path={dest_path}")
            return dest_path
            
        except Exception as e:
            logger.warning(f"图片下载失败 | url={url[:50]}... | error={e}")
            return None
    
    async def cleanup_cache(self, max_age_seconds: int = 604800) -> int:
        """
        清理过期缓存图片
        
        Args:
            max_age_seconds: 最大缓存时间（秒），默认 7 天
            
        Returns:
            清理的文件数量
        """
        if not self._cache_dir.exists():
            return 0
        
        now = time.time()
        cleaned_count = 0
        
        for file_path in self._cache_dir.iterdir():
            if file_path.is_file():
                file_age = now - file_path.stat().st_mtime
                
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"删除缓存失败 | path={file_path} | error={e}")
        
        if cleaned_count > 0:
            logger.info(f"清理图片缓存 | cleaned={cleaned_count}")
        
        return cleaned_count


# 全局单例
image_fetcher = ConcurrentImageFetcher()
