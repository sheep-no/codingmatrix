"""
PPT 配置加载器单元测试

测试配置加载器的核心功能：
- 从 YAML 加载全局设置
- 合并配置
- 热重载机制
- 配置访问
- 目录创建
"""

import pytest
import yaml
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.ppt.config_loader import (
    ConfigLoader,
    ConfigLoaderError,
    PPTConfig,
    ServiceConfig,
    AIConfig,
    TextConfig,
)


@pytest.fixture
def temp_settings(tmp_path):
    """创建临时设置文件"""
    settings = {
        "service": {
            "output_dir": "./test-output",
            "static_dir": "./test-static",
        },
        "ai": {
            "default_model": "Test/Model",
            "max_retries": 5,
            "temperature": 0.9,
        },
        "text": {
            "max_title_length": 30,
            "max_content_lines": 6,
            "default_title_size": 36,
        },
        "images": {
            "max_concurrent_search": 10,
            "download_timeout": 15,
        },
        "animations": {
            "default_enabled": True,
            "duration": 1.0,
        },
        "export": {
            "pdf": {
                "enabled": False,
                "conversion_timeout": 120,
            }
        },
        "storage": {
            "file_retention_days": 14,
            "max_total_size_gb": 20,
        },
    }
    
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(yaml.dump(settings, allow_unicode=True))
    
    return settings_file


@pytest.fixture
def temp_templates(tmp_path):
    """创建临时模板文件"""
    templates = {
        "templates": {
            "custom_template": {
                "id": "custom_template",
                "name": "自定义模板",
                "name_en": "Custom Template",
                "description": "测试模板",
                "category": "test",
                "colors": {"primary": "#ff0000"},
                "fonts": {"title": "Arial"},
                "layouts": ["title_slide"],
                "animations": {},
                "is_default": True,
            },
        },
        "settings": {
            "default_template": "custom_template",
        },
    }
    
    templates_file = tmp_path / "templates.yaml"
    templates_file.write_text(yaml.dump(templates, allow_unicode=True))
    
    return templates_file


@pytest.fixture
def config_loader(temp_settings, temp_templates):
    """创建配置加载器实例"""
    return ConfigLoader(
        settings_path=temp_settings,
        templates_path=temp_templates,
    )


