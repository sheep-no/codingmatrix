"""
PPT 模板系统单元测试

测试模板管理器、内置模板和模板配置功能
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptx.templates import (
    TemplateManager,
    TemplateConfig,
    SlideLayout,
    TemplateCategory,
)
from app.utils.pptx.templates.presets import (
    BusinessReportTemplate,
    AcademicPresetTemplate,
    PitchDeckTemplate,
    EducationTemplate,
    MinimalTemplate,
    TechTemplate,
)


class TestTemplateConfig:
    """测试模板配置数据类"""

    def test_default_config(self):
        """测试默认配置"""
        config = TemplateConfig(
            template_id="test",
            name="Test",
            name_zh="测试",
            category=TemplateCategory.BUSINESS,
            description="测试模板"
        )

        assert config.template_id == "test"
        assert config.primary_color == "1F4E79"
        assert config.title_font == "微软雅黑"
        assert config.title_size == 32
        assert config.slide_width == 13.333
        assert config.slide_height == 7.5

    def test_custom_config(self):
        """测试自定义配置"""
        config = TemplateConfig(
            template_id="custom",
            name="Custom",
            name_zh="自定义",
            category=TemplateCategory.MINIMAL,
            description="自定义模板",
            primary_color="FF0000",
            title_size=40,
            has_header_bar=False
        )

        assert config.primary_color == "FF0000"
        assert config.title_size == 40
        assert config.has_header_bar is False

    def test_copy_config(self):
        """测试配置复制"""
        config = TemplateConfig(
            template_id="original",
            name="Original",
            name_zh="原始",
            category=TemplateCategory.BUSINESS,
            description="原始模板"
        )

        copied = config.copy()

        assert copied.template_id.startswith("custom_")
        assert copied.primary_color == config.primary_color
        assert copied.title_size == config.title_size
        assert copied is not config


class TestSlideLayout:
    """测试幻灯片布局枚举"""

    def test_layout_values(self):
        """测试布局值"""
        assert SlideLayout.TITLE_ONLY.value == "title_only"
        assert SlideLayout.TITLE_CONTENT.value == "title_content"
        assert SlideLayout.TITLE_IMAGE.value == "title_image"
        assert SlideLayout.TITLE_TWO_COLUMN.value == "title_two_column"
        assert SlideLayout.TITLE_BULLET.value == "title_bullet"
        assert SlideLayout.TITLE_CHART.value == "title_chart"
        assert SlideLayout.FULL_IMAGE.value == "full_image"
        assert SlideLayout.END_SLIDE.value == "end_slide"


class TestTemplateCategory:
    """测试模板分类枚举"""

    def test_category_values(self):
        """测试分类值"""
        assert TemplateCategory.BUSINESS.value == "business"
        assert TemplateCategory.ACADEMIC.value == "academic"
        assert TemplateCategory.PITCH.value == "pitch"
        assert TemplateCategory.TECH.value == "tech"
        assert TemplateCategory.EDUCATION.value == "education"
        assert TemplateCategory.MINIMAL.value == "minimal"


class TestBuiltInTemplates:
    """测试内置模板"""

    def test_business_report_template(self):
        """测试商务汇报模板"""
        template = BusinessReportTemplate()
        config = template.config

        assert config.template_id == "business_report"
        assert config.category == TemplateCategory.BUSINESS
        assert config.primary_color == "1F4E79"
        assert config.has_header_bar is True
        assert config.has_footer_bar is True
        assert len(config.layouts) > 0

    def test_academic_template(self):
        """测试学术论文模板"""
        template = AcademicPresetTemplate()
        config = template.config

        assert config.template_id == "academic"
        assert config.category == TemplateCategory.ACADEMIC
        assert config.primary_color == "203864"
        assert config.has_header_bar is False
        assert config.has_page_number is True

    def test_pitch_deck_template(self):
        """测试产品路演模板"""
        template = PitchDeckTemplate()
        config = template.config

        assert config.template_id == "pitch_deck"
        assert config.category == TemplateCategory.PITCH
        assert config.primary_color == "C00000"
        assert config.has_corner_decor is True
        assert config.background_color == "1A1A1A"

    def test_education_template(self):
        """测试教育培训模板"""
        template = EducationTemplate()
        config = template.config

        assert config.template_id == "education"
        assert config.category == TemplateCategory.EDUCATION
        assert config.primary_color == "2E75B6"
        assert config.has_corner_decor is True

    def test_minimal_template(self):
        """测试简约风格模板"""
        template = MinimalTemplate()
        config = template.config

        assert config.template_id == "minimal"
        assert config.category == TemplateCategory.MINIMAL
        assert config.slide_margin == 1.5
        assert config.has_header_bar is False
        assert config.has_footer_bar is False

    def test_tech_template(self):
        template = TechTemplate()
        config = template.config

        assert config.template_id == "tech"
        assert config.category == TemplateCategory.TECH
        assert config.background_color == "0F172A"
        assert config.accent_color == "F97316"


class TestTemplateManager:
    """测试模板管理器"""

    @pytest.fixture
    def manager(self):
        """创建模板管理器"""
        return TemplateManager()

    def test_manager_initialization(self, manager):
        """测试管理器初始化"""
        assert manager is not None
        templates = manager.list_templates()
        assert len(templates) == 9

    def test_list_templates(self, manager):
        """测试列出模板"""
        templates = manager.list_templates()

        assert len(templates) == 9
        for template in templates:
            assert "id" in template
            assert "name" in template
            assert "name_zh" in template
            assert "category" in template
            assert "description" in template

    def test_get_template(self, manager):
        """测试获取模板"""
        template = manager.get_template("business_report")
        assert template is not None
        assert template.config.template_id == "business_report"

    def test_get_template_not_found(self, manager):
        """测试获取不存在的模板"""
        template = manager.get_template("nonexistent")
        assert template is None

    def test_get_config(self, manager):
        """测试获取模板配置"""
        config = manager.get_config("academic")
        assert config is not None
        assert config.template_id == "academic"

    def test_recommend_by_category(self, manager):
        """测试按分类推荐模板"""
        recommendations = manager.recommend_template(
            category=TemplateCategory.BUSINESS
        )

        assert len(recommendations) > 0
        assert recommendations[0] == "business_report"

    def test_recommend_by_keywords(self, manager):
        """测试按关键词推荐模板"""
        recommendations = manager.recommend_template(
            keywords=["学术", "论文"]
        )

        assert len(recommendations) > 0
        assert "academic" in recommendations

    def test_recommend_default(self, manager):
        """测试默认推荐"""
        recommendations = manager.recommend_template()

        assert len(recommendations) > 0
        assert len(recommendations) <= 5

    def test_register_custom_template(self, manager):
        """测试注册自定义模板"""
        config = TemplateConfig(
            template_id="custom_test",
            name="Custom Test",
            name_zh="自定义测试",
            category=TemplateCategory.MINIMAL,
            description="测试用自定义模板"
        )

        from app.utils.pptx.templates.base import TemplateBase

        class CustomTestTemplate(TemplateBase):
            @property
            def config(self):
                return config

        template = CustomTestTemplate()
        manager.register(template)

        templates = manager.list_templates()
        assert len(templates) == 10

        saved = manager.get_template("custom_test")
        assert saved is not None

    def test_register_duplicate(self, manager):
        """测试重复注册"""
        from app.utils.pptx.templates.base import TemplateBase

        class DuplicateTemplate(TemplateBase):
            @property
            def config(self):
                return TemplateConfig(
                    template_id="business_report",
                    name="Duplicate",
                    name_zh="重复",
                    category=TemplateCategory.BUSINESS,
                    description="重复模板"
                )

        with pytest.raises(ValueError, match="模板已存在"):
            manager.register(DuplicateTemplate())

    def test_save_and_load_custom_template(self, manager, tmp_path):
        """测试保存和加载自定义模板"""
        config = TemplateConfig(
            template_id="save_test",
            name="Save Test",
            name_zh="保存测试",
            category=TemplateCategory.EDUCATION,
            description="保存测试模板",
            primary_color="ABC123"
        )

        saved_id = manager.save_custom_template(config)
        assert saved_id == "save_test"

        config_path = tmp_path / "save_test.json"
        import shutil
        shutil.copy(
            manager._template_dir / "save_test.json",
            config_path
        )

        loaded = manager.load_custom_template(str(config_path))
        assert loaded is not None
        assert loaded.template_id == "save_test"
        assert loaded.primary_color == "ABC123"

    def test_load_invalid_template(self, manager, tmp_path):
        """测试加载无效模板"""
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("not valid json")

        loaded = manager.load_custom_template(str(invalid_path))
        assert loaded is None
