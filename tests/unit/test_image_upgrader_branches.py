import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image

import app.utils.pptx.image_upgrader as image_upgrader


def _response(*, json_data=None, status_code=200, headers=None, content=b""):
    request = httpx.Request("GET", "https://example.com")
    if json_data is not None:
        return httpx.Response(
            status_code=status_code,
            json=json_data,
            headers=headers or {},
            request=request,
        )
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        content=content,
        request=request,
    )


class StubClient:
    """按队列返回响应或抛出异常，并记录请求参数。"""

    responses = []
    requests = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _next(self, method, url, **kwargs):
        type(self).requests.append((method, url, kwargs))
        item = type(self).responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)


@pytest.fixture(autouse=True)
def _patch_transport(monkeypatch):
    StubClient.responses = []
    StubClient.requests = []
    monkeypatch.setattr(image_upgrader.httpx, "Client", StubClient)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    yield


@pytest.fixture
def cache(tmp_path):
    return image_upgrader.ImageCacheManager(cache_dir=tmp_path / "cache")


def _store_search_cache(cache, query, order):
    results = [{"url": "u", "source": "unsplash", "quality_score": 0.9}]
    cache.set_search_results(
        cache.generate_cache_key(query, "strategy", order="+".join(order)),
        results,
    )
    return results


class TestCacheManager:
    def test_cache_key_is_stable_and_param_sensitive(self, cache):
        assert cache.generate_cache_key("q", "src", a=1, b=2) == cache.generate_cache_key(
            "q", "src", b=2, a=1
        )
        assert cache.generate_cache_key("q", "src", a=1) != cache.generate_cache_key("q", "src", a=2)

    def test_expired_search_entry_is_removed(self, cache, monkeypatch):
        key = cache.generate_cache_key("q", "src")
        cache.set_search_results(key, [{"url": "u"}])
        cache._search_cache[key]["cached_at"] = datetime.now() - cache._ttl - timedelta(seconds=1)
        assert cache.get_search_results(key) is None
        assert key not in cache._search_cache

    def test_cached_image_round_trip(self, cache):
        path = cache.cache_image("https://example.com/a.jpg", b"data")
        assert path.read_bytes() == b"data"
        assert cache.get_cached_image_path("https://example.com/a.jpg") == path

    def test_expired_image_file_is_removed(self, cache, monkeypatch):
        path = cache.cache_image("https://example.com/a.jpg", b"data")
        old = (datetime.now() - cache._ttl - timedelta(hours=1)).timestamp()
        import os

        os.utime(path, (old, old))
        assert cache.get_cached_image_path("https://example.com/a.jpg") is None
        assert not path.exists()

    def test_size_limit_evicts_oldest_files(self, tmp_path):
        import os

        manager = image_upgrader.ImageCacheManager(cache_dir=tmp_path / "cache", max_size_mb=0)
        first = tmp_path / "cache" / "old.jpg"
        second = tmp_path / "cache" / "new.jpg"
        first.write_bytes(b"x" * 10)
        second.write_bytes(b"y" * 10)
        os.utime(first, (1000, 1000))
        os.utime(second, (2000, 2000))
        manager._enforce_size_limit()
        assert not first.exists()
        assert not second.exists()

    def test_clear_expired_counts_files_and_entries(self, cache):
        import os

        path = cache.cache_image("https://example.com/a.jpg", b"data")
        old = (datetime.now() - cache._ttl - timedelta(hours=1)).timestamp()
        os.utime(path, (old, old))
        key = cache.generate_cache_key("q", "src")
        cache.set_search_results(key, [])
        cache._search_cache[key]["cached_at"] = datetime.now() - cache._ttl - timedelta(hours=1)
        assert cache.clear_expired() == 1
        assert key not in cache._search_cache

    def test_cache_stats_report_files_and_entries(self, cache):
        cache.cache_image("https://example.com/a.jpg", b"1234")
        cache.set_search_results("key", [])
        stats = cache.get_cache_stats()
        assert stats["file_count"] == 1
        assert stats["search_cache_entries"] == 1
        assert stats["max_size_mb"] == 500


