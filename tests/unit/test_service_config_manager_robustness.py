"""ServiceConfigManager.load_configs 对损坏持久化配置的健壮性回归。

原先 load_configs 直接下标 cfg['port'] / cfg['process_signature']，
任一损坏条目或非 dict 顶层都会抛 KeyError/AttributeError（均不在
ValueError/TypeError/RuntimeError/OSError 白名单内），使
ServiceConfigManager() 构造整体失败，get_guardian() 单例不可用、
所有守护端点 500。
"""
import json

from app.utils.service_config_manager import ServiceConfigManager


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_malformed_entry_is_skipped_valid_entries_loaded(tmp_path):
    config_path = _write(
        tmp_path / "cfg.json",
        {
            "services": [
                {"port": 8000, "process_signature": "a_app.py", "name": "svc-a"},
                {"port": 8001},  # 缺 process_signature
                "not-a-dict",
            ]
        },
    )

    manager = ServiceConfigManager(config_path=config_path)

    assert list(manager.configs.keys()) == ["8000_a_app.py"]


def test_non_dict_top_level_does_not_crash(tmp_path):
    config_path = _write(tmp_path / "cfg.json", ["unexpected", "list"])

    manager = ServiceConfigManager(config_path=config_path)

    assert manager.configs == {}


def test_missing_name_and_display_name_are_backfilled(tmp_path):
    config_path = _write(
        tmp_path / "cfg.json",
        {
            "services": [
                {
                    "port": 9000,
                    "process_signature": "b_app.py",
                    "process_name": "worker",
                }
            ]
        },
    )

    manager = ServiceConfigManager(config_path=config_path)

    cfg = manager.configs["9000_b_app.py"]
    assert cfg["name"] == "worker"
    assert cfg["display_name"] == "worker"
