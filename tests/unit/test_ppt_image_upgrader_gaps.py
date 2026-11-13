"""Remaining branch coverage for app/utils/pptx/image_upgrader.py."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image

import app.utils.pptx.image_upgrader as image_upgrader


def _response(*, json_data=None, status_code=200, headers=None):
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(
        status_code=status_code,
        json=json_data if json_data is not None else {},
        headers=headers or {},
        request=request,
    )


def _request_error():
    return httpx.RequestError(
        "boom", request=httpx.Request("GET", "https://example.com")
    )


class StubClient:
    responses = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        item = type(self).responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _patch_transport(monkeypatch):
    StubClient.responses = []
    monkeypatch.setattr(image_upgrader.httpx, "Client", StubClient)
    return None


@pytest.fixture
def cache(tmp_path):
    return image_upgrader.ImageCacheManager(cache_dir=tmp_path / "cache")


# --- cache eviction / clear_expired ---


def test_enforce_size_limit_stops_once_under_threshold(tmp_path):
    manager = image_upgrader.ImageCacheManager(
        cache_dir=tmp_path / "cache", max_size_mb=0
    )
    # max_size_mb=0 时上限为 0，无法在中途降到阈值以下；
    # 这里直接把上限设为 10 字节，删除最旧文件后即可 break。
    manager._max_size_bytes = 10
    first = tmp_path / "cache" / "old.jpg"
    second = tmp_path / "cache" / "new.jpg"
    first.write_bytes(b"x" * 8)
    second.write_bytes(b"y" * 8)
    import os

    os.utime(first, (1000, 1000))
    os.utime(second, (2000, 2000))
    manager._enforce_size_limit()
    assert not first.exists()
    assert second.exists()


def test_clear_expired_skips_directories_and_fresh_files(cache):
    nested = cache._cache_dir / "nested"
    nested.mkdir()
    fresh = cache._cache_dir / "fresh.jpg"
    fresh.write_bytes(b"x")
    assert cache.clear_expired() == 0
    assert nested.exists()
    assert fresh.exists()


# --- Pexels curated endpoint ---


def test_pexels_curated_non_429_returns_empty():
    StubClient.responses = [_response(status_code=500)]
    assert image_upgrader.PexelsImageSearch(api_key="k").get_random_photo() == []


def test_pexels_curated_request_errors_exhaust_retries():
    StubClient.responses = [_request_error(), _request_error(), _request_error()]
    assert image_upgrader.PexelsImageSearch(api_key="k").get_random_photo() == []


def test_pexels_curated_payload_exception_returns_empty():
    StubClient.responses = [_response(json_data=[])]
    assert image_upgrader.PexelsImageSearch(api_key="k").get_random_photo() == []


# --- Pixabay / Unsplash request error exhaustion ---


def test_pixabay_request_errors_exhaust_retries():
    StubClient.responses = [_request_error(), _request_error(), _request_error()]
    assert image_upgrader.PixabayImageSearch(api_key="k").search_images("q") == []


def test_unsplash_request_errors_exhaust_retries():
    StubClient.responses = [_request_error(), _request_error(), _request_error()]
    assert image_upgrader.UnsplashImageSearch(api_key="k").search_images("q") == []


def test_unsplash_random_request_errors_exhaust_retries():
    StubClient.responses = [_request_error(), _request_error(), _request_error()]
    assert image_upgrader.UnsplashImageSearch(api_key="k").get_random_photos(max_results=1) == []


# --- quality score ratio bands ---


def test_unsplash_quality_score_mid_ratio_band():
    score = image_upgrader.UnsplashImageSearch._calculate_quality_score(
        {"width": 1500, "height": 1000, "likes": 200}
    )
    # megapixels 1.5 -> 0.125, likes -> 0.3, ratio 1.5 -> 0.1
    assert score == pytest.approx(0.525)


# --- aspect ratio height zero ---


def test_aspect_ratio_zero_height_returns_zero(monkeypatch, tmp_path):
    image = tmp_path / "zero.png"
    image.write_bytes(b"x")

    class Img:
        size = (100, 0)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(Image, "open", lambda path: Img())
    result = image_upgrader.ImageQualityChecker().check_aspect_ratio(str(image))
    assert result["ratio"] == "0:0"
    assert result["deviation"] == 1.0


# --- batch generation single failure ---


def test_generate_batch_single_prompt_failure_returns_empty(monkeypatch):
    generator = image_upgrader.AdvancedImageGenerator()

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            raise RuntimeError("upstream down")

    monkeypatch.setattr(image_upgrader.httpx, "AsyncClient", FakeAsyncClient)
    assert generator.generate_batch(["a"]) == []


# --- strategy source order branches ---


@pytest.mark.parametrize("keywords", [["office"], ["illustration"]])
def test_get_best_image_pexels_and_pixabay_orders(cache, monkeypatch, keywords):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)
    seen = {}

    def search(query, order):
        seen["order"] = order
        return [{"url": "u", "quality_score": 0.9}]

    monkeypatch.setattr(strategy, "_search_concurrent", search)
    monkeypatch.setattr(strategy, "_check_image_quality", lambda info: True)
    result = strategy.get_best_image(keywords)
    assert result["url"] == "u"
    assert seen["order"][0] == strategy._determine_preferred_source(keywords)


# --- _search_concurrent fallbacks ---


def test_search_concurrent_unknown_source_returns_empty(cache):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)
    assert strategy._search_concurrent("q", ["unknown"]) == []


def test_search_concurrent_running_loop_unknown_source(cache):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)

    async def run():
        return strategy._search_concurrent("q", ["unknown"])

    assert asyncio.run(run()) == []


def test_search_concurrent_falls_back_when_asyncio_run_raises(cache, monkeypatch):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)
    calls = []

    def boom(coro):
        coro.close()
        raise RuntimeError("loop broken")

    monkeypatch.setattr(image_upgrader.asyncio, "run", boom)
    strategy._unsplash.search_images = lambda *a, **k: calls.append("unsplash") or [
        {"quality_score": 0.9, "url": "u"}
    ]
    strategy._pexels.search_images = lambda *a, **k: calls.append("pexels") or []
    strategy._pixabay.search_images = lambda *a, **k: calls.append("pixabay") or []
    results = strategy._search_concurrent("q", ["unsplash", "unknown"])
    assert calls == ["unsplash"]
    assert results[0]["source"] == "unsplash"


def test_search_concurrent_skips_exception_entries(cache):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)
    strategy._unsplash.search_images = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("down")
    )
    results = strategy._search_concurrent("q", ["unsplash"])
    assert results == []


# --- check image quality without cache ---


def test_check_image_quality_without_cache_downloads(cache, tmp_path):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)
    strategy._cache = None
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
        info = {"web_url": "https://example.com/a.png"}
        result = strategy._check_image_quality(info)
        assert result is True
    finally:
        module.ImageDownloader = original


def test_cache_clear_expired_removes_only_old_entries(cache):
    key = cache.generate_cache_key("q", "src")
    cache.set_search_results(key, [{"url": "u"}])
    cache._search_cache[key]["cached_at"] = datetime.now() - cache._ttl - timedelta(hours=1)
    fresh_key = cache.generate_cache_key("fresh", "src")
    cache.set_search_results(fresh_key, [{"url": "v"}])
    assert cache.clear_expired() == 0
    assert key not in cache._search_cache
    assert fresh_key in cache._search_cache


# --- quality filtering and score thresholds ---


def test_pixabay_filters_low_quality_hit():
    StubClient.responses = [
        _response(json_data={"hits": [{"id": 1, "imageWidth": 10, "imageHeight": 10}]})
    ]
    results = image_upgrader.PixabayImageSearch(api_key="k").search_images(
        "q", min_quality_score=0.9
    )
    assert results == []


def test_pixabay_quality_score_below_hd():
    score = image_upgrader.PixabayImageSearch._calculate_quality_score(
        {"imageWidth": 100, "imageHeight": 100}
    )
    assert score < 0.2


def test_unsplash_filters_low_quality_photo():
    StubClient.responses = [
        _response(json_data={"results": [{"id": "p", "width": 10, "height": 10}]})
    ]
    results = image_upgrader.UnsplashImageSearch(api_key="k").search_images(
        "q", min_quality_score=0.9
    )
    assert results == []


# --- generator batch falsy results ---


def test_generate_batch_running_loop_skips_falsy_results(monkeypatch):
    generator = image_upgrader.AdvancedImageGenerator()
    monkeypatch.setattr(generator, "generate_with_style", lambda prompt: None)

    async def run():
        return generator.generate_batch(["a", "b"])

    assert asyncio.run(run()) == []


def test_generate_batch_fallback_skips_falsy_results(monkeypatch):
    generator = image_upgrader.AdvancedImageGenerator()
    monkeypatch.setattr(generator, "generate_with_style", lambda prompt: None)
    monkeypatch.setattr(
        image_upgrader.asyncio,
        "run",
        lambda coro: (_ for _ in ()).throw(RuntimeError("x")),
    )
    assert generator.generate_batch(["a"]) == []


# --- strategy serial fallback with all sources and errors ---


def test_search_concurrent_fallback_covers_all_sources_and_errors(cache, monkeypatch):
    strategy = image_upgrader.ImageStrategy(cache_manager=cache)

    def boom(coro):
        coro.close()
        raise RuntimeError("loop broken")

    monkeypatch.setattr(image_upgrader.asyncio, "run", boom)

    def unsplash(*a, **k):
        return [{"quality_score": 0.9, "url": "u"}]

    def pexels(*a, **k):
        raise RuntimeError("pexels down")

    def pixabay(*a, **k):
        return []

    strategy._unsplash.search_images = unsplash
    strategy._pexels.search_images = pexels
    strategy._pixabay.search_images = pixabay

    results = strategy._search_concurrent(
        "q", ["unsplash", "pexels", "pixabay", "unknown"]
    )
    assert [item["source"] for item in results] == ["unsplash"]
