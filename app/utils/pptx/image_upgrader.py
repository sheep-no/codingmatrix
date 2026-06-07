"""PPTX 智能配图策略模块

提供 Pexels/Pixabay/Unsplash 图库搜索、图片质量检测、下载转换、AI 图片生成、智能降级链、图片缓存管理等功能。
"""

import logging
import httpx
import os
import hashlib
import random
import uuid
import math
import io
import asyncio
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ImageCacheManager:
    """图片缓存管理器

    管理已下载和搜索结果的缓存，支持基于关键词的缓存键生成、缓存过期策略、
    缓存大小限制和自动清理。
    """

    _DEFAULT_CACHE_DIR = Path("./pptx_output/image_cache")
    _DEFAULT_MAX_SIZE_MB = 500
    _DEFAULT_TTL_HOURS = 24

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_size_mb: int = _DEFAULT_MAX_SIZE_MB,
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ):
        """初始化

        Args:
            cache_dir: 缓存目录路径
            max_size_mb: 缓存最大大小 (MB)
            ttl_hours: 缓存过期时间 (小时)
        """
        self._cache_dir = cache_dir or self._DEFAULT_CACHE_DIR
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._ttl = timedelta(hours=ttl_hours)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._search_cache: Dict[str, Dict] = {}

    @staticmethod
    def generate_cache_key(query: str, source: str, **kwargs) -> str:
        """基于关键词和参数生成缓存键

        Args:
            query: 搜索关键词
            source: 图片来源 (pexels, pixabay, unsplash)
            **kwargs: 额外搜索参数

        Returns:
            MD5 缓存键字符串
        """
        params_str = f"{source}:{query}:" + ":".join(
            f"{k}={v}" for k, v in sorted(kwargs.items())
        )
        return hashlib.md5(params_str.encode("utf-8")).hexdigest()

    def get_search_results(self, cache_key: str) -> Optional[List[Dict]]:
        """获取缓存的搜索结果

        Args:
            cache_key: 缓存键

        Returns:
            缓存的搜索结果列表，未命中或过期返回 None
        """
        if cache_key not in self._search_cache:
            return None

        entry = self._search_cache[cache_key]
        if datetime.now() - entry["cached_at"] > self._ttl:
            del self._search_cache[cache_key]
            return None

        logger.info("搜索结果缓存命中: %s", cache_key[:8])
        return entry["results"]

    def set_search_results(self, cache_key: str, results: List[Dict]) -> None:
        """缓存搜索结果

        Args:
            cache_key: 缓存键
            results: 搜索结果列表
        """
        self._search_cache[cache_key] = {
            "results": results,
            "cached_at": datetime.now(),
        }
        logger.info("搜索结果已缓存: %s (%d 条)", cache_key[:8], len(results))

    def get_cached_image_path(self, url: str) -> Optional[Path]:
        """获取已缓存的图片本地路径

        Args:
            url: 图片 URL

        Returns:
            缓存文件路径，不存在返回 None
        """
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        cached_file = self._cache_dir / f"{url_hash}.jpg"
        if cached_file.exists():
            mtime = datetime.fromtimestamp(cached_file.stat().st_mtime)
            if datetime.now() - mtime <= self._ttl:
                logger.info("图片文件缓存命中: %s", url_hash[:8])
                return cached_file
            else:
                cached_file.unlink()
        return None

    def cache_image(self, url: str, data: bytes) -> Path:
        """缓存图片数据到本地

        Args:
            url: 图片 URL
            data: 图片二进制数据

        Returns:
            缓存文件路径
        """
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        cached_file = self._cache_dir / f"{url_hash}.jpg"
        cached_file.write_bytes(data)
        self._enforce_size_limit()
        logger.info("图片已缓存: %s -> %s (%d bytes)", url_hash[:8], cached_file, len(data))
        return cached_file

    def _enforce_size_limit(self) -> None:
        """检查并清理超出大小限制的缓存"""
        total_size = sum(f.stat().st_size for f in self._cache_dir.glob("*") if f.is_file())
        if total_size <= self._max_size_bytes:
            return

        files_with_mtime = [
            (f, f.stat().st_mtime) for f in self._cache_dir.glob("*") if f.is_file()
        ]
        files_with_mtime.sort(key=lambda x: x[1])

        for file_path, _ in files_with_mtime:
            if total_size <= self._max_size_bytes:
                break
            file_size = file_path.stat().st_size
            file_path.unlink()
            total_size -= file_size
            logger.info("清理过期缓存: %s (%d bytes)", file_path.name, file_size)

    def clear_expired(self) -> int:
        """清理所有过期缓存文件

        Returns:
            清理的文件数量
        """
        count = 0
        cutoff = datetime.now() - self._ttl
        for f in self._cache_dir.glob("*"):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    count += 1

        expired_keys = [
            k for k, v in self._search_cache.items()
            if datetime.now() - v["cached_at"] > self._ttl
        ]
        for k in expired_keys:
            del self._search_cache[k]

        logger.info("清理过期缓存: %d 个文件, %d 个搜索记录", count, len(expired_keys))
        return count

    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息

        Returns:
            包含文件数量、总大小、搜索缓存数量的字典
        """
        files = list(self._cache_dir.glob("*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        return {
            "file_count": len([f for f in files if f.is_file()]),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_mb": self._max_size_bytes / (1024 * 1024),
            "search_cache_entries": len(self._search_cache),
        }


class PexelsImageSearch:
    """Pexels 图库搜索器

    通过 Pexels API 搜索高质量免费图片。
    """

    _BASE_URL = "https://api.pexels.com/v1"
    _SEARCH_URL = f"{_BASE_URL}/search"
    _CURATED_URL = f"{_BASE_URL}/curated"
    _MAX_RETRIES = 3
    _RETRY_DELAY = 1.0

    def __init__(self, api_key: Optional[str] = None):
        """初始化

        Args:
            api_key: Pexels API 密钥，未提供时从环境变量读取
        """
        self._api_key = api_key or os.environ.get("PEXELS_API_KEY")
        self._headers = {"Authorization": self._api_key} if self._api_key else {}

    def search_images(
        self,
        query: str,
        max_results: int = 5,
        orientation: Optional[str] = None,
        size: Optional[str] = None,
        color: Optional[str] = None,
        min_quality_score: float = 0.0,
    ) -> List[Dict]:
        """搜索图片

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            orientation: 图片方向 (landscape, portrait, square)
            size: 图片尺寸 (large, medium, small)
            color: 主色调颜色
            min_quality_score: 最低质量分数 (0-1)

        Returns:
            图片信息列表，包含 url, photographer, src, quality_score 等字段
        """
        if not self._api_key:
            logger.warning("Pexels API key 未配置，跳过搜索")
            return []

        params: Dict[str, object] = {"query": query, "per_page": max_results}
        if orientation:
            params["orientation"] = orientation
        if size:
            params["size"] = size
        if color:
            params["color"] = color

        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(self._SEARCH_URL, headers=self._headers, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                        retry_after = float(e.response.headers.get("Retry-After", self._RETRY_DELAY * (attempt + 1)))
                        logger.warning("Pexels 速率限制，%.1f 秒后重试 (%d/%d)", retry_after, attempt + 1, self._MAX_RETRIES)
                        import time
                        time.sleep(retry_after)
                        continue
                    logger.error("Pexels API 请求失败: %s", e)
                    return []
                except httpx.RequestError as e:
                    if attempt < self._MAX_RETRIES - 1:
                        logger.warning("Pexels 网络异常，%.1f 秒后重试 (%d/%d)", self._RETRY_DELAY, attempt + 1, self._MAX_RETRIES)
                        import time
                        time.sleep(self._RETRY_DELAY)
                        continue
                    logger.error("Pexels 网络请求异常: %s", e)
                    return []
            else:
                return []

            results = []
            for photo in data.get("photos", []):
                img_info = {
                    "id": photo.get("id"),
                    "url": photo.get("url"),
                    "photographer": photo.get("photographer"),
                    "src": photo.get("src", {}),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "quality_score": self._calculate_quality_score(photo),
                }
                if img_info["quality_score"] >= min_quality_score:
                    results.append(img_info)

            logger.info("Pexels 搜索 '%s' 返回 %d 条结果 (过滤后)", query, len(results))
            return results

        except Exception as e:
            logger.error("Pexels 搜索异常: %s", e)
            return []

    def get_random_photo(self, max_results: int = 3) -> List[Dict]:
        """获取随机精选照片

        Args:
            max_results: 获取数量

        Returns:
            随机精选照片列表
        """
        if not self._api_key:
            logger.warning("Pexels API key 未配置")
            return []

        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(
                            self._CURATED_URL,
                            headers=self._headers,
                            params={"per_page": max_results * 3},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                        import time
                        time.sleep(self._RETRY_DELAY * (attempt + 1))
                        continue
                    logger.error("Pexels 精选照片请求失败: %s", e)
                    return []
                except httpx.RequestError as e:
                    if attempt < self._MAX_RETRIES - 1:
                        import time
                        time.sleep(self._RETRY_DELAY)
                        continue
                    logger.error("Pexels 网络请求异常: %s", e)
                    return []
            else:
                return []

            photos = data.get("photos", [])
            selected = random.sample(photos, min(max_results, len(photos)))

            results = []
            for photo in selected:
                results.append({
                    "id": photo.get("id"),
                    "url": photo.get("url"),
                    "photographer": photo.get("photographer"),
                    "src": photo.get("src", {}),
                    "quality_score": self._calculate_quality_score(photo),
                })
            return results

        except Exception as e:
            logger.error("Pexels 精选照片异常: %s", e)
            return []

    @staticmethod
    def _calculate_quality_score(photo: Dict) -> float:
        """计算图片质量分数

        Args:
            photo: Pexels 图片信息

        Returns:
            质量分数 (0-1)
        """
        width = photo.get("width", 0)
        height = photo.get("height", 0)
        if width == 0 or height == 0:
            return 0.0

        megapixels = (width * height) / 1_000_000
        score = min(megapixels / 10.0, 0.6)

        ratio = width / height
        if 1.7 <= ratio <= 1.85:
            score += 0.2
        elif 1.3 <= ratio <= 2.0:
            score += 0.1

        if width >= 1920 and height >= 1080:
            score += 0.2

        return round(min(score, 1.0), 3)


class PixabayImageSearch:
    """Pixabay 图库搜索器

    通过 Pixabay API 搜索免费图片和插画。
    """

    _BASE_URL = "https://pixabay.com/api"
    _MAX_RETRIES = 3
    _RETRY_DELAY = 1.0

    def __init__(self, api_key: Optional[str] = None):
        """初始化

        Args:
            api_key: Pixabay API 密钥，未提供时从环境变量读取
        """
        self._api_key = api_key or os.environ.get("PIXABAY_API_KEY")

    def search_images(
        self,
        query: str,
        max_results: int = 5,
        image_type: Optional[str] = None,
        orientation: Optional[str] = None,
        category: Optional[str] = None,
        min_quality_score: float = 0.0,
    ) -> List[Dict]:
        """搜索图片

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            image_type: 图片类型 (all, photo, illustration, vector)
            orientation: 图片方向 (all, horizontal, vertical)
            category: 图片分类
            min_quality_score: 最低质量分数 (0-1)

        Returns:
            图片信息列表，包含 url, tags, dimensions, quality_score 等字段
        """
        if not self._api_key:
            logger.warning("Pixabay API key 未配置，跳过搜索")
            return []

        params: Dict[str, object] = {
            "key": self._api_key,
            "q": query,
            "per_page": max_results,
        }
        if image_type:
            params["image_type"] = image_type
        else:
            params["image_type"] = "photo"
        if orientation:
            params["orientation"] = orientation
        else:
            params["orientation"] = "horizontal"
        if category:
            params["category"] = category

        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(self._BASE_URL, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                        import time
                        retry_after = float(e.response.headers.get("Retry-After", self._RETRY_DELAY * (attempt + 1)))
                        logger.warning("Pixabay 速率限制，%.1f 秒后重试 (%d/%d)", retry_after, attempt + 1, self._MAX_RETRIES)
                        time.sleep(retry_after)
                        continue
                    logger.error("Pixabay API 请求失败: %s", e)
                    return []
                except httpx.RequestError as e:
                    if attempt < self._MAX_RETRIES - 1:
                        logger.warning("Pixabay 网络异常，%.1f 秒后重试 (%d/%d)", self._RETRY_DELAY, attempt + 1, self._MAX_RETRIES)
                        import time
                        time.sleep(self._RETRY_DELAY)
                        continue
                    logger.error("Pixabay 网络请求异常: %s", e)
                    return []
            else:
                return []

            results = []
            for hit in data.get("hits", []):
                img_info = {
                    "id": hit.get("id"),
                    "url": hit.get("pageURL"),
                    "preview_url": hit.get("previewURL"),
                    "web_url": hit.get("webformatURL"),
                    "full_url": hit.get("largeImageURL"),
                    "tags": hit.get("tags", ""),
                    "width": hit.get("imageWidth"),
                    "height": hit.get("imageHeight"),
                    "downloads": hit.get("downloads"),
                    "likes": hit.get("likes"),
                    "quality_score": self._calculate_quality_score(hit),
                }
                if img_info["quality_score"] >= min_quality_score:
                    results.append(img_info)

            logger.info("Pixabay 搜索 '%s' 返回 %d 条结果 (过滤后)", query, len(results))
            return results

        except Exception as e:
            logger.error("Pixabay 搜索异常: %s", e)
            return []

    def download_and_cache(
        self,
        image_info: Dict,
        cache_manager: Optional["ImageCacheManager"] = None,
    ) -> Optional[Path]:
        """下载图片并写入缓存

        Args:
            image_info: 图片信息字典
            cache_manager: 缓存管理器实例

        Returns:
            本地文件路径，失败返回 None
        """
        url = image_info.get("full_url") or image_info.get("web_url")
        if not url:
            return None

        if cache_manager:
            cached_path = cache_manager.get_cached_image_path(url)
            if cached_path:
                return cached_path

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning("URL 返回非图片类型: %s", content_type)
                    return None

                if cache_manager:
                    return cache_manager.cache_image(url, resp.content)
                else:
                    temp_path = Path("/tmp") / f"pixabay_{uuid.uuid4().hex[:8]}.jpg"
                    temp_path.write_bytes(resp.content)
                    logger.info("图片下载成功: %s -> %s", url, temp_path)
                    return temp_path

        except httpx.HTTPStatusError as e:
            logger.error("Pixabay 图片下载 HTTP 错误: %s", e)
            return None
        except httpx.RequestError as e:
            logger.error("Pixabay 图片下载网络错误: %s", e)
            return None
        except OSError as e:
            logger.error("Pixabay 图片保存失败: %s", e)
            return None

    @staticmethod
    def _calculate_quality_score(hit: Dict) -> float:
        """计算图片质量分数

        Args:
            hit: Pixabay 图片信息

        Returns:
            质量分数 (0-1)
        """
        width = hit.get("imageWidth", 0)
        height = hit.get("imageHeight", 0)
        if width == 0 or height == 0:
            return 0.0

        megapixels = (width * height) / 1_000_000
        score = min(megapixels / 10.0, 0.5)

        likes = hit.get("likes", 0)
        downloads = hit.get("downloads", 0)
        popularity_score = min((likes + downloads / 10) / 100, 0.3)
        score += popularity_score

        if width >= 1920 and height >= 1080:
            score += 0.2

        return round(min(score, 1.0), 3)


class UnsplashImageSearch:
    """Unsplash 图库搜索器

    通过 Unsplash API 搜索高质量免费图片。
    """

    _BASE_URL = "https://api.unsplash.com"
    _SEARCH_URL = f"{_BASE_URL}/search/photos"
    _PHOTOS_URL = f"{_BASE_URL}/photos"
    _RANDOM_URL = f"{_PHOTOS_URL}/random"
    _MAX_RETRIES = 3
    _RETRY_DELAY = 1.0

    def __init__(self, api_key: Optional[str] = None):
        """初始化

        Args:
            api_key: Unsplash API 密钥 (Access Key)，未提供时从环境变量读取
        """
        self._api_key = api_key or os.environ.get("UNSPLASH_API_KEY")

    def search_images(
        self,
        query: str,
        max_results: int = 5,
        orientation: Optional[str] = None,
        color: Optional[str] = None,
        order_by: str = "relevant",
        min_quality_score: float = 0.0,
    ) -> List[Dict]:
        """搜索图片

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            orientation: 图片方向 (landscape, portrait, squarish)
            color: 主色调 (black_and_white, black, white, yellow, orange, red, purple, magenta, green, teal, blue)
            order_by: 排序方式 (relevant, latest, oldest)
            min_quality_score: 最低质量分数 (0-1)

        Returns:
            图片信息列表，包含 url, photographer, urls, quality_score 等字段
        """
        if not self._api_key:
            logger.warning("Unsplash API key 未配置，跳过搜索")
            return []

        params: Dict[str, object] = {
            "query": query,
            "per_page": max_results,
            "order_by": order_by,
        }
        if orientation:
            params["orientation"] = orientation
        if color:
            params["color"] = color

        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(
                            self._SEARCH_URL,
                            headers={"Authorization": f"Client-ID {self._api_key}"},
                            params=params,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                        import time
                        retry_after = float(e.response.headers.get("Retry-After", self._RETRY_DELAY * (attempt + 1)))
                        logger.warning("Unsplash 速率限制，%.1f 秒后重试 (%d/%d)", retry_after, attempt + 1, self._MAX_RETRIES)
                        time.sleep(retry_after)
                        continue
                    logger.error("Unsplash API 请求失败: %s", e)
                    return []
                except httpx.RequestError as e:
                    if attempt < self._MAX_RETRIES - 1:
                        logger.warning("Unsplash 网络异常，%.1f 秒后重试 (%d/%d)", self._RETRY_DELAY, attempt + 1, self._MAX_RETRIES)
                        import time
                        time.sleep(self._RETRY_DELAY)
                        continue
                    logger.error("Unsplash 网络请求异常: %s", e)
                    return []
            else:
                return []

            results = []
            for photo in data.get("results", []):
                img_info = {
                    "id": photo.get("id"),
                    "url": photo.get("links", {}).get("html"),
                    "photographer": photo.get("user", {}).get("name"),
                    "photographer_username": photo.get("user", {}).get("username"),
                    "urls": photo.get("urls", {}),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "quality_score": self._calculate_quality_score(photo),
                }
                if img_info["quality_score"] >= min_quality_score:
                    results.append(img_info)

            logger.info("Unsplash 搜索 '%s' 返回 %d 条结果 (过滤后)", query, len(results))
            return results

        except Exception as e:
            logger.error("Unsplash 搜索异常: %s", e)
            return []

    def get_random_photos(
        self,
        max_results: int = 3,
        topic: Optional[str] = None,
        color: Optional[str] = None,
        orientation: Optional[str] = None,
    ) -> List[Dict]:
        """获取随机精选照片

        Args:
            max_results: 获取数量
            topic: 主题/分类 ID
            color: 主色调过滤
            orientation: 方向过滤

        Returns:
            随机照片列表
        """
        if not self._api_key:
            logger.warning("Unsplash API key 未配置")
            return []

        results = []
        for _ in range(max_results):
            params: Dict[str, object] = {"count": 1}
            if topic:
                params["topics"] = [topic]
            if color:
                params["color"] = color
            if orientation:
                params["orientation"] = orientation

            try:
                photo = None
                for attempt in range(self._MAX_RETRIES):
                    try:
                        with httpx.Client(timeout=10.0) as client:
                            resp = client.get(
                                self._RANDOM_URL,
                                headers={"Authorization": f"Client-ID {self._api_key}"},
                                params=params,
                            )
                            resp.raise_for_status()
                            photo = resp.json()
                            break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                            import time
                            time.sleep(self._RETRY_DELAY * (attempt + 1))
                            continue
                        break
                    except httpx.RequestError as e:
                        if attempt < self._MAX_RETRIES - 1:
                            import time
                            time.sleep(self._RETRY_DELAY)
                            continue
                        break

                if photo is None:
                    continue

                results.append({
                    "id": photo.get("id"),
                    "url": photo.get("links", {}).get("html"),
                    "photographer": photo.get("user", {}).get("name"),
                    "urls": photo.get("urls", {}),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "quality_score": self._calculate_quality_score(photo),
                })
            except Exception as e:
                logger.error("Unsplash 随机照片异常: %s", e)

        logger.info("Unsplash 随机照片返回 %d 条结果", len(results))
        return results

    @staticmethod
    def _calculate_quality_score(photo: Dict) -> float:
        """计算图片质量分数

        Args:
            photo: Unsplash 图片信息

        Returns:
            质量分数 (0-1)
        """
        width = photo.get("width", 0)
        height = photo.get("height", 0)
        if width == 0 or height == 0:
            return 0.0

        megapixels = (width * height) / 1_000_000
        score = min(megapixels / 12.0, 0.5)

        likes = photo.get("likes", 0)
        score += min(likes / 200, 0.3)

        ratio = width / height
        if 1.7 <= ratio <= 1.85:
            score += 0.2
        elif 1.3 <= ratio <= 2.0:
            score += 0.1

        return round(min(score, 1.0), 3)


class ImageQualityChecker:
    """图片质量检测器

    检测图片分辨率、纵横比、文件大小等质量指标。
    """

    _COMMON_ASPECT_RATIOS = [
        (4, 3),
        (16, 9),
        (3, 2),
        (1, 1),
    ]

    def check_resolution(self, image_path: str) -> Dict:
        """检查图片分辨率

        Args:
            image_path: 图片文件路径

        Returns:
            包含 width, height, megapixels, is_hd 的字典
        """
        path = Path(image_path)
        if not path.exists():
            logger.error("图片文件不存在: %s", image_path)
            return {"width": 0, "height": 0, "megapixels": 0.0, "is_hd": False}

        try:
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
                megapixels = (width * height) / 1_000_000
                is_hd = width >= 1920 and height >= 1080

                logger.info(
                    "图片分辨率: %dx%d (%.2f MP, HD=%s)",
                    width, height, megapixels, is_hd,
                )
                return {
                    "width": width,
                    "height": height,
                    "megapixels": round(megapixels, 2),
                    "is_hd": is_hd,
                }
        except ImportError:
            logger.warning("PIL 库未安装，无法检测分辨率")
            return {"width": 0, "height": 0, "megapixels": 0.0, "is_hd": False}
        except Exception as e:
            logger.error("读取图片失败: %s", e)
            return {"width": 0, "height": 0, "megapixels": 0.0, "is_hd": False}

    def check_aspect_ratio(self, image_path: str) -> Dict:
        """检查图片纵横比

        Args:
            image_path: 图片文件路径

        Returns:
            包含 ratio, ratio_decimal, closest_match, deviation 的字典
        """
        path = Path(image_path)
        if not path.exists():
            logger.error("图片文件不存在: %s", image_path)
            return {"ratio": "0:0", "ratio_decimal": 0.0, "closest_match": None, "deviation": 1.0}

        try:
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
                if height == 0:
                    return {"ratio": "0:0", "ratio_decimal": 0.0, "closest_match": None, "deviation": 1.0}

                ratio_decimal = width / height

                closest_match = None
                min_deviation = float("inf")
                for w, h in self._COMMON_ASPECT_RATIOS:
                    target = w / h
                    deviation = abs(ratio_decimal - target)
                    if deviation < min_deviation:
                        min_deviation = deviation
                        closest_match = f"{w}:{h}"

                gcd_val = math.gcd(width, height)
                ratio_str = f"{width // gcd_val}:{height // gcd_val}"

                return {
                    "ratio": ratio_str,
                    "ratio_decimal": round(ratio_decimal, 3),
                    "closest_match": closest_match,
                    "deviation": round(min_deviation, 4),
                }
        except ImportError:
            logger.warning("PIL 库未安装，无法检测纵横比")
            return {"ratio": "0:0", "ratio_decimal": 0.0, "closest_match": None, "deviation": 1.0}
        except Exception as e:
            logger.error("读取图片失败: %s", e)
            return {"ratio": "0:0", "ratio_decimal": 0.0, "closest_match": None, "deviation": 1.0}

    def is_suitable_for_pptx(
        self,
        image_path: str,
        min_width: int = 800,
        min_height: int = 600,
    ) -> Dict:
        """判断图片是否适合用于 PPT

        Args:
            image_path: 图片文件路径
            min_width: 最小宽度要求
            min_height: 最小高度要求

        Returns:
            包含 suitable, reasons, resolution, aspect_ratio 的字典
        """
        resolution = self.check_resolution(image_path)
        aspect_ratio = self.check_aspect_ratio(image_path)

        reasons = []
        suitable = True

        if resolution["width"] < min_width:
            suitable = False
            reasons.append(f"宽度过小 ({resolution['width']} < {min_width})")

        if resolution["height"] < min_height:
            suitable = False
            reasons.append(f"高度不足 ({resolution['height']} < {min_height})")

        if aspect_ratio["deviation"] > 0.15:
            reasons.append(f"纵横比不标准 (偏差 {aspect_ratio['deviation']})")

        path = Path(image_path)
        file_size = path.stat().st_size if path.exists() else 0
        if file_size > 10 * 1024 * 1024:
            suitable = False
            reasons.append(f"文件过大 ({file_size / 1024 / 1024:.1f} MB)")

        return {
            "suitable": suitable,
            "reasons": reasons,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }


class ImageDownloader:
    """图片下载器

    提供图片下载、格式转换等功能。
    """

    def download_image(self, url: str, save_path: str) -> bool:
        """下载图片到本地

        Args:
            url: 图片 URL
            save_path: 保存路径

        Returns:
            是否下载成功
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning("URL 返回非图片类型: %s", content_type)
                    return False

                path = Path(save_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)

                logger.info("图片下载成功: %s -> %s (%d bytes)", url, save_path, len(resp.content))
                return True

        except httpx.HTTPStatusError as e:
            logger.error("图片下载 HTTP 错误: %s", e)
            return False
        except httpx.RequestError as e:
            logger.error("图片下载网络错误: %s", e)
            return False
        except OSError as e:
            logger.error("保存图片写失败: %s", e)
            return False

    def download_and_convert(self, url: str, save_path: str, format: str = "PNG") -> bool:
        """下载图片并转换格式

        Args:
            url: 图片 URL
            save_path: 输出保存路径
            format: 目标格式 (PNG, JPEG, WEBP)

        Returns:
            是否成功
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()

            from PIL import Image
            with Image.open(io.BytesIO(resp.content)) as img:
                path = Path(save_path)
                path.parent.mkdir(parents=True, exist_ok=True)

                suffix_map = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
                if path.suffix.lower() != suffix_map.get(format.upper(), "").lower():
                    path = path.with_suffix(suffix_map.get(format.upper(), ".png"))
                    save_path = str(path)

                if format.upper() == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                img.save(save_path, format=format.upper())
                logger.info("图片下载并转换为 %s: %s", format, save_path)
                return True

        except Exception as e:
            logger.error("图片下载或转换失败: %s", e)
            return False


class AdvancedImageGenerator:
    """AI 图片生成增强器

    提供带风格生成、批量生成、变体生成等功能。
    """

    def __init__(self, api_endpoint: Optional[str] = None):
        """初始化

        Args:
            api_endpoint: AI 图片生成 API 端点
        """
        self._api_endpoint = api_endpoint or "https://api.example.com/v1/generate"

    def generate_with_style(self, prompt: str, style: str = "flat illustration") -> Optional[Dict]:
        """带风格参数生成图片

        Args:
            prompt: 生成提示词
            style: 图片风格

        Returns:
            生成结果字典，失败返回 None
        """
        full_prompt = f"{prompt}, {style}"
        logger.info("生成图片: style='%s', prompt='%s'", style, prompt)

        try:
            request_id = str(uuid.uuid4())
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    self._api_endpoint,
                    json={"prompt": full_prompt, "request_id": request_id},
                )
                resp.raise_for_status()
                result = resp.json()

                return {
                    "image_url": result.get("image_url"),
                    "prompt": full_prompt,
                    "style": style,
                    "request_id": request_id,
                }
        except httpx.HTTPStatusError as e:
            logger.error("图片生成 API 错误: %s", e)
            return None
        except httpx.RequestError as e:
            logger.error("图片生成网络错误: %s", e)
            return None

    def generate_batch(self, prompts: List[str], max_concurrent: int = 3) -> List[Dict]:
        """批量生成图片

        Args:
            prompts: 提示词列表
            max_concurrent: 最大并发数

        Returns:
            生成结果列表
        """
        results = []
        logger.info("批量生成 %d 张图片，最大并发 %d", len(prompts), max_concurrent)

        try:
            async def _fetch(client: httpx.AsyncClient, prompt: str) -> Optional[Dict]:
                try:
                    resp = await client.post(self._api_endpoint, json={"prompt": prompt})
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e:
                    logger.error("批量生成单张图片失败: %s", e)
                    return None

            async def _run_batch():
                async with httpx.AsyncClient(timeout=60.0) as client:
                    sem = asyncio.Semaphore(max_concurrent)

                    async def _limited(p: str):
                        async with sem:
                            return await _fetch(client, p)

                    return await asyncio.gather(*[_limited(p) for p in prompts])

            # 安全获取事件循环：复用已有循环或创建新的
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 已有运行中的事件循环，用 nest_asyncio 或同步回退
                logger.warning("检测到已有事件循环，降级为串行生成")
                for i, prompt in enumerate(prompts):
                    res = self.generate_with_style(prompt)
                    if res:
                        results.append({"image_url": res.get("image_url"), "prompt": prompt, "index": i})
                return results
            else:
                batch_results = asyncio.run(_run_batch())
                for i, res in enumerate(batch_results):
                    if res:
                        results.append({
                            "image_url": res.get("image_url"),
                            "prompt": prompts[i],
                            "index": i,
                        })

            logger.info("批量生成完成: %d/%d 成功", len(results), len(prompts))
            return results

        except Exception as e:
            logger.error("批量生成异常: %s", e)
            for i, prompt in enumerate(prompts):
                res = self.generate_with_style(prompt)
                if res:
                    results.append({"image_url": res.get("image_url"), "prompt": prompt, "index": i})
            return results

    def generate_variations(self, base_prompt: str, count: int = 3) -> List[Dict]:
        """生成变体图片

        Args:
            base_prompt: 基础提示词
            count: 变体数量

        Returns:
            变体生成结果列表
        """
        variations = [
            f"{base_prompt}, high quality, detailed",
            f"{base_prompt}, minimalist style, clean composition",
            f"{base_prompt}, vibrant colors, dramatic lighting",
            f"{base_prompt}, soft lighting, pastel tones",
            f"{base_prompt}, professional photography style",
        ]

        selected = random.sample(variations, min(count, len(variations)))
        logger.info("生成 %d 个变体 from base: '%s'", count, base_prompt)

        return self.generate_batch(selected)


class ImageStrategy:
    """配图策略管理器

    管理多图源的降级链：Unsplash -> Pexels -> Pixabay -> AI 生成 -> 占位符。
    支持智能图片来源选择、并发搜索、图片质量评分和自动过滤。
    """

    _KEYWORD_SOURCE_HINTS = {
        "nature": "unsplash",
        "landscape": "unsplash",
        "travel": "unsplash",
        "food": "unsplash",
        "business": "pexels",
        "technology": "pexels",
        "office": "pexels",
        "illustration": "pixabay",
        "icon": "pixabay",
        "vector": "pixabay",
        "background": "unsplash",
        "texture": "pixabay",
        "pattern": "pixabay",
    }

    def __init__(
        self,
        pexels_api_key: Optional[str] = None,
        pixabay_api_key: Optional[str] = None,
        unsplash_api_key: Optional[str] = None,
        image_gen_endpoint: Optional[str] = None,
        cache_manager: Optional[ImageCacheManager] = None,
    ):
        """初始化

        Args:
            pexels_api_key: Pexels API 密钥
            pixabay_api_key: Pixabay API 密钥
            unsplash_api_key: Unsplash API 密钥
            image_gen_endpoint: AI 图片生成 API 端点
            cache_manager: 图片缓存管理器
        """
        self._pexels = PexelsImageSearch(api_key=pexels_api_key)
        self._pixabay = PixabayImageSearch(api_key=pixabay_api_key)
        self._unsplash = UnsplashImageSearch(api_key=unsplash_api_key)
        self._generator = AdvancedImageGenerator(api_endpoint=image_gen_endpoint)
        self._quality_checker = ImageQualityChecker()
        self._cache = cache_manager or ImageCacheManager()

    def get_best_image(
        self,
        keywords: List[str],
        description: Optional[str] = None,
        slide_type: str = "content",
    ) -> Optional[Dict]:
        """获取最佳配图

        按智能降级链依次尝试各图源，返回首个满足质量要求的图片。

        Args:
            keywords: 关键词列表
            description: 幻灯片描述（用于 AI 生成）
            slide_type: 幻灯片类型

        Returns:
            最佳图片信息字典，或 None
        """
        query = " ".join(keywords) if keywords else ""
        logger.info("获取配图: keywords=%s, slide_type=%s", keywords, slide_type)

        preferred_source = self._determine_preferred_source(keywords)

        if preferred_source == "unsplash":
            order = ["unsplash", "pexels", "pixabay"]
        elif preferred_source == "pexels":
            order = ["pexels", "unsplash", "pixabay"]
        elif preferred_source == "pixabay":
            order = ["pixabay", "pexels", "unsplash"]
        else:
            order = ["unsplash", "pexels", "pixabay"]

        cache_key = self._cache.generate_cache_key(query, "strategy", order="+".join(order))
        cached_results = self._cache.get_search_results(cache_key)
        if cached_results:
            for img in cached_results:
                if img.get("quality_score", 0) >= 0.5:
                    logger.info("缓存命中最佳图片: %s", img.get("url", img.get("web_url")))
                    return img

        search_results = self._search_concurrent(query, order)

        for img in search_results:
            if self._check_image_quality(img):
                logger.info("%s 命中: %s", img.get("source", "unknown"), img.get("url", img.get("web_url")))
                return img

        if description:
            ai_prompt = f"{description}, presentation slide background, {slide_type} style"
            ai_result = self._generator.generate_with_style(ai_prompt)
            if ai_result and ai_result.get("image_url"):
                logger.info("AI 生成成功")
                return {"source": "ai_generation", **ai_result}

        logger.warning("所有图源均失败，返回占位符")
        return self._generate_placeholder(query)

    def fallback_chain(self) -> List[str]:
        """返回降级链各层名称

        Returns:
            降级链列表
        """
        return ["unsplash", "pexels", "pixabay", "ai_generation", "placeholder"]

    def _determine_preferred_source(self, keywords: List[str]) -> Optional[str]:
        """根据关键词智能选择首选图片来源

        Args:
            keywords: 关键词列表

        Returns:
            推荐的图片来源名称
        """
        source_scores: Dict[str, int] = {"unsplash": 0, "pexels": 0, "pixabay": 0}

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in self._KEYWORD_SOURCE_HINTS:
                source_scores[self._KEYWORD_SOURCE_HINTS[kw_lower]] += 2
            for hint_keyword, source in self._KEYWORD_SOURCE_HINTS.items():
                if hint_keyword in kw_lower:
                    source_scores[source] += 1

        preferred = max(source_scores, key=source_scores.get)
        if source_scores[preferred] > 0:
            logger.info("智能图片来源选择: %s (关键词: %s)", preferred, keywords)
            return preferred
        return None

    def _search_concurrent(self, query: str, order: List[str]) -> List[Dict]:
        """并发搜索多个图库

        Args:
            query: 搜索关键词
            order: 搜索优先级顺序

        Returns:
            按优先级排序的图片列表
        """
        all_results: List[Dict] = []

        async def _search_source(source: str) -> List[Dict]:
            if source == "unsplash":
                results = await asyncio.to_thread(
                    self._unsplash.search_images, query, max_results=5, min_quality_score=0.3
                )
                return [{"source": "unsplash", **r} for r in results]
            elif source == "pexels":
                results = await asyncio.to_thread(
                    self._pexels.search_images, query, max_results=5, min_quality_score=0.3
                )
                return [{"source": "pexels", **r} for r in results]
            elif source == "pixabay":
                results = await asyncio.to_thread(
                    self._pixabay.search_images, query, max_results=5, min_quality_score=0.3
                )
                return [{"source": "pixabay", **r} for r in results]
            return []

        async def _run_all():
            tasks = [_search_source(s) for s in order]
            return await asyncio.gather(*tasks, return_exceptions=True)

        try:
            # 安全获取事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 已有运行中的事件循环，降级为串行搜索
                logger.warning("检测到已有事件循环，降级为串行搜索")
                source_results_list = []
                for source in order:
                    try:
                        if source == "unsplash":
                            results = self._unsplash.search_images(query, max_results=5, min_quality_score=0.3)
                        elif source == "pexels":
                            results = self._pexels.search_images(query, max_results=5, min_quality_score=0.3)
                        elif source == "pixabay":
                            results = self._pixabay.search_images(query, max_results=5, min_quality_score=0.3)
                        else:
                            results = []
                        source_results_list.append([{"source": source, **r} for r in results])
                    except Exception as e:
                        logger.warning("串行搜索 %s 失败: %s", source, e)
                        source_results_list.append([])
            else:
                source_results_list = asyncio.run(_run_all())
        except Exception as e:
            logger.warning("搜索失败，降级为串行搜索: %s", e)
            source_results_list = []
            for source in order:
                try:
                    if source == "unsplash":
                        results = self._unsplash.search_images(query, max_results=5, min_quality_score=0.3)
                    elif source == "pexels":
                        results = self._pexels.search_images(query, max_results=5, min_quality_score=0.3)
                    elif source == "pixabay":
                        results = self._pixabay.search_images(query, max_results=5, min_quality_score=0.3)
                    else:
                        results = []
                    source_results_list.append([{"source": source, **r} for r in results])
                except Exception as se:
                    logger.warning("串行搜索 %s 失败: %s", source, se)
                    source_results_list.append([])

        for source_results in source_results_list:
            if isinstance(source_results, Exception):
                logger.warning("某图源搜索异常: %s", source_results)
                continue
            all_results.extend(source_results)

        all_results.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        if all_results:
            self._cache.set_search_results(
                self._cache.generate_cache_key(query, "strategy"),
                all_results,
            )

        return all_results

    def _check_image_quality(self, image_info: Dict) -> bool:
        """检查远程图片质量

        通过 URL 下载临时文件并检测质量。
        """
        url = (
            image_info.get("full_url")
            or image_info.get("urls", {}).get("full")
            or image_info.get("src", {}).get("large2x")
            or image_info.get("web_url")
        )

        if not url:
            return False

        if self._cache:
            cached_path = self._cache.get_cached_image_path(url)
            if cached_path:
                quality = self._quality_checker.is_suitable_for_pptx(str(cached_path))
                return quality["suitable"]

        downloader = ImageDownloader()
        temp_path = Path("/tmp") / f"pptx_check_{uuid.uuid4().hex[:8]}.jpg"

        try:
            if downloader.download_image(url, str(temp_path)):
                if self._cache:
                    temp_data = temp_path.read_bytes()
                    self._cache.cache_image(url, temp_data)
                quality = self._quality_checker.is_suitable_for_pptx(str(temp_path))
                return quality["suitable"]
            return False
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _generate_placeholder(query: str) -> Dict:
        """生成占位符图片信息

        Args:
            query: 搜索关键词（用作标签）

        Returns:
            占位符信息字典
        """
        return {
            "source": "placeholder",
            "url": None,
            "label": f"配图: {query}",
            "width": 1920,
            "height": 1080,
            "color": "#E0E0E0",
        }
