"""
PPT 图片策略单元测试

测试图库搜索、图片缓存和降级策略
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptx.image_upgrader import (
    ImageCacheManager,
    ImageQualityChecker,
    ImageDownloader,
    ImageStrategy
)


class TestImageCacheManager:
    """测试图片缓存管理器"""

    @pytest.fixture
    def cache_manager(self, tmp_path):
        return ImageCacheManager(cache_dir=tmp_path / "cache")

    def test_generate_cache_key(self, cache_manager):
        """测试缓存键生成"""
        key1 = cache_manager.generate_cache_key("technology", "unsplash")
        key2 = cache_manager.generate_cache_key("technology", "pexels")
        key3 = cache_manager.generate_cache_key("nature", "unsplash")

        assert key1 is not None
        assert len(key1) == 32
        assert key1 != key2
        assert key1 != key3

    def test_set_and_get_cache(self, cache_manager):
        """测试缓存设置和获取"""
        cache_key = cache_manager.generate_cache_key("test", "source")
        results = [{"url": "http://example.com/image1.jpg"}]

        cache_manager.set_search_results(cache_key, results)
        cached = cache_manager.get_search_results(cache_key)

        assert cached == results

    def test_cache_miss(self, cache_manager):
        """测试缓存未命中"""
        cached = cache_manager.get_search_results("nonexistent_key")
        assert cached is None

    def test_clear_expired(self, cache_manager):
        """测试清理过期缓存"""
        cache_key = cache_manager.generate_cache_key("test", "source")
        results = [{"url": "http://example.com/image.jpg"}]
        cache_manager.set_search_results(cache_key, results)

        cleared = cache_manager.clear_expired()
        assert isinstance(cleared, int)

    def test_cache_stats(self, cache_manager):
        """测试缓存统计"""
        stats = cache_manager.get_cache_stats()

        assert isinstance(stats, dict)
        assert "file_count" in stats
        assert "total_size_mb" in stats


class TestImageQualityChecker:
    """测试图片质量检查器"""

    @pytest.fixture
    def checker(self):
        return ImageQualityChecker()

    def test_check_resolution_nonexistent(self, checker):
        """测试不存在的文件"""
        result = checker.check_resolution("/nonexistent/file.jpg")
        assert result["width"] == 0
        assert result["height"] == 0
        assert result["is_hd"] is False

    def test_check_resolution_valid(self, checker, tmp_path):
        """测试有效分辨率检查"""
        from PIL import Image
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (1920, 1080), color="red")
        img.save(str(img_path))

        result = checker.check_resolution(str(img_path))

        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["is_hd"] is True

    def test_check_aspect_ratio_nonexistent(self, checker):
        """测试不存在的文件纵横比"""
        result = checker.check_aspect_ratio("/nonexistent/file.jpg")
        assert result["closest_match"] is None

    def test_check_aspect_ratio_valid(self, checker, tmp_path):
        """测试有效纵横比检查"""
        from PIL import Image
        img_path = tmp_path / "16_9.jpg"
        Image.new("RGB", (1920, 1080), color="green").save(str(img_path))

        result = checker.check_aspect_ratio(str(img_path))

        assert result["closest_match"] is not None

    def test_is_suitable_for_pptx_nonexistent(self, checker):
        """测试不存在的文件适用性"""
        result = checker.is_suitable_for_pptx("/nonexistent/file.jpg")
        assert result["suitable"] is False
        assert len(result["reasons"]) > 0


class TestImageDownloader:
    """测试图片下载器"""

    @pytest.fixture
    def downloader(self):
        return ImageDownloader()

    def test_download_image_invalid_url(self, downloader):
        """测试无效 URL 下载"""
        result = downloader.download_image(
            "http://invalid-url-example-12345.com/test.jpg",
            "/tmp/test_download.jpg"
        )
        assert result is False

    def test_download_and_convert_invalid(self, downloader):
        """测试无效 URL 转换"""
        result = downloader.download_and_convert(
            "http://invalid-url-example-12345.com/test.jpg",
            "/tmp/test_convert.png"
        )
        assert result is False


class TestImageStrategy:
    """测试图片策略管理器"""

    @pytest.fixture
    def strategy(self):
        return ImageStrategy()

    def test_fallback_chain(self, strategy):
        """测试降级链"""
        chain = strategy.fallback_chain()

        assert "unsplash" in chain
        assert "pexels" in chain
        assert "pixabay" in chain
        assert "ai_generation" in chain
        assert "placeholder" in chain
        assert len(chain) == 5

    def test_determine_preferred_source(self, strategy):
        """测试智能来源选择"""
        source = strategy._determine_preferred_source(["nature", "landscape"])
        assert source == "unsplash"

    def test_determine_preferred_source_business(self, strategy):
        """测试商务来源选择"""
        source = strategy._determine_preferred_source(["business", "office"])
        assert source == "pexels"

    def test_get_best_image_fallback(self, strategy):
        """测试获取图片降级策略"""
        result = strategy.get_best_image(
            keywords=["test_keyword_xyz_123"]
        )

        assert result is not None
        assert "source" in result

    def test_get_best_image_empty_keywords(self, strategy):
        """测试空关键词获取图片"""
        result = strategy.get_best_image(keywords=[])

        assert result is not None
        assert result["source"] in ["unsplash", "pexels", "pixabay", "ai_generation", "placeholder"]

    def test_generate_placeholder(self, strategy):
        """测试生成占位符"""
        placeholder = strategy._generate_placeholder("test")

        assert placeholder["source"] == "placeholder"
        assert placeholder["width"] == 1920
        assert placeholder["height"] == 1080
