"""ChartGenerationNode 分支补测：参数校验、图形类型与异常路径。"""

import pytest

from app.utils.workflow.node_types import chart_generation
from app.utils.workflow.node_types.chart_generation import ChartGenerationNode


def _node(**params):
    base = {"chart_type": "bar", "title": "T", "data": {"A": 1}}
    base.update(params)
    return ChartGenerationNode("node", base)


def test_optional_params_defaults():
    assert _node().get_optional_params() == {
        "x_label": "",
        "y_label": "",
        "output_format": "png",
        "dpi": 100,
    }


def test_validate_params_missing_fields():
    errors = ChartGenerationNode("node", {}).validate_params()
    assert "Missing required parameter: chart_type" in errors
    assert "Missing required parameter: title" in errors
    assert "Missing required parameter: data" in errors


def test_validate_params_non_string_title():
    errors = _node(title=123).validate_params()
    assert "Parameter 'title' must be a string" in errors


def test_validate_params_data_must_be_dict_or_list():
    errors = _node(data="nope").validate_params()
    assert "Parameter 'data' must be a dict or list" in errors


@pytest.mark.parametrize("dpi", [71, 601, "100", None])
def test_validate_params_invalid_dpi(dpi):
    errors = _node(dpi=dpi).validate_params()
    assert "Parameter 'dpi' must be an integer between 72 and 600" in errors


@pytest.mark.asyncio
async def test_execute_scatter_and_histogram(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_generation.tempfile, "tempdir", str(tmp_path))

    scatter = await _node(
        chart_type="scatter", data={"x": [1, 2], "y": [3, 4]}, x_label="X", y_label="Y"
    ).execute({})
    assert scatter.success

    histogram = await _node(
        chart_type="histogram", data=[1, 2, 2, 3], x_label="Values"
    ).execute({})
    assert histogram.success

    chart_generation.cleanup_all_temp_files()


@pytest.mark.asyncio
async def test_execute_import_error_returns_error_result(monkeypatch):
    async def missing_dependency(*_args, **_kwargs):
        raise ImportError("no matplotlib")

    monkeypatch.setattr(ChartGenerationNode, "_generate_chart", missing_dependency)
    result = await _node().execute({})

    assert not result.success
    assert "matplotlib is required for chart generation" in result.error


@pytest.mark.asyncio
async def test_execute_generic_error_returns_error_result(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("bad data")

    monkeypatch.setattr(ChartGenerationNode, "_generate_chart", boom)
    result = await _node().execute({})

    assert not result.success
    assert "Chart generation failed" in result.error


@pytest.mark.asyncio
async def test_bar_with_list_data_and_labels():
    result = await _node(chart_type="bar", data=[1, 2, 3]).execute({})
    assert result.success
    chart_generation.cleanup_all_temp_files()


@pytest.mark.asyncio
async def test_bar_with_empty_list_skips_ylim():
    result = await _node(chart_type="bar", data=[]).execute({})
    assert result.success
    chart_generation.cleanup_all_temp_files()


@pytest.mark.asyncio
async def test_line_with_dict_data():
    result = await _node(chart_type="line", data={"a": 1, "b": 2}).execute({})
    assert result.success
    chart_generation.cleanup_all_temp_files()


@pytest.mark.asyncio
async def test_axis_labels_are_applied_when_provided():
    result = await _node(
        chart_type="bar", data={"A": 1}, x_label="X", y_label="Y"
    ).execute({})
    assert result.success
    chart_generation.cleanup_all_temp_files()


@pytest.mark.asyncio
async def test_invalid_bar_data_raises_inside_plot_helper():
    node = _node()
    with pytest.raises(ValueError, match="bar chart"):
        await node._plot_bar(None, "bad", "", "")


@pytest.mark.asyncio
async def test_invalid_line_data_raises_inside_plot_helper():
    node = _node()
    with pytest.raises(ValueError, match="line chart"):
        await node._plot_line(None, "bad", "", "")


@pytest.mark.asyncio
async def test_invalid_scatter_data_raises_inside_plot_helper():
    node = _node()
    with pytest.raises(ValueError, match="scatter chart"):
        await node._plot_scatter(None, [1, 2, 3], "", "")


@pytest.mark.asyncio
async def test_invalid_histogram_data_raises_inside_plot_helper():
    node = _node()
    with pytest.raises(ValueError, match="histogram"):
        await node._plot_histogram(None, {"other": 1}, "")


@pytest.mark.asyncio
async def test_scatter_list_of_two_and_histogram_dict_values():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    try:
        node = _node(chart_type="scatter")
        await node._plot_scatter(ax, [[1, 2], [3, 4]], "", "")
        await node._plot_histogram(ax, {"values": [1, 2, 3]}, "")
    finally:
        plt.close(fig)


def test_font_configuration_failure_sets_flag(monkeypatch):
    class BrokenManager:
        @staticmethod
        def addfont(_path):
            raise RuntimeError("font boom")

    import matplotlib.font_manager as fm

    monkeypatch.setattr(chart_generation, "_fonts_configured", False)
    monkeypatch.setattr(chart_generation.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(fm.fontManager, "addfont", BrokenManager.addfont)
    monkeypatch.setattr(fm, "FontProperties", lambda *a, **k: type(
        "FP", (), {"get_name": lambda self: "x"}
    )())

    chart_generation._configure_fonts()
    assert chart_generation._fonts_configured is True


def test_cleanup_swallows_unlink_errors(monkeypatch):
    chart_generation._temp_files.add("/nonexistent/chart.png")

    def boom(_path):
        raise OSError("locked")

    monkeypatch.setattr(chart_generation.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(chart_generation.os, "unlink", boom)

    chart_generation.cleanup_all_temp_files()
    assert chart_generation._temp_files == set()


def test_cleanup_skips_missing_files(monkeypatch):
    chart_generation._temp_files.add("/missing/chart.png")
    monkeypatch.setattr(chart_generation.os.path, "exists", lambda _p: False)

    chart_generation.cleanup_all_temp_files()

    assert chart_generation._temp_files == set()


def test_validate_params_accepts_explicit_valid_format_and_dpi():
    errors = _node(output_format="svg", dpi=200).validate_params()
    assert errors == []


@pytest.mark.asyncio
async def test_unknown_chart_type_still_saves_figure():
    result = await _node(chart_type="unknown").execute({})
    assert result.success
    chart_generation.cleanup_all_temp_files()