class TestConfigLoader:
    """配置加载器测试类"""
    
    def test_load_settings(self, config_loader):
        """测试加载全局设置"""
        config_loader.load()
        
        # 验证服务设置
        assert config_loader.config.service.output_dir == "./test-output"
        assert config_loader.config.service.static_dir == "./test-static"
        
        # 验证 AI 设置
        assert config_loader.config.ai.default_model == "Test/Model"
        assert config_loader.config.ai.max_retries == 5
        assert config_loader.config.ai.temperature == 0.9
        
        # 验证文本设置
        assert config_loader.config.text.max_title_length == 30
        assert config_loader.config.text.max_content_lines == 6
        assert config_loader.config.text.default_title_size == 36
        
        # 验证图片设置
        assert config_loader.config.images.max_concurrent_search == 10
        assert config_loader.config.images.download_timeout == 15
        
        # 验证动画设置
        assert config_loader.config.animations.default_enabled is True
        assert config_loader.config.animations.duration == 1.0
        
        # 验证导出设置
        assert config_loader.config.export.pdf_enabled is False
        assert config_loader.config.export.conversion_timeout == 120
        
        # 验证存储设置
        assert config_loader.config.storage.file_retention_days == 14
        assert config_loader.config.storage.max_total_size_gb == 20
    
    def test_load_templates(self, config_loader):
        """测试加载模板配置"""
        config_loader.load()
        
        # 验证模板已加载
        assert "custom_template" in config_loader.templates
        
        template = config_loader.templates["custom_template"]
        assert template["name"] == "自定义模板"
    
    def test_ensure_directories(self, config_loader, tmp_path):
        """测试确保目录存在"""
        # 修改输出目录到临时路径
        config_loader.load()
        
        output_dir = Path(config_loader.config.service.output_dir)
        assert output_dir.exists()
    
    def test_get_setting(self, config_loader):
        """测试获取配置项"""
        config_loader.load()
        
        # 获取 AI 设置
        model = config_loader.get_setting("ai", "default_model")
        assert model == "Test/Model"
        
        # 获取文本设置
        max_length = config_loader.get_setting("text", "max_title_length")
        assert max_length == 30
        
        # 获取不存在的配置项，返回默认值
        value = config_loader.get_setting("nonexistent", "key", "default")
        assert value == "default"
    
    def test_set_setting(self, config_loader):
        """测试设置配置项"""
        config_loader.load()
        
        # 设置新值
        config_loader.set_setting("ai", "temperature", 0.5)
        
        # 验证设置生效
        assert config_loader.config.ai.temperature == 0.5
    
    def test_set_setting_invalid_section(self, config_loader, caplog):
        """测试设置不存在的配置节"""
        config_loader.load()
        
        config_loader.set_setting("nonexistent", "key", "value")
        
        assert "配置节不存在" in caplog.text
    
    def test_hot_reload_settings(self, config_loader, temp_settings):
        """测试热重载设置文件"""
        # 初始加载
        config_loader.load()
        assert config_loader.config.ai.default_model == "Test/Model"
        
        # 修改设置文件
        new_settings = {
            "service": {"output_dir": "./new-output"},
            "ai": {"default_model": "New/Model", "temperature": 0.9},
        }
        
        import time
        temp_settings.write_text(yaml.dump(new_settings, allow_unicode=True))
        time.sleep(0.1)
        temp_settings.touch()
        
        # 热重载
        has_changes = config_loader.hot_reload()
        
        assert has_changes is True
        assert config_loader.config.ai.default_model == "New/Model"
    
    def test_hot_reload_templates(self, config_loader, temp_templates):
        """测试热重载模板文件"""
        # 初始加载
        config_loader.load()
        assert "custom_template" in config_loader.templates
        
        # 修改模板文件
        new_templates = {
            "templates": {
                "updated_template": {
                    "id": "updated_template",
                    "name": "更新模板",
                    "name_en": "Updated",
                    "description": "更新后的模板",
                    "category": "test",
                    "colors": {},
                    "fonts": {},
                    "layouts": [],
                    "animations": {},
                },
            },
        }
        
        import time
        temp_templates.write_text(yaml.dump(new_templates, allow_unicode=True))
        time.sleep(0.1)
        temp_templates.touch()
        
        # 热重载
        has_changes = config_loader.hot_reload()
        
        assert has_changes is True
        assert "updated_template" in config_loader.templates
    
    def test_hot_reload_no_changes(self, config_loader):
        """测试没有变更时热重载返回 false"""
        config_loader.load()
        
        import time
        time.sleep(0.1)  # 确保时间戳不会相同
        
        has_changes = config_loader.hot_reload()
        
        assert has_changes is False
    
    def test_load_missing_settings_file(self, tmp_path):
        """测试加载不存在的设置文件"""
        non_existent_settings = tmp_path / "non_existent_settings.yaml"
        non_existent_templates = tmp_path / "non_existent_templates.yaml"
        
        loader = ConfigLoader(
            settings_path=non_existent_settings,
            templates_path=non_existent_templates,
        )
        
        # 应该不会抛出异常
        loader.load()
        
        # 使用默认配置
        assert loader.config.ai.default_model == "Qwen/Qwen3.5-4B"
    
    def test_config_property(self, config_loader):
        """测试 config 属性"""
        config_loader.load()
        
        config = config_loader.config
        
        assert isinstance(config, PPTConfig)
        assert config.ai is not None
        assert config.text is not None
        assert config.images is not None
    
    def test_templates_property(self, config_loader):
        """测试 templates 属性"""
        config_loader.load()
        
        templates = config_loader.templates
        
        assert isinstance(templates, dict)
        assert "custom_template" in templates


class TestConfigDefaults:
    """测试默认配置值"""
    
    def test_default_ppt_config(self):
        """测试默认 PPT 配置"""
        config = PPTConfig()
        
        assert config.service.output_dir == "./pptx_output"
        assert config.ai.default_model == "Qwen/Qwen3.5-4B"
        assert config.text.default_title_size == 32
        assert config.images.max_concurrent_search == 5
        assert config.animations.default_animation == "fade"
        assert config.export.pdf_enabled is True
        assert config.storage.file_retention_days == 7
    
    def test_default_service_config(self):
        """测试默认服务配置"""
        service = ServiceConfig()
        
        assert service.output_dir == "./pptx_output"
        assert service.static_dir == "./static/ppt"
        assert service.image_cache_dir == "./static/images/ppt-cache"
        assert service.temp_dir == "./tmp/ppt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
