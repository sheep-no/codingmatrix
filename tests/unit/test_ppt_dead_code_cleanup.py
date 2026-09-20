"""AJP12：aiGeneratorPptx 中零消费的图片搜索/下载死代码已删除。

这些符号在模块内定义后无任何调用方，且各自持有与真实实现重复的
路径常量与初始化单例，保留会误导后续维护。
"""

import app.api.v1.aiGeneratorPptx as pptx_module


def test_dead_image_helpers_removed():
    for name in (
        "search_image_url",
        "download_image",
        "get_image_for_slide",
        "get_image_search_manager",
        "IMAGE_CACHE_DIR",
        "_safe_download_image",
        "_MAX_IMAGE_DOWNLOAD_BYTES",
        "_image_search_manager",
        "ImageSearchManager",
    ):
        assert not hasattr(pptx_module, name), f"{name} 应已删除"
