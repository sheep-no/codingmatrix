"""
PPT 排版引擎单元测试

测试文字分析、布局优化和排版工具功能
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptx.layout_engine import (
    TextAnalyzer,
    LayoutOptimizer,
    LayoutUtils
)
from app.utils.pptx.templates import TemplateConfig, TemplateCategory, SlideLayout


class TestTextAnalyzer:
    """测试文字分析器"""

    def test_count_chinese_chars(self):
        """测试中文字符统计"""
        assert TextAnalyzer.count_chinese_chars("你好世界") == 4
        assert TextAnalyzer.count_chinese_chars("Hello World") == 0
        assert TextAnalyzer.count_chinese_chars("Hello 你好") == 2
        assert TextAnalyzer.count_chinese_chars("") == 0

    def test_analyze_text_density(self):
        """测试文字密度分析"""
        result = TextAnalyzer.analyze_text_density("Hello 你好")
        assert result['total_chars'] > 0
        assert 'chinese_count' in result
        assert 'chinese_ratio' in result
        assert 'ascii_ratio' in result

    def test_analyze_empty_text(self):
        """测试空文本密度分析"""
        result = TextAnalyzer.analyze_text_density("")
        assert result['total_chars'] == 0
        assert result['chinese_ratio'] == 0.0
        assert result['density_score'] == 0.0

    def test_estimate_display_height(self):
        """测试文字高度估算"""
        height = TextAnalyzer.estimate_display_height(
            "Line 1\nLine 2\nLine 3",
            font_size=16,
            line_spacing=1.5,
            max_width=6.0
        )
        assert height > 0

    def test_estimate_display_height_empty(self):
        """测试空文本高度估算"""
        height = TextAnalyzer.estimate_display_height(
            "",
            font_size=16,
            line_spacing=1.5
        )
        assert height == 0.0


class TestLayoutOptimizer:
    """测试布局优化器"""

    @pytest.fixture
    def optimizer(self):
        return LayoutOptimizer()

    @pytest.fixture
    def template_config(self):
        return {
            'content_width': 10.0,
            'content_height': 6.0,
            'margin': 0.5,
            'title_min_size': 24,
            'title_max_size': 44,
            'body': {
                'font_size': 18,
                'min_size': 12,
                'max_size': 24,
                'line_spacing': 1.5,
                'columns': 1
            }
        }

    def test_optimize_slide_content(self, optimizer, template_config):
        """测试幻灯片内容优化"""
        slide_data = {
            "title": "测试标题",
            "body": "这是一段测试正文内容"
        }

        optimized = optimizer.optimize_slide_content(slide_data, template_config)

        assert optimized is not None
        assert 'title' in optimized
        assert 'body' in optimized

    def test_adjust_font_size(self, optimizer):
        """测试自适应字号"""
        short_text = "短文本"
        long_text = "这是一个很长的文本内容，需要缩小字号才能适应容器宽度"

        size_short = optimizer.adjust_font_size(
            short_text,
            max_width=5.0,
            min_size=12,
            max_size=36
        )

        size_long = optimizer.adjust_font_size(
            long_text,
            max_width=5.0,
            min_size=12,
            max_size=36
        )

        assert 12 <= size_short <= 36
        assert 12 <= size_long <= 36

    def test_adjust_font_size_empty(self, optimizer):
        """测试空文本字号"""
        size = optimizer.adjust_font_size(
            "",
            max_width=5.0,
            min_size=12,
            max_size=36
        )
        assert size == 36

    def test_split_to_columns(self, optimizer):
        """测试分栏处理"""
        content = "段落一\n段落二\n段落三\n段落四"

        columns = optimizer.split_to_columns(content, num_columns=2)

        assert len(columns) == 2
        assert columns[0]['text'] is not None
        assert columns[1]['text'] is not None

    def test_split_to_columns_single(self, optimizer):
        """测试单栏分割"""
        content = "单一内容"

        columns = optimizer.split_to_columns(content, num_columns=1)

        assert len(columns) == 1

    def test_prevent_overflow(self, optimizer):
        """测试防溢出检测"""
        short_text = "短文本"
        long_text = "这是一个非常长的文本，可能会溢出容器的显示范围导致排版问题出现"

        result_short = optimizer.prevent_overflow(
            short_text,
            max_height=3.0,
            font_size=16,
            line_spacing=1.5,
            max_width=6.0
        )

        result_long = optimizer.prevent_overflow(
            long_text,
            max_height=1.0,
            font_size=16,
            line_spacing=1.5,
            max_width=6.0
        )

        assert 'fits' in result_short
        assert 'adjusted' in result_long

    def test_optimize_whitespace(self, optimizer, template_config):
        """测试留白优化"""
        slide_data = {
            "title": {"text": "标题", "font_size": 32},
            "body": {"text": "内容", "font_size": 18}
        }

        config = optimizer.optimize_whitespace(slide_data, template_config)

        assert config is not None
        assert 'spacing' in config
        assert 'margin' in config['spacing']


class TestLayoutUtils:
    """测试排版工具函数"""

    def test_get_layout_for_slide_type(self):
        """测试根据幻灯片类型获取布局"""
        layout = LayoutUtils.get_layout_for_slide_type("title")
        assert layout == "TITLE_SLIDE"
        
        layout = LayoutUtils.get_layout_for_slide_type("end")
        assert layout == "END_SLIDE"

    def test_calculate_content_area(self):
        """测试内容区域计算"""
        area = LayoutUtils.calculate_content_area(
            slide_width=13.333,
            slide_height=7.5,
            margin=0.8
        )

        assert 'width' in area
        assert 'height' in area
        assert area['width'] < 13.333
        assert area['height'] < 7.5

    def test_calculate_optimal_font_size(self):
        """测试计算最优字号"""
        size = LayoutUtils.calculate_optimal_font_size(
            text_length=100,
            container_width=10.0
        )

        assert 10 <= size <= 48
