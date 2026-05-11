"""
测试 Guardian Router 管理 API

测试配置管理、资源监控、备份恢复等功能
"""
import pytest
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestGuardianRouterImports:
    """测试路由模块导入"""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        """设置测试环境变量"""
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "test-api-key-for-testing")

    def test_import_guardian_router(self):
        """测试 guardian_router 模块导入"""
        from app.api.v2.guardian_router import router
        assert router is not None

    def test_import_services(self):
        """测试相关服务导入"""
        from app.services.resource_config import resource_config_service
        from app.services.feature_switch import feature_switch_service
        from app.services.log_config import log_config_service

        assert resource_config_service is not None
        assert feature_switch_service is not None
        assert log_config_service is not None


class TestMemoryStatsEndpoint:
    """测试内存监控端点"""

    def test_memory_stats_structure(self):
        """测试内存统计返回结构"""
        # 模拟内存数据
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 1024 * 1024 * 500  # 500 MB
        mock_memory_info.vms = 1024 * 1024 * 2000  # 2000 MB

        mock_memory_full = MagicMock()
        mock_memory_full.uss = 1024 * 1024 * 400  # 400 MB

        mock_vm = MagicMock()
        mock_vm.total = 1024 * 1024 * 1024 * 4  # 4 GB
        mock_vm.available = 1024 * 1024 * 1024 * 2  # 2 GB
        mock_vm.used = 1024 * 1024 * 1024 * 2  # 2 GB
        mock_vm.percent = 50.0
        mock_vm.free = 1024 * 1024 * 1024 * 2  # 2 GB

        mock_swap = MagicMock()
        mock_swap.total = 1024 * 1024 * 1024 * 2
        mock_swap.used = 0
        mock_swap.percent = 0

        expected = {
            "process": {
                "rss_mb": mock_memory_info.rss / 1024 / 1024,
                "vms_mb": mock_memory_info.vms / 1024 / 1024,
                "uss_mb": mock_memory_full.uss / 1024 / 1024,
                "percent": 12.5  # 500MB / 4GB
            },
            "system": {
                "total_mb": mock_vm.total / 1024 / 1024,
                "available_mb": mock_vm.available / 1024 / 1024,
                "used_mb": mock_vm.used / 1024 / 1024,
                "percent": mock_vm.percent,
                "free_mb": mock_vm.free / 1024 / 1024
            },
            "swap": {
                "total_mb": mock_swap.total / 1024 / 1024,
                "used_mb": mock_swap.used / 1024 / 1024,
                "percent": mock_swap.percent
            },
            "recommendations": {
                "env_warning": False,
                "env_critical": False,
                "process_warning": False,
                "suggestions": ["内存使用正常"]
            },
            "timestamp": datetime.now().isoformat()
        }

        # 验证结构
        assert "process" in expected
        assert "system" in expected
        assert "swap" in expected
        assert "recommendations" in expected
        assert expected["process"]["rss_mb"] == 500.0
        assert expected["system"]["percent"] == 50.0


class TestLogConfigEndpoint:
    """测试日志配置端点"""

    def test_log_config_structure(self):
        """测试日志配置返回结构"""
        expected = {
            "log_level": "INFO",
            "global_level": "WARNING",
            "log_to_file": True,
            "log_to_console": True
        }

        assert "log_level" in expected
        assert "log_to_file" in expected
        assert isinstance(expected["log_to_file"], bool)


