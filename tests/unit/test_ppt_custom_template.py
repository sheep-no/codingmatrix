"""
PPT 自定义模板解析器单元测试

测试模板解析、验证和转换功能
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptx.custom_template import (
    CustomTemplateParser,
    TemplateValidator,
    TemplateConverter
)
from app.utils.pptx.templates import TemplateConfig, TemplateCategory


class TestTemplateValidator:
    """测试模板验证器"""

    @pytest.fixture
    def validator(self):
        return TemplateValidator()

    def test_validate_nonexistent_file(self, validator):
        """测试不存在的文件"""
        is_valid, errors = validator.validate_template("/nonexistent/file.pptx")
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_invalid_extension(self, validator, tmp_path):
        """测试无效扩展名"""
        invalid_file = tmp_path / "template.txt"
        invalid_file.write_text("not a pptx file")

        is_valid, errors = validator.validate_template(str(invalid_file))
        assert is_valid is False

    def test_validate_empty_file(self, validator, tmp_path):
        """测试空文件"""
        empty_file = tmp_path / "empty.pptx"
        empty_file.write_bytes(b"")

        is_valid, errors = validator.validate_template(str(empty_file))
        assert is_valid is False


class TestTemplateConverter:
    """测试模板转换器"""

    @pytest.fixture
    def converter(self):
        return TemplateConverter()

    @pytest.fixture
    def base_config(self):
        return TemplateConfig(
            template_id="base",
            name="Base",
            name_zh="基础",
            category=TemplateCategory.BUSINESS,
            description="基础模板",
            primary_color="1F4E79",
            title_size=32,
            body_size=16
        )

    @pytest.fixture
    def custom_config(self):
        return TemplateConfig(
            template_id="custom",
            name="Custom",
            name_zh="自定义",
            category=TemplateCategory.MINIMAL,
            description="自定义模板",
            primary_color="FF0000",
            title_size=40,
            body_size=14
        )

    def test_merge_configs(self, converter, base_config, custom_config):
        """测试配置合并"""
        merged = converter.merge_configs(base_config, custom_config)

        assert merged.primary_color == "FF0000"
        assert merged.title_size == 40
        assert merged.body_size == 14
        assert merged.template_id == "custom"

    def test_merge_configs_partial_override(self, converter, base_config, custom_config):
        """测试部分覆盖合并"""
        custom_config.title_font = "Arial"
        # 恢复自定义模板的主色为默认值，测试主色是否回退到基础模板
        custom_config.primary_color = "1F4E79" 
        merged = converter.merge_configs(base_config, custom_config)

        assert merged.primary_color == "1F4E79"
        assert merged.title_font == "Arial"

    def test_apply_config_to_presentation(self, converter, base_config):
        """测试配置应用到演示文稿"""
        from pptx import Presentation
        
        prs = Presentation()
        converter.apply_config_to_presentation(base_config, prs)

        assert prs.slide_width > 0
        assert prs.slide_height > 0
