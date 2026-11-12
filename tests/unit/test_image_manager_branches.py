"""ImageManager 全分支回归：外部图片源、下载转换、占位符与图标生成。"""

import io
import importlib

import pytest
from PIL import Image

im = importlib.import_module("app.utils.visual.image_manager")


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *, post_response=None, get_response=None, raise_on=None):
        self._post_response = post_response
        self._get_response = get_response
        self._raise_on = raise_on

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, *args, **kwargs):
        if self._raise_on == "post":
            raise RuntimeError("post boom")
        return self._post_response

    async def get(self, *args, **kwargs):
        if self._raise_on == "get":
            raise RuntimeError("get boom")
        return self._get_response


def _client_factory(**kwargs):
    return lambda *args, **client_kwargs: _FakeClient(**kwargs)


def _png_bytes(color=(10, 20, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def manager(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(im, "IMAGE_CACHE_DIR", cache_dir)
    return im.ImageManager()


def test_cache_key_and_filename_are_stable(manager):
    key1 = manager._generate_cache_key("描述", ["a", "b"])
    key2 = manager._generate_cache_key("描述", ["a", "b"])
    assert key1 == key2
    assert len(key1) == 32

    filename = manager._generate_filename("a b/c*d?_ 长" * 20)
    assert filename.endswith(".png")
    assert "/" not in filename
    assert "*" not in filename
    assert len(filename.rsplit("_", 1)[0]) <= 30


@pytest.mark.asyncio
async def test_cache_hit_returns_same_asset(manager):
    async def _gaopin(keywords):
        return im.ImageAsset(source=im.ImageSource.LOCAL, local_path="/tmp/x.png")

    manager._search_gaopin = _gaopin
    first = await manager.get_image_for_slide("photo", "d", ["k"], 1)
    manager.generated_count = 0
    second = await manager.get_image_for_slide("photo", "d", ["k"], 2)
    assert second is first
    assert manager.generated_count == 0


@pytest.mark.asyncio
async def test_gaopin_success_and_failure_paths(manager, monkeypatch):
    async def _download(url, description):
        return "/tmp/gaopin.png"

    manager._download_image = _download
    payload = {
        "return_code": "000000",
        "return_data": {"data": [{"thumbnailUrl300C": "https://img/x.png"}]},
    }
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(post_response=_FakeResponse(payload=payload))
    )

    asset = await manager._search_gaopin(["施工", "安全"])
    assert asset is not None
    assert asset.source == im.ImageSource.LOCAL
    assert asset.local_path == "/tmp/gaopin.png"

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(post_response=_FakeResponse(payload={"return_code": "x"})),
    )
    assert await manager._search_gaopin([]) is None

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            post_response=_FakeResponse(
                payload={"return_code": "000000", "return_data": {"data": []}}
            )
        ),
    )
    assert await manager._search_gaopin(["k"]) is None

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            post_response=_FakeResponse(
                payload={
                    "return_code": "000000",
                    "return_data": {"data": [{"thumbnailUrl300C": ""}]},
                }
            )
        ),
    )
    assert await manager._search_gaopin(["k"]) is None

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(post_response=_FakeResponse(status_code=500)),
    )
    assert await manager._search_gaopin(["k"]) is None

    monkeypatch.setattr(im.httpx, "AsyncClient", _client_factory(raise_on="post"))
    assert await manager._search_gaopin(["k"]) is None


@pytest.mark.asyncio
async def test_gaopin_download_failure_warns(manager, monkeypatch):
    async def _download(url, description):
        return None

    manager._download_image = _download
    payload = {
        "return_code": "000000",
        "return_data": {"data": [{"thumbnailUrl300C": "https://img/x.png"}]},
    }
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(post_response=_FakeResponse(payload=payload))
    )
    assert await manager._search_gaopin(["k"]) is None


@pytest.mark.asyncio
async def test_kolors_success_non_200_missing_url_and_exception(manager, monkeypatch):
    async def _download(url, description):
        return "/tmp/kolors.png"

    manager._download_image = _download
    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            post_response=_FakeResponse(payload={"data": [{"url": "https://img/y.png"}]})
        ),
    )
    asset = await manager._generate_with_kolors("d", ["k"], "style")
    assert asset.source == im.ImageSource.KOLORS
    assert asset.local_path == "/tmp/kolors.png"

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(post_response=_FakeResponse(status_code=500, text="bad")),
    )
    assert await manager._generate_with_kolors("d", ["k"], "style") is None

    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(post_response=_FakeResponse(payload={}))
    )
    assert await manager._generate_with_kolors("d", ["k"], "style") is None

    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            post_response=_FakeResponse(payload={"data": [{"url": "https://img/y.png"}]})
        ),
    )
    manager._download_image = lambda url, description: _none()
    assert await manager._generate_with_kolors("d", ["k"], "style") is None

    monkeypatch.setattr(im.httpx, "AsyncClient", _client_factory(raise_on="post"))
    assert await manager._generate_with_kolors("d", ["k"], "style") is None