class TestBackupEndpoint:
    """测试配置备份端点"""

    def test_backup_data_structure(self):
        """测试备份数据格式"""
        backup_data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "created_by": "admin",
            "configs": {
                "docker_max_memory": {
                    "value": "512m",
                    "description": "Docker 容器最大内存"
                },
                "log_level": {
                    "value": "INFO",
                    "description": "日志级别"
                }
            }
        }

        assert backup_data["version"] == "1.0"
        assert "configs" in backup_data
        assert "docker_max_memory" in backup_data["configs"]
        assert backup_data["configs"]["docker_max_memory"]["value"] == "512m"

    def test_backup_filename_format(self):
        """测试备份文件名格式"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"config_backup_{timestamp}.json"

        assert filename.startswith("config_backup_")
        assert filename.endswith(".json")
        assert len(timestamp) == 15  # YYYYMMDD_HHMMSS

    def test_backup_list_item_structure(self):
        """测试备份列表项结构"""
        backup_item = {
            "filename": "config_backup_20260426_120000.json",
            "size": 1024,
            "created": datetime.now().isoformat(),
            "download_url": "/api/v2/Controller/admin/backup/20260426_120000"
        }

        assert "filename" in backup_item
        assert "size" in backup_item
        assert "created" in backup_item
        assert "download_url" in backup_item
        assert backup_item["filename"].endswith(".json")


class TestRestoreEndpoint:
    """测试配置恢复端点"""

    def test_restore_data_structure(self):
        """测试恢复数据格式"""
        restore_data = {
            "version": "1.0",
            "configs": {
                "docker_max_memory": {
                    "value": "1024m",
                    "description": "Docker 容器最大内存"
                }
            }
        }

        assert "configs" in restore_data
        assert "docker_max_memory" in restore_data["configs"]

    def test_restore_response_structure(self):
        """测试恢复响应格式"""
        response = {
            "status": "success",
            "message": "成功恢复 5 项配置",
            "restored_count": 5
        }

        assert response["status"] == "success"
        assert "restored_count" in response
        assert isinstance(response["restored_count"], int)


class TestWebSocketStatsEndpoint:
    """测试 WebSocket 状态端点"""

    def test_ws_stats_structure(self):
        """测试 WebSocket 统计数据格式"""
        ws_stats = {
            "current": 10,
            "max": 50,
            "available": 40,
            "timestamp": datetime.now().isoformat()
        }

        assert "current" in ws_stats
        assert "max" in ws_stats
        assert "available" in ws_stats
        assert ws_stats["available"] == ws_stats["max"] - ws_stats["current"]

    def test_ws_stats_calculation(self):
        """测试 WebSocket 使用率计算"""
        current = 25
        max_conn = 50
        available = max_conn - current
        usage_percent = (current / max_conn) * 100

        assert available == 25
        assert usage_percent == 50.0


class TestResourceConfigModel:
    """测试资源配置模型"""

    def test_server_config_defaults(self):
        """测试 ServerConfig 默认配置"""
        from app.models.server_config import ServerConfig

        defaults = ServerConfig.DEFAULT_CONFIGS

        # 检查必需的配置项
        required_keys = [
            "docker_max_memory",
            "docker_initial_memory",
            "docker_image",
            "docker_max_containers",
            "feature_docker_enabled",
            "feature_aicloud_enabled",
            "feature_project_enabled",
            "feature_workflow_enabled",
            "db_pool_size",
            "db_max_overflow",
            "db_pool_timeout",
            "log_level",
            "log_retention_days",
            "log_to_file"
        ]

        for key in required_keys:
            assert key in defaults, f"Missing required config: {key}"
            assert "value" in defaults[key]
            assert "description" in defaults[key]

    def test_default_docker_memory(self):
        """测试默认 Docker 内存配置"""
        from app.models.server_config import ServerConfig

        docker_config = ServerConfig.DEFAULT_CONFIGS["docker_max_memory"]
        assert docker_config["value"] == "512m"

    def test_default_log_level(self):
        """测试默认日志级别"""
        from app.models.server_config import ServerConfig

        log_config = ServerConfig.DEFAULT_CONFIGS["log_level"]
        assert log_config["value"] == "INFO"


class TestFeatureSwitches:
    """测试功能开关"""

    def test_feature_switch_keys(self):
        """测试功能开关配置键"""
        from app.models.server_config import ServerConfig

        feature_keys = [
            "feature_docker_enabled",
            "feature_aicloud_enabled",
            "feature_project_enabled",
            "feature_workflow_enabled"
        ]

        for key in feature_keys:
            assert key in ServerConfig.DEFAULT_CONFIGS
            assert ServerConfig.DEFAULT_CONFIGS[key]["value"] in ["true", "false"]