class TestPexelsSearch:
    def test_missing_key_returns_empty(self):
        assert image_upgrader.PexelsImageSearch(api_key="").search_images("q") == []

    def test_search_maps_fields_and_filters_quality(self):
        StubClient.responses = [
            _response(
                json_data={
                    "photos": [
                        {"id": 1, "url": "u1", "photographer": "p", "src": {"large": "x"}, "width": 1920, "height": 1080},
                        {"id": 2, "url": "u2", "width": 10, "height": 10},
                    ]
                }
            )
        ]
        results = image_upgrader.PexelsImageSearch(api_key="k").search_images(
            "q", orientation="landscape", size="large", color="blue", min_quality_score=0.5
        )
        assert [item["id"] for item in results] == [1]
        assert StubClient.requests[0][2]["params"]["orientation"] == "landscape"
        assert StubClient.requests[0][2]["params"]["size"] == "large"
        assert StubClient.requests[0][2]["params"]["color"] == "blue"

    def test_rate_limit_retries_then_succeeds(self):
        StubClient.responses = [
            _response(status_code=429, headers={"Retry-After": "0"}),
            _response(json_data={"photos": []}),
        ]
        assert image_upgrader.PexelsImageSearch(api_key="k").search_images("q") == []
        assert len(StubClient.requests) == 2

    def test_request_error_retries_then_gives_up(self):
        error = httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        StubClient.responses = [error, error, error]
        assert image_upgrader.PexelsImageSearch(api_key="k").search_images("q") == []

    def test_non_429_http_error_returns_empty(self):
        StubClient.responses = [_response(status_code=500)]
        assert image_upgrader.PexelsImageSearch(api_key="k").search_images("q") == []

    def test_unexpected_payload_exception_returns_empty(self):
        StubClient.responses = [_response(json_data=[])]
        assert image_upgrader.PexelsImageSearch(api_key="k").search_images("q") == []

    def test_random_photo_requires_key(self):
        assert image_upgrader.PexelsImageSearch(api_key="").get_random_photo() == []

    def test_random_photo_samples_requested_count(self):
        photos = [
            {"id": index, "width": 1920, "height": 1080, "src": {}}
            for index in range(5)
        ]
        StubClient.responses = [_response(json_data={"photos": photos})]
        results = image_upgrader.PexelsImageSearch(api_key="k").get_random_photo(max_results=2)
        assert len(results) == 2
        assert StubClient.requests[0][2]["params"]["per_page"] == 6

    def test_random_photo_retries_on_429_and_error(self):
        error = httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        StubClient.responses = [
            _response(status_code=429),
            error,
            _response(json_data={"photos": []}),
        ]
        assert image_upgrader.PexelsImageSearch(api_key="k").get_random_photo() == []

    def test_quality_score_boundaries(self):
        assert image_upgrader.PexelsImageSearch._calculate_quality_score({}) == 0.0
        assert image_upgrader.PexelsImageSearch._calculate_quality_score(
            {"width": 1920, "height": 1080}
        ) == 0.607
        assert image_upgrader.PexelsImageSearch._calculate_quality_score(
            {"width": 4000, "height": 3000}
        ) == 0.9


