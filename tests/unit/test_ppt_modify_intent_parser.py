"""
PPT 修改意图解析器和修改器单元测试

测试自然语言修改意图解析和 PPTX 修改功能
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptx.modify_intent_parser import (
    ModifyIntentParser,
    ModifyIntent,
    ModifyTarget,
    parse_modify_intent,
    format_modify_intent
)


class TestModifyIntentParser:
    """测试修改意图解析器"""

    def setup_method(self):
        self.parser = ModifyIntentParser()

    def test_parse_slide_number(self):
        """测试幻灯片编号提取"""
        intent = self.parser.parse("修改第3页的字体")
        assert len(intent.targets) > 0
        assert intent.targets[0].slide_number == 3

    def test_parse_slide_number_chinese(self):
        """测试中文数字幻灯片编号"""
        intent = self.parser.parse("第3张幻灯片改成蓝色")
        assert len(intent.targets) > 0
        assert intent.targets[0].slide_number == 3

    def test_parse_slide_number_english(self):
        """测试英文幻灯片编号"""
        intent = self.parser.parse("slide 5 的字体改成宋体")
        assert len(intent.targets) > 0
        assert intent.targets[0].slide_number == 5

    def test_parse_no_slide_number(self):
        """测试没有指定幻灯片编号"""
        intent = self.parser.parse("把标题改成微软雅黑")
        assert len(intent.targets) > 0
        assert intent.targets[0].slide_number is None

    def test_parse_font_modification(self):
        """测试字体修改意图"""
        intent = self.parser.parse("修改第3页的字体为微软雅黑")
        assert len(intent.targets) > 0
        target = intent.targets[0]
        assert target.slide_number == 3
        assert target.property_name == "font"
        assert target.property_value == "微软雅黑"

    def test_parse_color_modification(self):
        """测试颜色修改意图"""
        intent = self.parser.parse("第2页的背景改成蓝色")
        assert len(intent.targets) > 0
        target = intent.targets[0]
        assert target.slide_number == 2
        assert target.property_name in ["color", "background"]

    def test_parse_size_modification(self):
        """测试字号修改意图"""
        intent = self.parser.parse("把正文字号改成24")
        assert len(intent.targets) > 0
        target = intent.targets[0]
        assert target.property_name == "size"

    def test_parse_element_type_title(self):
        """测试目标元素类型 - 标题"""
        intent = self.parser.parse("修改标题的字体")
        assert len(intent.targets) > 0
        assert intent.targets[0].element_type == "title"

    def test_parse_element_type_text(self):
        """测试目标元素类型 - 正文"""
        intent = self.parser.parse("修改正文字体颜色")
        assert len(intent.targets) > 0
        assert intent.targets[0].element_type == "text"

    def test_parse_multiple_targets(self):
        """测试多个修改目标"""
        intent = self.parser.parse("修改第三页的字体与布局")
        assert len(intent.targets) >= 2
        property_names = {t.property_name for t in intent.targets}
        assert "font" in property_names
        assert "layout" in property_names

    def test_parse_complex_request(self):
        """测试复杂修改请求"""
        intent = self.parser.parse("把第2页标题改成微软雅黑，颜色改成红色")
        assert len(intent.targets) >= 2
        assert intent.targets[0].slide_number == 2

    def test_confidence_with_slide_number(self):
        """测试置信度 - 有幻灯片编号"""
        intent = self.parser.parse("修改第3页的字体为微软雅黑")
        assert intent.confidence >= 0.6

    def test_confidence_without_value(self):
        """测试置信度 - 没有具体值"""
        intent = self.parser.parse("修改第3页的字体")
        assert intent.confidence >= 0.3

    def test_confidence_no_targets(self):
        """测试置信度 - 无目标"""
        intent = self.parser.parse("你好")
        assert intent.confidence == 0.0

    def test_empty_input(self):
        """测试空输入"""
        intent = self.parser.parse("")
        assert len(intent.targets) == 0

    def test_font_extraction(self):
        """测试字体名称提取"""
        fonts = ["微软雅黑", "宋体", "黑体", "Arial", "Calibri"]
        for font in fonts:
            intent = self.parser.parse(f"改成{font}")
            found = any(t.property_value == font for t in intent.targets)
            assert found, f"未能提取字体：{font}"

    def test_color_extraction(self):
        """测试颜色提取"""
        colors = ["红色", "蓝色", "绿色", "black", "white"]
        for color in colors:
            intent = self.parser.parse(f"改成{color}")
            found = any(
                (t.property_value == color or t.property_value == color.lower())
                for t in intent.targets
            )
            assert found, f"未能提取颜色：{color}"


class TestParseModifyIntentFunction:
    """测试 parse_modify_intent 函数"""

    def test_basic_parse(self):
        """测试基本解析"""
        intent = parse_modify_intent("修改第3页的字体为微软雅黑")
        assert isinstance(intent, ModifyIntent)
        assert len(intent.targets) > 0
        assert intent.targets[0].slide_number == 3


class TestFormatModifyIntent:
    """测试 format_modify_intent 函数"""

    def test_format_with_targets(self):
        """测试格式化有目标的意图"""
        intent = ModifyIntent(
            raw_text="test",
            targets=[
                ModifyTarget(slide_number=3, property_name="font", property_value="微软雅黑")
            ]
        )
        result = format_modify_intent(intent)
        assert "第3页" in result
        assert "font" in result

    def test_format_empty(self):
        """测试格式化空意图"""
        intent = ModifyIntent(raw_text="test", targets=[])
        result = format_modify_intent(intent)
        assert "未识别" in result

    def test_format_no_slide_number(self):
        """测试格式化无幻灯片编号"""
        intent = ModifyIntent(
            raw_text="test",
            targets=[
                ModifyTarget(property_name="font", property_value="微软雅黑")
            ]
        )
        result = format_modify_intent(intent)
        assert "所有页" in result


class TestModifyTarget:
    """测试 ModifyTarget 数据类"""

    def test_default_values(self):
        """测试默认值"""
        target = ModifyTarget()
        assert target.slide_number is None
        assert target.element_type is None
        assert target.property_name is None
        assert target.property_value is None

    def test_with_values(self):
        """测试带值"""
        target = ModifyTarget(
            slide_number=3,
            element_type="title",
            property_name="font",
            property_value="微软雅黑"
        )
        assert target.slide_number == 3
        assert target.element_type == "title"
        assert target.property_name == "font"
        assert target.property_value == "微软雅黑"