async def _none():
    return None


@pytest.mark.asyncio
async def test_unsplash_success_status_and_exception(manager, monkeypatch):
    async def _save(content, keyword):
        return f"/tmp/{keyword}.jpg"

    manager._save_image_bytes = _save
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(get_response=_FakeResponse(content=b"img"))
    )
    asset = await manager._search_unsplash(["water", "safety"])
    assert asset.source == im.ImageSource.UNSPLASH
    assert asset.description.startswith("Unsplash:")

    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(get_response=_FakeResponse(status_code=404))
    )
    assert (await manager._search_unsplash([])).source == im.ImageSource.NONE

    monkeypatch.setattr(im.httpx, "AsyncClient", _client_factory(raise_on="get"))
    assert (await manager._search_unsplash(["k"])).source == im.ImageSource.NONE


@pytest.mark.asyncio
async def test_unsplash_save_failure_returns_none_asset(manager, monkeypatch):
    async def _save(content, keyword):
        return None

    manager._save_image_bytes = _save
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(get_response=_FakeResponse(content=b"img"))
    )
    assert (await manager._search_unsplash(["k"])).source == im.ImageSource.NONE


@pytest.mark.asyncio
async def test_save_image_bytes_sanitizes_keyword_path(manager, monkeypatch):
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(get_response=_FakeResponse(content=b"img"))
    )
    asset = await manager._search_unsplash(["../../escape"])
    assert asset.source == im.ImageSource.UNSPLASH
    saved = im.Path(asset.local_path).resolve()
    assert im.IMAGE_CACHE_DIR.resolve() in saved.parents


@pytest.mark.asyncio
async def test_download_image_plain_and_webp_conversion(manager, monkeypatch):
    content = _png_bytes()
    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            get_response=_FakeResponse(
                content=content, headers={"content-type": "image/png"}
            )
        ),
    )
    path = await manager._download_image("https://img/x.png", "plain")
    assert path is not None
    assert path.endswith(".png")

    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), (1, 2, 3, 200)).save(buf, "WEBP")
    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            get_response=_FakeResponse(
                content=buf.getvalue(), headers={"content-type": "image/webp"}
            )
        ),
    )
    path = await manager._download_image("https://img/y.webp", "webp")
    assert path is not None
    assert path.endswith(".png")
    assert Image.open(path).mode == "RGB"

    rgb_buf = io.BytesIO()
    Image.new("RGB", (4, 4), (9, 9, 9)).save(rgb_buf, "WEBP")
    monkeypatch.setattr(
        im.httpx,
        "AsyncClient",
        _client_factory(
            get_response=_FakeResponse(
                content=rgb_buf.getvalue(), headers={"content-type": "image/webp"}
            )
        ),
    )
    path = await manager._download_image("https://img/z.webp", "webp-rgb")
    assert path is not None
    assert Image.open(path).mode == "RGB"


@pytest.mark.asyncio
async def test_download_image_non_200_and_exception(manager, monkeypatch):
    monkeypatch.setattr(
        im.httpx, "AsyncClient", _client_factory(get_response=_FakeResponse(status_code=404))
    )
    assert await manager._download_image("https://img/x.png", "d") is None

    monkeypatch.setattr(im.httpx, "AsyncClient", _client_factory(raise_on="get"))
    assert await manager._download_image("https://img/x.png", "d") is None


@pytest.mark.asyncio
async def test_save_image_bytes_success_and_failure(manager, monkeypatch):
    path = await manager._save_image_bytes(b"abc", "kw")
    assert path is not None
    assert im.IMAGE_CACHE_DIR.exists()

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _boom)
    assert await manager._save_image_bytes(b"abc", "kw") is None


@pytest.mark.parametrize("keywords", [["warning"], ["water"], ["safety"], ["danger"], ["info"], []])
def test_create_placeholder_schemes(manager, keywords):
    asset = manager._create_placeholder("desc", keywords)
    assert asset.source == im.ImageSource.LOCAL
    assert asset.local_path is not None
    assert asset.description == "占位符: desc"