class TestPixabaySearch:
    def test_missing_key_returns_empty(self):
        assert image_upgrader.PixabayImageSearch(api_key="").search_images("q") == []

    def test_search_defaults_and_result_mapping(self):
        StubClient.responses = [
            _response(
                json_data={
                    "hits": [
                        {
                            "id": 1,
                            "pageURL": "page",
                            "previewURL": "preview",
                            "webformatURL": "web",
                            "largeImageURL": "full",
                            "tags": "a,b",
                            "imageWidth": 1920,
                            "imageHeight": 1080,
                            "downloads": 100,
                            "likes": 10,
                        }
                    ]
                }
            )
        ]
        results = image_upgrader.PixabayImageSearch(api_key="k").search_images("q")
        assert results[0]["full_url"] == "full"
        params = StubClient.requests[0][2]["params"]
        assert params["image_type"] == "photo"
        assert params["orientation"] == "horizontal"

    def test_search_retries_and_explicit_filters(self):
        error = httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        StubClient.responses = [
            _response(status_code=429),
            error,
            _response(json_data={"hits": []}),
        ]
        results = image_upgrader.PixabayImageSearch(api_key="k").search_images(
            "q", image_type="vector", orientation="vertical", category="nature"
        )
        assert results == []
        params = StubClient.requests[-1][2]["params"]
        assert params["image_type"] == "vector"
        assert params["orientation"] == "vertical"
        assert params["category"] == "nature"

    def test_search_http_error_and_payload_error(self):
        StubClient.responses = [_response(status_code=500)]
        assert image_upgrader.PixabayImageSearch(api_key="k").search_images("q") == []
        StubClient.responses = [_response(json_data=[])]
        assert image_upgrader.PixabayImageSearch(api_key="k").search_images("q") == []

    def test_download_requires_url(self):
        assert image_upgrader.PixabayImageSearch(api_key="k").download_and_cache({}) is None

    def test_download_uses_cache_hit(self, cache, monkeypatch):
        path = cache.cache_image("https://example.com/a.jpg", b"data")
        service = image_upgrader.PixabayImageSearch(api_key="k")
        result = service.download_and_cache(
            {"web_url": "https://example.com/a.jpg"}, cache_manager=cache
        )
        assert result == path
        assert StubClient.requests == []

    def test_download_rejects_non_image_content(self, cache):
        StubClient.responses = [_response(content=b"data", headers={"content-type": "text/html"})]
        assert image_upgrader.PixabayImageSearch(api_key="k").download_and_cache(
            {"web_url": "https://example.com/a"}, cache_manager=cache
        ) is None

    def test_download_without_cache_writes_temp_file(self):
        StubClient.responses = [
            _response(content=b"image", headers={"content-type": "image/jpeg"})
        ]
        path = image_upgrader.PixabayImageSearch(api_key="k").download_and_cache(
            {"full_url": "https://example.com/a.jpg"}
        )
        assert path.read_bytes() == b"image"
        path.unlink()

    def test_download_with_cache_writes_cache(self, cache):
        StubClient.responses = [
            _response(content=b"image", headers={"content-type": "image/jpeg"})
        ]
        path = image_upgrader.PixabayImageSearch(api_key="k").download_and_cache(
            {"full_url": "https://example.com/a.jpg"}, cache_manager=cache
        )
        assert path.parent == cache._cache_dir

    def test_download_http_and_network_errors(self):
        service = image_upgrader.PixabayImageSearch(api_key="k")
        StubClient.responses = [_response(status_code=500)]
        assert service.download_and_cache({"full_url": "https://example.com/a.jpg"}) is None
        StubClient.responses = [
            httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        ]
        assert service.download_and_cache({"full_url": "https://example.com/a.jpg"}) is None

    def test_download_write_error(self, monkeypatch, tmp_path):
        StubClient.responses = [
            _response(content=b"image", headers={"content-type": "image/jpeg"})
        ]

        def fail_write(self, data):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_bytes", fail_write)
        assert image_upgrader.PixabayImageSearch(api_key="k").download_and_cache(
            {"full_url": "https://example.com/a.jpg"}
        ) is None

    def test_quality_score(self):
        assert image_upgrader.PixabayImageSearch._calculate_quality_score({}) == 0.0
        assert image_upgrader.PixabayImageSearch._calculate_quality_score(
            {"imageWidth": 1920, "imageHeight": 1080, "likes": 100, "downloads": 1000}
        ) == 0.707


