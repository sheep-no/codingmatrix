"""visual 包图片管理器的缓存目录与配额计数回归。

覆盖 visual_package.md 中仍存续的缺陷：
- VPX10：缓存目录改为按需创建，导入模块不再产生文件系统副作用
- VPX11：占位符降级不消耗 max_generations_per_ppt 配额
"""

import importlib

import pytest

# 包 __init__ 导出的 image_manager 是单例，这里需要模块本身
im = importlib.import_module("app.utils.visual.image_manager")


@pytest.mark.asyncio
async def test_placeholder_does_not_consume_generation_quota(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(im, "IMAGE_CACHE_DIR", cache_dir)
    assert not cache_dir.exists()

    manager = im.ImageManager()

    async def _no_asset(*args, **kwargs):
        return None

    monkeypatch.setattr(manager, "_search_gaopin", _no_asset)
    monkeypatch.setattr(manager, "_generate_with_kolors", _no_asset)

    asset = await manager.get_image_for_slide(
        image_type="illustration",
        description="安全培训",
        keywords=["safety"],
        slide_index=1,
    )

    assert asset.source == im.ImageSource.LOCAL
    assert manager.generated_count == 0
    # VPX10：目录由首次写入按需创建
    assert cache_dir.exists()
    assert str(cache_dir) in asset.local_path


@pytest.mark.asyncio
async def test_real_asset_consumes_generation_quota(monkeypatch, tmp_path):
    monkeypatch.setattr(im, "IMAGE_CACHE_DIR", tmp_path / "cache")
    manager = im.ImageManager()

    async def _fake_search(keywords):
        return im.ImageAsset(
            source=im.ImageSource.KOLORS,
            local_path="/tmp/fake.png",
            description="fake",
            keywords=keywords,
        )

    monkeypatch.setattr(manager, "_search_gaopin", _fake_search)

    asset = await manager.get_image_for_slide(
        image_type="illustration",
        description="架构图",
        keywords=["architecture"],
        slide_index=2,
    )

    assert asset.source == im.ImageSource.KOLORS
    assert manager.generated_count == 1


@pytest.mark.asyncio
async def test_quota_exhausted_returns_placeholder_without_increment(monkeypatch, tmp_path):
    monkeypatch.setattr(im, "IMAGE_CACHE_DIR", tmp_path / "cache")
    manager = im.ImageManager()
    manager.generated_count = manager.max_generations_per_ppt

    async def _should_not_run(*args, **kwargs):
        raise AssertionError("配额用尽后不应再调用外部获取策略")

    monkeypatch.setattr(manager, "_search_gaopin", _should_not_run)

    asset = await manager.get_image_for_slide(
        image_type="illustration",
        description="超额",
        keywords=["overflow"],
        slide_index=3,
    )

    assert asset.source == im.ImageSource.LOCAL
    assert manager.generated_count == manager.max_generations_per_ppt