def test_create_placeholder_failure_returns_none_asset(manager, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("no image lib")

    monkeypatch.setattr(im.Image, "new", _boom)
    asset = manager._create_placeholder("desc", ["warning"])
    assert asset.source == im.ImageSource.NONE


@pytest.mark.asyncio
async def test_generate_icon_success_and_failure(manager, monkeypatch):
    path = await manager.generate_icon("warning")
    assert path is not None
    assert path.endswith(".png")

    monkeypatch.setattr(im.Image, "new", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert await manager.generate_icon("warning") is None


def test_clear_cache_and_stats(manager):
    manager.cache["k"] = im.ImageAsset(source=im.ImageSource.LOCAL)
    manager.generated_count = 2
    stats = manager.get_cache_stats()
    assert stats["cached_images"] == 1
    assert stats["generated_count"] == 2
    manager.clear_cache()
    assert manager.cache == {}
    assert manager.generated_count == 0


@pytest.mark.asyncio
async def test_fallbacks_log_and_use_placeholder(manager, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("source down")

    monkeypatch.setattr(manager, "_search_gaopin", _boom)
    monkeypatch.setattr(manager, "_generate_with_kolors", _boom)
    monkeypatch.setattr(manager, "_search_unsplash", _boom)

    asset = await manager.get_image_for_slide("illustration", "d", ["safety"], 5)
    assert asset.source == im.ImageSource.LOCAL
    assert manager.generated_count == 0

    photo = await manager.get_image_for_slide("photo", "d2", ["x"], 6)
    assert photo.source == im.ImageSource.LOCAL


@pytest.mark.asyncio
async def test_none_source_from_strategy_is_not_cached(manager, monkeypatch):
    async def _none_source(*args, **kwargs):
        return im.ImageAsset(source=im.ImageSource.NONE)

    monkeypatch.setattr(manager, "_search_gaopin", _none_source)
    monkeypatch.setattr(manager, "_generate_with_kolors", _none_source)

    def _placeholder(description, keywords):
        return im.ImageAsset(
            source=im.ImageSource.LOCAL, local_path="/tmp/p.png", description=description
        )

    monkeypatch.setattr(manager, "_create_placeholder", _placeholder)
    asset = await manager.get_image_for_slide("illustration", "d", ["k"], 7)
    assert asset.source == im.ImageSource.LOCAL
    assert manager.generated_count == 0


@pytest.mark.asyncio
async def test_placeholder_failure_returns_none_asset_without_cache(manager, monkeypatch):
    async def _none_source(*args, **kwargs):
        return im.ImageAsset(source=im.ImageSource.NONE)

    monkeypatch.setattr(manager, "_search_gaopin", _none_source)
    monkeypatch.setattr(manager, "_create_placeholder", lambda d, k: im.ImageAsset(source=im.ImageSource.NONE))

    asset = await manager.get_image_for_slide("illustration", "d", ["k"], 8)
    assert asset.source == im.ImageSource.NONE
    assert manager.cache == {}


@pytest.mark.asyncio
async def test_quota_exhausted_short_circuits_to_placeholder(manager, monkeypatch):
    manager.generated_count = manager.max_generations_per_ppt

    async def _boom(*args, **kwargs):
        raise AssertionError("配额用尽后不应调用外部策略")

    monkeypatch.setattr(manager, "_search_gaopin", _boom)
    asset = await manager.get_image_for_slide("illustration", "d", ["k"], 9)
    assert asset.source == im.ImageSource.LOCAL
    assert manager.generated_count == manager.max_generations_per_ppt


@pytest.mark.asyncio
async def test_kolors_and_unsplash_success_through_main_flow(manager, monkeypatch):
    async def _gaopin(keywords):
        return None

    async def _kolors(description, keywords, style):
        return im.ImageAsset(
            source=im.ImageSource.KOLORS, local_path="/tmp/k.png", keywords=keywords
        )

    monkeypatch.setattr(manager, "_search_gaopin", _gaopin)
    monkeypatch.setattr(manager, "_generate_with_kolors", _kolors)

    asset = await manager.get_image_for_slide("illustration", "插图", ["k"], 10)
    assert asset.source == im.ImageSource.KOLORS
    assert manager.generated_count == 1

    async def _none_kolors(description, keywords, style):
        return im.ImageAsset(source=im.ImageSource.NONE)

    async def _unsplash(keywords):
        return im.ImageAsset(
            source=im.ImageSource.UNSPLASH, local_path="/tmp/u.jpg", keywords=keywords
        )

    manager2 = im.ImageManager()
    monkeypatch.setattr(manager2, "_search_gaopin", _gaopin)
    monkeypatch.setattr(manager2, "_generate_with_kolors", _none_kolors)
    monkeypatch.setattr(manager2, "_search_unsplash", _unsplash)
    asset = await manager2.get_image_for_slide("photo", "照片", ["k"], 11)
    assert asset.source == im.ImageSource.UNSPLASH