class TestUnsplashSearch:
    def test_missing_key_returns_empty(self):
        assert image_upgrader.UnsplashImageSearch(api_key="").search_images("q") == []
        assert image_upgrader.UnsplashImageSearch(api_key="").get_random_photos() == []

    def test_search_maps_fields_and_filters(self):
        StubClient.responses = [
            _response(
                json_data={
                    "results": [
                        {
                            "id": "id",
                            "links": {"html": "page"},
                            "user": {"name": "author", "username": "user"},
                            "urls": {"full": "full"},
                            "width": 1920,
                            "height": 1080,
                            "description": None,
                            "alt_description": "alt",
                            "likes": 200,
                        }
                    ]
                }
            )
        ]
        results = image_upgrader.UnsplashImageSearch(api_key="k").search_images(
            "q", orientation="landscape", color="blue", min_quality_score=0.5
        )
        assert results[0]["description"] == "alt"
        assert results[0]["photographer_username"] == "user"
        params = StubClient.requests[0][2]["params"]
        assert params["orientation"] == "landscape"
        assert params["color"] == "blue"

    def test_search_retry_and_errors(self):
        error = httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        StubClient.responses = [
            _response(status_code=429),
            error,
            _response(json_data={"results": []}),
        ]
        assert image_upgrader.UnsplashImageSearch(api_key="k").search_images("q") == []
        StubClient.responses = [_response(status_code=500)]
        assert image_upgrader.UnsplashImageSearch(api_key="k").search_images("q") == []
        StubClient.responses = [_response(json_data=[])]
        assert image_upgrader.UnsplashImageSearch(api_key="k").search_images("q") == []

    def test_random_photos_builds_params_and_skips_failures(self):
        error = httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        StubClient.responses = [
            _response(status_code=429),
            error,
            _response(json_data={"id": "p", "urls": {}, "links": {}}),
        ]
        results = image_upgrader.UnsplashImageSearch(api_key="k").get_random_photos(
            max_results=1, topic="nature", color="green", orientation="landscape"
        )
        assert results and results[0]["id"] == "p"
        params = StubClient.requests[-1][2]["params"]
        assert params["topics"] == ["nature"]
        assert params["color"] == "green"
        assert params["orientation"] == "landscape"

    def test_random_photos_gives_up_without_result(self):
        StubClient.responses = [
            _response(status_code=500),
            _response(status_code=500),
            _response(status_code=500),
        ]
        assert image_upgrader.UnsplashImageSearch(api_key="k").get_random_photos(max_results=1) == []

    def test_random_photos_unexpected_exception_is_logged(self):
        StubClient.responses = [_response(json_data=[])]
        assert image_upgrader.UnsplashImageSearch(api_key="k").get_random_photos(max_results=1) == []

    def test_quality_score(self):
        assert image_upgrader.UnsplashImageSearch._calculate_quality_score({}) == 0.0
        assert image_upgrader.UnsplashImageSearch._calculate_quality_score(
            {"width": 1920, "height": 1080, "likes": 200}
        ) == 0.673


class TestQualityChecker:
    def test_unreadable_image_is_reported(self, tmp_path):
        broken = tmp_path / "broken.jpg"
        broken.write_bytes(b"not an image")
        checker = image_upgrader.ImageQualityChecker()
        assert checker.check_resolution(str(broken))["width"] == 0
        assert checker.check_aspect_ratio(str(broken))["closest_match"] is None

    @pytest.mark.parametrize(
        ("size", "expected"),
        [((4000, 3000), "4:3"), ((1600, 900), "16:9"), ((3000, 2000), "3:2"), ((1000, 1000), "1:1")],
    )
    def test_aspect_ratio_matches_common_ratios(self, tmp_path, size, expected):
        path = tmp_path / "img.png"
        Image.new("RGB", size).save(path)
        result = image_upgrader.ImageQualityChecker().check_aspect_ratio(str(path))
        assert result["closest_match"] == expected
        assert result["deviation"] <= 0.15

    def test_suitable_image_has_no_reasons(self, tmp_path):
        path = tmp_path / "img.png"
        Image.new("RGB", (1920, 1080)).save(path)
        result = image_upgrader.ImageQualityChecker().is_suitable_for_pptx(str(path))
        assert result["suitable"] is True
        assert result["reasons"] == []

    def test_oversized_file_is_rejected(self, tmp_path, monkeypatch):
        path = tmp_path / "img.png"
        Image.new("RGB", (1920, 1080)).save(path)
        monkeypatch.setattr(Path, "stat", lambda self: type("S", (), {"st_size": 11 * 1024 * 1024})())
        result = image_upgrader.ImageQualityChecker().is_suitable_for_pptx(str(path))
        assert result["suitable"] is False
        assert any("文件过大" in reason for reason in result["reasons"])

    def test_non_standard_ratio_adds_reason_but_stays_suitable(self, tmp_path):
        path = tmp_path / "img.png"
        Image.new("RGB", (2400, 600)).save(path)
        result = image_upgrader.ImageQualityChecker().is_suitable_for_pptx(str(path))
        assert result["suitable"] is True
        assert any("纵横比不标准" in reason for reason in result["reasons"])


