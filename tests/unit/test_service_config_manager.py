"""ServiceConfigManager 读取、保存与服务识别测试。"""

import json

import pytest

import app.utils.service_config_manager as scm
from app.utils.service_config_manager import ServiceConfigManager


@pytest.fixture
def manager(tmp_path):
    return ServiceConfigManager(config_path=str(tmp_path / "cfg" / "services.json"))


class TestLoad:
    def test_missing_file_logs_warning(self, tmp_path, monkeypatch):
        warnings = []
        monkeypatch.setattr(scm.logger, "warning", lambda message: warnings.append(message))

        manager = ServiceConfigManager(config_path=str(tmp_path / "absent.json"))

        assert manager.configs == {}
        assert warnings == ["未发现历史配置，将创建新配置"]

    def test_invalid_json_logs_error(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.json"
        path.write_text("{broken", encoding="utf-8")
        errors = []
        monkeypatch.setattr(scm.logger, "error", lambda message: errors.append(message))

        manager = ServiceConfigManager(config_path=str(path))

        assert manager.configs == {}
        assert errors and errors[0].startswith("加载配置失败:")

    def test_services_not_a_list_logs_error(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps({"services": {"a": 1}}), encoding="utf-8")
        errors = []
        monkeypatch.setattr(scm.logger, "error", lambda message: errors.append(message))

        manager = ServiceConfigManager(config_path=str(path))

        assert manager.configs == {}
        assert errors == [f"配置格式非法(services 非列表)，忽略: {path}"]

    def test_valid_configs_keep_existing_fields(self, tmp_path):
        path = tmp_path / "cfg.json"
        path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "port": 8000,
                            "process_signature": "a_app.py",
                            "name": "a",
                            "display_name": "服务A",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        manager = ServiceConfigManager(config_path=str(path))

        assert manager.configs["8000_a_app.py"]["display_name"] == "服务A"

    def test_skipped_entries_logged(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.json"
        path.write_text(
            json.dumps({"services": [{"port": 1}, {"port": 2, "process_signature": "x"}]}),
            encoding="utf-8",
        )
        warnings = []
        monkeypatch.setattr(scm.logger, "warning", lambda message: warnings.append(message))

        manager = ServiceConfigManager(config_path=str(path))

        assert list(manager.configs) == ["2_x"]
        assert warnings[-1] == "跳过 1 条缺少 port/process_signature 的非法配置项"


class TestSave:
    def test_save_sorts_and_writes(self, manager, tmp_path):
        manager.configs["b"] = {"port": 9000, "name": "b"}
        manager.configs["a"] = {"port": 8000, "name": "a"}

        manager.save_configs()

        payload = json.loads((tmp_path / "cfg" / "services.json").read_text(encoding="utf-8"))
        assert [cfg["port"] for cfg in payload["services"]] == [8000, 9000]
        assert "last_updated" in payload

    def test_save_failure_is_logged(self, manager, monkeypatch):
        critical = []
        monkeypatch.setattr(scm.logger, "critical", lambda message: critical.append(message))

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(scm.os, "makedirs", boom)

        manager.save_configs()

        assert critical == ["保存配置失败: disk full"]

    def test_save_without_directory_component(self, tmp_path):
        manager = ServiceConfigManager(config_path="relative-config.json")
        manager.configs["x"] = {"port": 1}

        manager.save_configs()

        assert manager.configs["x"]["port"] == 1


class TestGetOrCreate:
    def test_existing_config_is_returned(self, manager, monkeypatch):
        info = {"name": "python", "cmdline": "python app.py"}
        first = manager.get_or_create_config(8000, info)
        monkeypatch.setattr(
            scm.ServiceConfigManager, "_generate_temp_name",
            lambda *_a, **_k: pytest.fail("should reuse existing config"),
        )

        second = manager.get_or_create_config(8000, info)

        assert second is first

    def test_new_config_fields(self, manager):
        config = manager.get_or_create_config(
            8000, {"name": "python", "cmdline": "python /srv/app.py"}
        )

        assert config["id"] == "8000_python_app.py"
        assert config["port"] == 8000
        assert config["display_name"] == "Python应用:srv"
        assert config["auto_start"] is False
        assert config["learned"] is False
        assert config["fuse_retry_times"] == 0
        assert config["startup_timeout"] == 30

    def test_new_config_is_persisted(self, manager, tmp_path):
        manager.get_or_create_config(8000, {"name": "svc", "cmdline": ""})

        payload = json.loads((tmp_path / "cfg" / "services.json").read_text(encoding="utf-8"))
        assert payload["services"][0]["port"] == 8000

    def test_signature_falls_back_to_process_name(self, manager):
        config = manager.get_or_create_config(8100, {"name": "worker", "cmdline": "run"})

        assert config["process_signature"] == "worker_worker"

    def test_missing_process_info_fields_use_defaults(self, manager):
        config = manager.get_or_create_config(8200, {})

        assert config["process_name"] == "unknown"
        assert config["cmdline"] == ""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("redis-server", "Redis缓存:6379"),
            ("mysqld", "MySQL数据库:3306"),
            ("postgres", "PostgreSQL:5432"),
            ("nginx", "Nginx代理:80"),
        ],
    )
    def test_temp_names_for_known_services(self, manager, name, expected):
        port = int(expected.rsplit(":", 1)[1])
        assert manager._generate_temp_name(port, name, "") == expected

    def test_python_temp_name_uses_path_segment(self, manager):
        assert (
            manager._generate_temp_name(8000, "Python3", "/srv/my-app/main.py")
            == "Python应用:my-app"
        )

    def test_python_temp_name_uses_last_directory(self, manager):
        assert (
            manager._generate_temp_name(8000, "python", "/var/www/app/main.py")
            == "Python应用:app"
        )

    def test_python_temp_name_supports_windows_paths(self, manager):
        assert (
            manager._generate_temp_name(8000, "python", r"C:\apps\worker\main.py")
            == "Python应用:worker"
        )

    def test_python_temp_name_without_path_segment(self, manager):
        assert manager._generate_temp_name(8000, "python", "python main.py") == "python:8000"

    def test_unknown_process_temp_name(self, manager):
        assert manager._generate_temp_name(7000, "custom", "") == "custom:7000"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("redis", "docker restart redis-6379"),
            ("mysqld", "systemctl restart mysql"),
            ("nginx", "nginx -s reload"),
            ("worker", "# 请手动配置重启命令: worker"),
        ],
    )
    def test_restart_command_guesses(self, manager, name, expected):
        assert manager._guess_restart_cmd(name, 6379) == expected


class TestUpdateAndQuery:
    def test_update_existing_name(self, manager):
        manager.get_or_create_config(8000, {"name": "svc", "cmdline": ""})
        key = manager.get_service_key(8000, "svc_svc")

        manager.update_display_name(8000, "svc_svc", "业务服务")

        assert manager.configs[key]["display_name"] == "业务服务"
        assert manager.configs[key]["learned"] is True

    def test_update_missing_name_logs_error(self, manager, monkeypatch):
        errors = []
        monkeypatch.setattr(scm.logger, "error", lambda message: errors.append(message))

        manager.update_display_name(1, "missing", "x")

        assert errors == ["未找到服务配置: 1_missing"]

    def test_get_enabled_services_filters_auto_start(self, manager):
        manager.configs = {
            "a": {"auto_start": True},
            "b": {"auto_start": False},
            "c": {},
        }

        assert manager.get_enabled_services() == [{"auto_start": True}]

    def test_get_service_key_format(self, manager):
        assert manager.get_service_key(8080, "sig") == "8080_sig"
