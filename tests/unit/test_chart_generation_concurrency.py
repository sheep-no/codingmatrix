"""图表生成节点的并发缺陷回归。

CH1：`_generate_chart` 在 `plt.subplots` 与保存之间 `await`，pyplot 的
「当前图形」可能被并发协程替换，旧实现用 `plt.savefig` 会保存错图。
CH2：`_temp_files` 为模块级集合，注册/清理无锁，且保存失败时残留半成品。
CH3：`_configure_fonts` 的 `_fonts_configured` 标志存在 check-then-act 竞态。
"""

import os
import threading
import time

import pytest


def _chart_module():
    from app.utils.workflow.node_types import chart_generation

    return chart_generation


@pytest.mark.asyncio
async def test_saves_own_figure_not_pyplot_current(monkeypatch):
    """CH1：保存的必须是本节点创建的图形，而非 pyplot 的当前图形。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    cg = _chart_module()
    node = cg.ChartGenerationNode(
        "test",
        {
            "chart_type": "bar",
            "title": "Concurrency",
            "data": {"A": 1, "B": 2},
        },
    )

    real_subplots = plt.subplots

    def subplots_with_rogue(*args, **kwargs):
        fig, ax = real_subplots(*args, **kwargs)
        # 模拟并发协程在 await 期间新建并抢走 pyplot 当前图形
        real_subplots(figsize=(4, 3))
        return fig, ax

    monkeypatch.setattr(plt, "subplots", subplots_with_rogue)

    chart_path = None
    try:
        result = await node.execute({})
        assert result.success
        chart_path = result.data["chart_path"]
        with Image.open(chart_path) as image:
            # 本节点图形 figsize=(10,6)、dpi=100；被抢走的图形为 (4,3)
            assert image.size == (1000, 600)
    finally:
        plt.close("all")
        cg.cleanup_all_temp_files()
        if chart_path and os.path.exists(chart_path):
            os.unlink(chart_path)


@pytest.mark.asyncio
async def test_failed_save_reclaims_temp_file(monkeypatch):
    """CH2：保存抛异常时，半成品既不留盘也不残留在注册集合。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    cg = _chart_module()
    node = cg.ChartGenerationNode(
        "test",
        {
            "chart_type": "bar",
            "title": "Failure",
            "data": {"A": 1},
        },
    )

    created = []
    real_ntf = cg.tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        handle = real_ntf(*args, **kwargs)
        created.append(handle.name)
        return handle

    def explode(*args, **kwargs):
        raise RuntimeError("savefig boom")

    monkeypatch.setattr(cg.tempfile, "NamedTemporaryFile", tracking_ntf)
    monkeypatch.setattr(Figure, "savefig", explode)
    before = set(cg._temp_files)

    try:
        result = await node.execute({})
        assert not result.success
        assert created, "未观察到临时文件创建"
        assert not os.path.exists(created[0])
        assert cg._temp_files == before
    finally:
        plt.close("all")
        cg.cleanup_all_temp_files()


def test_cleanup_survives_concurrent_registration(monkeypatch, tmp_path):
    """CH2：清理过程中并发注册不会抛出「集合遍历中被修改」。"""
    cg = _chart_module()

    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    cg._temp_files.update({str(first), str(second)})

    injected = {"done": False}
    real_unlink = os.unlink

    def unlink_and_inject(path):
        real_unlink(path)
        if not injected["done"]:
            injected["done"] = True
            cg._temp_files.add(str(tmp_path / "c.png"))

    monkeypatch.setattr(cg.os, "unlink", unlink_and_inject)

    try:
        cg.cleanup_all_temp_files()
        assert injected["done"]
        # 快照语义：清理只处理快照内的文件，并发新注册的条目保留
        assert str(tmp_path / "c.png") in cg._temp_files
    finally:
        cg._temp_files.clear()


def test_font_configuration_is_serialized(monkeypatch):
    """CH3：多线程首调字体配置时只注册一次。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    cg = _chart_module()

    calls = []
    real_addfont = fm.fontManager.addfont

    def slow_addfont(path):
        calls.append(path)
        time.sleep(0.05)
        real_addfont(path)

    monkeypatch.setattr(fm.fontManager, "addfont", slow_addfont)
    monkeypatch.setattr(cg, "_fonts_configured", False)
    saved_family = plt.rcParams["font.family"]
    saved_sans = list(plt.rcParams["font.sans-serif"])

    try:
        threads = [threading.Thread(target=cg._configure_fonts) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(calls) == 1
    finally:
        plt.rcParams["font.family"] = saved_family
        plt.rcParams["font.sans-serif"] = saved_sans