class TestDownloader:
    def test_download_image_success(self, tmp_path):
        StubClient.responses = [
            _response(content=b"image", headers={"content-type": "image/png"})
        ]
        target = tmp_path / "nested" / "img.png"
        assert image_upgrader.ImageDownloader().download_image(
            "https://example.com/a.png", str(target)
        )
        assert target.read_bytes() == b"image"

    def test_download_image_rejects_non_image(self, tmp_path):
        StubClient.responses = [_response(content=b"html", headers={"content-type": "text/html"})]
        assert not image_upgrader.ImageDownloader().download_image(
            "https://example.com/a", str(tmp_path / "a.png")
        )

    def test_download_image_http_and_network_errors(self, tmp_path):
        downloader = image_upgrader.ImageDownloader()
        StubClient.responses = [_response(status_code=404)]
        assert not downloader.download_image("https://example.com/a", str(tmp_path / "a.png"))
        StubClient.responses = [
            httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        ]
        assert not downloader.download_image("https://example.com/a", str(tmp_path / "a.png"))

    def test_download_image_write_failure(self, tmp_path, monkeypatch):
        StubClient.responses = [
            _response(content=b"image", headers={"content-type": "image/png"})
        ]
        monkeypatch.setattr(Path, "write_bytes", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
        assert not image_upgrader.ImageDownloader().download_image(
            "https://example.com/a", str(tmp_path / "a.png")
        )

    @pytest.mark.parametrize(
        ("target", "format", "expected_suffix"),
        [("out.bin", "PNG", ".png"), ("out.bin", "JPEG", ".jpg"), ("out.bin", "WEBP", ".webp")],
    )
    def test_download_and_convert_formats(self, tmp_path, target, format, expected_suffix):
        image = Image.new("RGB", (10, 10), "red")
        buffer = __import__("io").BytesIO()
        image.save(buffer, format="PNG")
        StubClient.responses = [_response(content=buffer.getvalue())]
        result = image_upgrader.ImageDownloader().download_and_convert(
            "https://example.com/a.png", str(tmp_path / target), format=format
        )
        assert result is True
        assert (tmp_path / target).with_suffix(expected_suffix).exists()

    def test_download_and_convert_converts_rgba_for_jpeg(self, tmp_path):
        image = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        buffer = __import__("io").BytesIO()
        image.save(buffer, format="PNG")
        StubClient.responses = [_response(content=buffer.getvalue())]
        target = tmp_path / "out.jpg"
        assert image_upgrader.ImageDownloader().download_and_convert(
            "https://example.com/a.png", str(target), format="JPEG"
        )
        assert Image.open(target).mode == "RGB"

    def test_download_and_convert_failure(self, tmp_path):
        StubClient.responses = [_response(content=b"not image")]
        assert not image_upgrader.ImageDownloader().download_and_convert(
            "https://example.com/a.png", str(tmp_path / "out.png")
        )


class TestAdvancedGenerator:
    def test_generate_with_style_success(self):
        StubClient.responses = [_response(json_data={"image_url": "https://cdn/x.png"})]
        result = image_upgrader.AdvancedImageGenerator().generate_with_style("cat", "flat")
        assert result["image_url"] == "https://cdn/x.png"
        assert result["prompt"] == "cat, flat"
        assert StubClient.requests[0][1] == "https://api.example.com/v1/generate"

    def test_generate_with_style_errors(self):
        generator = image_upgrader.AdvancedImageGenerator()
        StubClient.responses = [_response(status_code=500)]
        assert generator.generate_with_style("cat") is None
        StubClient.responses = [
            httpx.RequestError("boom", request=httpx.Request("GET", "https://example.com"))
        ]
        assert generator.generate_with_style("cat") is None

    def test_generate_batch_falls_back_when_loop_running(self, monkeypatch):
        generator = image_upgrader.AdvancedImageGenerator()
        monkeypatch.setattr(
            generator,
            "generate_with_style",
            lambda prompt: {"image_url": f"url-{prompt}"},
        )

        async def run():
            return generator.generate_batch(["a", "b"])

        results = asyncio.run(run())
        assert [item["prompt"] for item in results] == ["a", "b"]

    def test_generate_batch_uses_async_client(self, monkeypatch):
        generator = image_upgrader.AdvancedImageGenerator()

        class FakeAsyncResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"image_url": "https://cdn/x.png"}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, json):
                return FakeAsyncResponse()

        monkeypatch.setattr(image_upgrader.httpx, "AsyncClient", FakeAsyncClient)
        results = generator.generate_batch(["a", "b"], max_concurrent=1)
        assert len(results) == 2

    def test_generate_batch_exception_falls_back(self, monkeypatch):
        generator = image_upgrader.AdvancedImageGenerator()
        monkeypatch.setattr(
            generator, "generate_with_style", lambda prompt: {"image_url": "fallback"}
        )
        monkeypatch.setattr(
            image_upgrader.asyncio, "run", lambda coro: (_ for _ in ()).throw(RuntimeError("x"))
        )
        results = generator.generate_batch(["a"])
        assert results[0]["image_url"] == "fallback"

    def test_generate_variations_uses_batch(self, monkeypatch):
        generator = image_upgrader.AdvancedImageGenerator()
        captured = []
        monkeypatch.setattr(
            generator, "generate_batch", lambda prompts: captured.extend(prompts) or []
        )
        generator.generate_variations("cat", count=2)
        assert len(captured) == 2
        assert all("cat" in prompt for prompt in captured)


