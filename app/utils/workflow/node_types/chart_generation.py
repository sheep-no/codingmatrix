"""
Chart Generation Node - 图表生成节点

使用 matplotlib 生成各种类型的图表
"""

import logging
import asyncio
import tempfile
import os
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)

_temp_files: Set[str] = set()

_fonts_configured = False


def _configure_fonts():
    """配置 matplotlib 中文字体支持"""
    global _fonts_configured
    if _fonts_configured:
        return

    try:
        font_path = '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'
        if not os.path.exists(font_path):
            font_path = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'

        if os.path.exists(font_path):
            import matplotlib.font_manager as fm
            fm.fontManager.addfont(font_path)
            font_prop = fm.FontProperties(fname=font_path)
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = [font_prop.get_name()] + plt.rcParams['font.sans-serif']
            logger.info(f"配置中文字体: {font_path}")

        plt.rcParams['axes.unicode_minus'] = False
        _fonts_configured = True
    except Exception as e:
        logger.warning(f"字体配置失败: {e}")
        _fonts_configured = True


def cleanup_all_temp_files() -> None:
    """清理所有临时图表文件"""
    for path in _temp_files:
        try:
            if os.path.exists(path):
                os.unlink(path)
                logger.debug(f"清理临时文件: {path}")
        except Exception as e:
            logger.warning(f"清理临时文件失败 {path}: {e}")
    _temp_files.clear()


