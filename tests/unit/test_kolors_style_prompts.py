"""KOL5：风格 prompt 只有一条动态读取路径。

原先模块导入时还求值了一份 `STYLE_PROMPTS` 快照（无任何引用），
自定义 skill 风格更新后该副本永不过期，属易误导的死代码。
"""


def test_get_style_prompts_reflects_custom_styles(monkeypatch):
    from app.api.v1 import kolors_api

    monkeypatch.setattr(
        kolors_api, "_load_custom_image_styles", lambda: {"my_style": "自定义风格"}
    )

    styles = kolors_api.get_style_prompts()

    assert styles["my_style"] == "自定义风格"
    assert "realistic" in styles


def test_no_stale_module_level_snapshot():
    from app.api.v1 import kolors_api

    assert not hasattr(kolors_api, "STYLE_PROMPTS")