class TestImageStrategyBranches:
    def test_search_cache_round_trip_uses_same_key(self, cache, monkeypatch):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        monkeypatch.setattr(strategy, "_check_image_quality", lambda info: True)
        monkeypatch.setattr(
            strategy,
            "_search_concurrent",
            lambda query, order: _store_search_cache(cache, query, order),
        )
        first = strategy.get_best_image(["nature"])
        assert first["url"] == "u"
        monkeypatch.setattr(
            strategy, "_search_concurrent", lambda *_: (_ for _ in ()).throw(AssertionError("searched"))
        )
        cached = strategy.get_best_image(["nature"])
        assert cached["url"] == "u"

    def test_search_results_are_cached_under_lookup_key(self, cache):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        for name in ("_unsplash", "_pexels", "_pixabay"):
            getattr(strategy, name).search_images = lambda *a, **k: [
                {"quality_score": 0.9, "url": "u"}
            ]
        order = ["unsplash", "pexels", "pixabay"]
        results = strategy._search_concurrent("nature", order)
        lookup_key = cache.generate_cache_key("nature", "strategy", order="+".join(order))
        assert cache.get_search_results(lookup_key) == results

    def test_low_quality_cache_is_ignored(self, cache, monkeypatch):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        key = cache.generate_cache_key("q", "strategy", order="unsplash+pexels+pixabay")
        cache.set_search_results(key, [{"url": "u", "quality_score": 0.1}])
        monkeypatch.setattr(strategy, "_search_concurrent", lambda *_: [])
        result = strategy.get_best_image(["q"])
        assert result["source"] == "placeholder"

    def test_search_results_below_quality_fall_through_to_ai(self, cache, monkeypatch):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        monkeypatch.setattr(
            strategy, "_search_concurrent", lambda *_: [{"url": "u", "quality_score": 0.9}]
        )
        monkeypatch.setattr(strategy, "_check_image_quality", lambda info: False)
        monkeypatch.setattr(
            strategy._generator, "generate_with_style", lambda prompt: {"image_url": "ai"}
        )
        result = strategy.get_best_image(["q"], description="badge")
        assert result["source"] == "ai_generation"

    def test_ai_result_without_url_falls_back_to_placeholder(self, cache, monkeypatch):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        monkeypatch.setattr(strategy, "_search_concurrent", lambda *_: [])
        monkeypatch.setattr(strategy._generator, "generate_with_style", lambda prompt: {})
        result = strategy.get_best_image(["q"], description="badge")
        assert result["source"] == "placeholder"

    def test_preferred_source_ordering(self, tmp_path):
        strategy = image_upgrader.ImageStrategy(cache_manager=image_upgrader.ImageCacheManager(cache_dir=tmp_path / "c"))
        assert strategy._determine_preferred_source(["illustration"]) == "pixabay"
        assert strategy._determine_preferred_source([]) is None
        assert strategy._determine_preferred_source(["office"]) == "pexels"

    def test_search_concurrent_with_running_loop(self, cache):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        calls = []
        for name in ("_unsplash", "_pexels", "_pixabay"):
            service = getattr(strategy, name)
            service.search_images = lambda *a, **k: calls.append(a) or [{"quality_score": 0.5}]

        async def run():
            return strategy._search_concurrent("q", ["unsplash", "pexels", "pixabay"])

        results = asyncio.run(run())
        assert len(results) == 3
        assert len(calls) == 3

    def test_search_concurrent_handles_source_exception(self, cache):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        strategy._unsplash.search_images = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
        strategy._pexels.search_images = lambda *a, **k: [{"quality_score": 0.7, "url": "u"}]
        strategy._pixabay.search_images = lambda *a, **k: []

        async def run():
            return strategy._search_concurrent("q", ["unsplash", "pexels", "pixabay"])

        results = asyncio.run(run())
        assert len(results) == 1
        assert results[0]["source"] == "pexels"

    def test_check_image_quality_without_url(self, cache):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        assert strategy._check_image_quality({}) is False

    def test_check_image_quality_uses_cache(self, cache, tmp_path):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        image = tmp_path / "img.png"
        Image.new("RGB", (1920, 1080)).save(image)
        cached_path = cache.cache_image("https://example.com/a.png", image.read_bytes())
        assert strategy._check_image_quality({"web_url": "https://example.com/a.png"})
        assert cached_path.exists()

    def test_check_image_quality_downloads_and_caches(self, cache, tmp_path):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)
        image = tmp_path / "img.png"
        Image.new("RGB", (1920, 1080)).save(image)

        class Downloader:
            def download_image(self, url, path):
                Path(path).write_bytes(image.read_bytes())
                return True

        import app.utils.pptx.image_upgrader as module

        original = module.ImageDownloader
        module.ImageDownloader = Downloader
        try:
            assert strategy._check_image_quality({"web_url": "https://example.com/a.png"})
        finally:
            module.ImageDownloader = original

    def test_check_image_quality_download_failure(self, cache):
        strategy = image_upgrader.ImageStrategy(cache_manager=cache)

        class Downloader:
            def download_image(self, url, path):
                return False

        import app.utils.pptx.image_upgrader as module

        original = module.ImageDownloader
        module.ImageDownloader = Downloader
        try:
            assert strategy._check_image_quality({"web_url": "https://example.com/a.png"}) is False
        finally:
            module.ImageDownloader = original