class ChartGenerationNode(TaskNodeBase):
    """
    图表生成节点

    使用 matplotlib 生成图表并保存为文件

    参数:
        chart_type: 图表类型 (bar/line/pie/scatter/histogram)
        title: 图表标题
        data: 图表数据
        x_label: X 轴标签
        y_label: Y 轴标签
        output_format: 输出格式 (png/svg/pdf，默认 png)
    """

    task_type = TaskType.CHART_GENERATION

    VALID_CHART_TYPES = ("bar", "line", "pie", "scatter", "histogram")

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return ["chart_type", "title", "data"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "x_label": "",
            "y_label": "",
            "output_format": "png",
            "dpi": 100,
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "chart_type" not in self.params:
            errors.append("Missing required parameter: chart_type")
        elif self.params["chart_type"] not in self.VALID_CHART_TYPES:
            errors.append(
                f"Invalid chart_type: {self.params['chart_type']}. "
                f"Must be one of: {', '.join(self.VALID_CHART_TYPES)}"
            )

        if "title" not in self.params:
            errors.append("Missing required parameter: title")
        elif not isinstance(self.params["title"], str):
            errors.append("Parameter 'title' must be a string")

        if "data" not in self.params:
            errors.append("Missing required parameter: data")
        elif not isinstance(self.params["data"], (dict, list)):
            errors.append("Parameter 'data' must be a dict or list")

        if "output_format" in self.params:
            fmt = self.params["output_format"]
            if fmt not in ("png", "svg", "pdf"):
                errors.append("Parameter 'output_format' must be 'png', 'svg', or 'pdf'")

        if "dpi" in self.params:
            dpi = self.params["dpi"]
            if not isinstance(dpi, int) or dpi < 72 or dpi > 600:
                errors.append("Parameter 'dpi' must be an integer between 72 and 600")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        生成图表

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 图表生成结果
        """
        chart_type = self.params["chart_type"]
        title = self.params["title"]
        data = self.params["data"]
        x_label = self.params.get("x_label", "")
        y_label = self.params.get("y_label", "")
        output_format = self.params.get("output_format", "png")
        dpi = self.params.get("dpi", 100)

        try:
            logger.info(f"[{self.node_id}] 生成图表 | type={chart_type}, title={title}")

            chart_path = await self._generate_chart(
                chart_type=chart_type,
                title=title,
                data=data,
                x_label=x_label,
                y_label=y_label,
                output_format=output_format,
                dpi=dpi
            )

            logger.info(f"[{self.node_id}] 图表生成成功 | path={chart_path}")

            return NodeResult.success_result(
                data={
                    "chart_path": chart_path,
                    "chart_type": chart_type,
                    "title": title,
                    "format": output_format,
                },
                metadata={
                    "node_type": self.task_type.value,
                    "chart_type": chart_type,
                    "format": output_format,
                }
            )

        except ImportError as e:
            error_msg = "matplotlib is required for chart generation"
            logger.error(f"[{self.node_id}] {error_msg}: {e}")
            return NodeResult.error_result(
                error=f"{error_msg}: {str(e)}",
                metadata={"node_type": self.task_type.value}
            )
        except Exception as e:
            error_msg = f"Chart generation failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value}
            )

    async def _generate_chart(
        self,
        chart_type: str,
        title: str,
        data: Any,
        x_label: str,
        y_label: str,
        output_format: str,
        dpi: int
    ) -> str:
        """生成图表并保存"""

        _configure_fonts()

        import numpy as np

        fig, ax = plt.subplots(figsize=(10, 6), dpi=dpi)

        if chart_type == "bar":
            await self._plot_bar(ax, data, x_label, y_label)
        elif chart_type == "line":
            await self._plot_line(ax, data, x_label, y_label)
        elif chart_type == "pie":
            await self._plot_pie(ax, data)
        elif chart_type == "scatter":
            await self._plot_scatter(ax, data, x_label, y_label)
        elif chart_type == "histogram":
            await self._plot_histogram(ax, data, x_label)

        ax.set_title(title, fontsize=14, pad=20)

        if x_label and chart_type != "pie":
            ax.set_xlabel(x_label, fontsize=12)
        if y_label and chart_type != "pie":
            ax.set_ylabel(y_label, fontsize=12)

        plt.tight_layout()

        temp_file = tempfile.NamedTemporaryFile(
            suffix=f'.{output_format}',
            delete=False
        )
        chart_path = temp_file.name
        temp_file.close()

        _temp_files.add(chart_path)

        plt.savefig(chart_path, format=output_format, dpi=dpi)
        plt.close(fig)

        return chart_path

    async def _plot_bar(self, ax, data: Dict, x_label: str, y_label: str) -> None:
        """绘制柱状图"""
        import numpy as np

        if isinstance(data, dict):
            labels = list(data.keys())
            values = list(data.values())
        elif isinstance(data, list):
            values = data
            labels = [str(i+1) for i in range(len(values))]
        else:
            raise ValueError("Data for bar chart must be dict or list")

        x = np.arange(len(labels))
        ax.bar(x, values, tick_label=labels)

        if values:
            max_val = max(values)
            ax.set_ylim(0, max_val * 1.1)

    async def _plot_line(self, ax, data: Any, x_label: str, y_label: str) -> None:
        """绘制折线图"""
        import numpy as np

        if isinstance(data, dict):
            x_data = list(data.keys())
            y_data = list(data.values())
        elif isinstance(data, list):
            y_data = data
            x_data = list(range(len(y_data)))
        else:
            raise ValueError("Data for line chart must be dict or list")

        ax.plot(x_data, y_data, marker='o', linewidth=2)

    async def _plot_pie(self, ax, data: Dict) -> None:
        """绘制饼图"""
        labels = list(data.keys())
        values = list(data.values())
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)

    async def _plot_scatter(self, ax, data: Any, x_label: str, y_label: str) -> None:
        """绘制散点图"""
        import numpy as np

        if isinstance(data, dict):
            x_data = data.get('x', [])
            y_data = data.get('y', [])
        elif isinstance(data, list) and len(data) == 2:
            x_data = data[0]
            y_data = data[1]
        else:
            raise ValueError("Data for scatter chart must be {'x': [...], 'y': [...]} or [[x...], [y...]]")

        ax.scatter(x_data, y_data, s=100, alpha=0.6)

    async def _plot_histogram(self, ax, data: Any, x_label: str) -> None:
        """绘制直方图"""
        import numpy as np

        if isinstance(data, list):
            values = data
        elif isinstance(data, dict) and 'values' in data:
            values = data['values']
        else:
            raise ValueError("Data for histogram must be list or {'values': [...]}")

        ax.hist(values, bins=20, edgecolor='black', alpha=0.7)
