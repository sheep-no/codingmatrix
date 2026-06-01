"""
PPT 模板注册表单元测试

测试模板注册表的核心功能：
- 从 YAML 加载配置
- 获取模板
- 列出模板
- 注册自定义模板
- 热重载
- 错误处理
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.ppt.template_registry import (
    TemplateRegistry,
    TemplateRegistryError,
    TemplateConfig,
    TemplateInfo,
)


@pytest.fixture
def temp_config(tmp_path):
    """创建临时配置文件"""
    config = {
        "templates": {
            "modern": {
                "id": "modern",
                "name": "现代简约",
                "name_en": "Modern Minimal",
                "description": "简洁清晰的现代风格",
                "category": "general",
                "colors": {
                    "primary": "#2563eb",
                    "secondary": "#64748b",
                    "background": "#ffffff",
                },
                "fonts": {
                    "title": "Arial, sans-serif",
                    "body": "Arial, sans-serif",
                },
                "layouts": ["title_slide", "content_with_image"],
                "animations": {"default": "fade", "supported": ["fade"]},
                "is_default": True,
            },
        },
        "settings": {
            "default_template": "modern",
        },
    }
    
    config_file = tmp_path / "templates.yaml"
    config_file.write_text(yaml.dump(config, allow_unicode=True))
    
    return config_file


@pytest.fixture
def registry(temp_config):
    """创建注册表实例"""
    reg = TemplateRegistry(config_path=temp_config)
    reg.load()
    return reg


class TestTemplateRegistry:
    """模板注册表测试类"""
    
    def test_load_from_yaml(self, registry):
        """测试从 YAML 加载配置"""
        # 验证模板已加载
        assert "modern" in registry._templates
        
        template = registry._templates["modern"]
        assert template.name == "现代简约"
        assert template.name_en == "Modern Minimal"
        assert template.colors["primary"] == "#2563eb"
        assert template.is_default is True
    
    def test_get_template_exists(self, registry):
        """测试获取存在的模板"""
        template = registry.get_template("modern")
        
        assert template is not None
        assert template.id == "modern"
        assert template.name == "现代简约"
    
    def test_get_template_not_exists_fallback(self, registry):
        """测试获取不存在的模板时回退到默认"""
        template = registry.get_template("non_existent")
        
        # 应该返回默认模板
        assert template is not None
        assert template.is_default is True
    
    def test_get_template_no_default_error(self):
        """测试没有默认模板时的异常"""
        reg = TemplateRegistry()
        reg._templates = {}  # 清空模板
        
        with pytest.raises(TemplateRegistryError):
            reg.get_template("any_template")
    
    def test_list_templates_all(self, registry):
        """测试列出所有模板"""
        templates = registry.list_templates()
        
        assert len(templates) >= 1
        assert all(isinstance(t, TemplateInfo) for t in templates)
        
        # 默认模板应该排前面
        if templates:
            assert templates[0].is_default is True
    
    def test_list_templates_by_category(self, registry):
        """测试按类别过滤模板"""
        templates = registry.list_templates(category="general")
        
        assert all(t.category == "general" for t in templates)
    
    def test_register_custom_template(self, registry):
        """测试注册自定义模板"""
        template_id = registry.register_custom(
            template_id="custom_my_brand",
            name="我的品牌",
            colors={"primary": "#ff0000", "background": "#ffffff"},
            fonts={"title": "CustomFont", "body": "CustomBody"},
            created_by="user_123",
        )
        
        assert template_id == "custom_my_brand"
        
        # 验证模板已注册
        template = registry.get_template("custom_my_brand")
        assert template.is_custom is True
        assert template.created_by == "user_123"
        assert template.category == "custom"
    
    def test_register_custom_duplicate_error(self, registry):
        """测试注册重复模板 ID 时抛出异常"""
        # 先注册一次
        registry.register_custom(
            template_id="duplicate_test",
            name="测试",
            colors={},
            fonts={},
        )
        
        # 再次注册应该失败
        with pytest.raises(TemplateRegistryError) as exc_info:
            registry.register_custom(
                template_id="duplicate_test",
                name="测试 2",
                colors={},
                fonts={},
            )
        
        assert "已存在" in str(exc_info.value)
    
    def test_hot_reload(self, registry, temp_config):
        """测试热重载配置文件"""
        # 修改配置文件
        new_config = {
            "templates": {
                "modern": {
                    "id": "modern",
                    "name": "现代简约（更新）",
                    "name_en": "Modern Minimal",
                    "description": "更新后的描述",
                    "category": "general",
                    "colors": {"primary": "#2563eb"},
                    "fonts": {"title": "Arial"},
                    "layouts": [],
                    "animations": {},
                    "is_default": True,
                },
            },
            "settings": {},
        }
        
        # 写入新配置并更新时间戳
        import time
        temp_config.write_text(yaml.dump(new_config, allow_unicode=True))
        time.sleep(0.1)  # 确保时间戳不同
        temp_config.touch()
        
        # 热重载
        registry.hot_reload()
        
        # 验证配置已更新
        template = registry.get_template("modern")
        assert template.name == "现代简约（更新）"
    
    def test_get_settings(self, registry):
        """测试获取全局设置"""
        settings = registry.get_settings()
        
        assert settings is not None
        assert settings.default_template == "modern"
    
    def test_get_categories(self, registry):
        """测试获取所有类别"""
        # 注册不同类别的模板
        registry.register_custom(
            template_id="test_business",
            name="商务测试",
            colors={},
            fonts={},
        )
        
        categories = registry.get_categories()
        
        assert "general" in categories
        assert "custom" in categories
    
    def test_load_missing_file_uses_defaults(self, tmp_path):
        """测试加载不存在的文件时使用默认配置"""
        non_existent = tmp_path / "non_existent.yaml"
        
        reg = TemplateRegistry(config_path=non_existent)
        reg.load()
        
        # 应该使用内置默认
        assert "modern" in reg._templates


class TestTemplateConfig:
    """模板配置测试类"""
    
    def test_template_config_defaults(self):
        """测试模板配置默认值"""
        config = TemplateConfig(
            id="test",
            name="测试",
            name_en="Test",
            description="测试模板",
            category="test",
            colors={},
            fonts={},
            layouts=[],
            animations={},
        )
        
        assert config.is_default is False
        assert config.is_custom is False
        assert config.created_by is None
        assert config.thumbnail == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
