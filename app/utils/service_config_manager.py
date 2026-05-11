# utils/service_config_manager.py
import json
import os
import re
import threading
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ServiceConfigManager:
    """服务配置管理器：记住用户私设的名称"""

    def __init__(self, config_path: str = "data/service_configs.json"):
        self.config_path = config_path
        self.configs: Dict[str, dict] = {}
        self.logger = logger
        self._lock = threading.RLock()
        self.load_configs()

    def load_configs(self):
        """加载配置（同步IO即可，文件很小）"""
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for cfg in data.get("services", []):
                            key = f"{cfg['port']}_{cfg['process_signature']}"
                            if "name" not in cfg:
                                cfg["name"] = cfg.get("process_name", "unknown")
                                self.logger.warning(f"为配置 {key} 补全缺失的 'name' 字段")
                            self.configs[key] = cfg
                    self.logger.info(f"已加载 {len(self.configs)} 个服务配置")
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    self.logger.error(f"加载配置失败: {self.config_path} - {e}")
            else:
                self.logger.warning("未发现历史配置，将创建新配置")

    def save_configs(self):
        """保存配置（同步IO，带错误处理）"""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                config_list = list(self.configs.values())
                config_list.sort(key=lambda x: x['port'])

                data = {
                    "last_updated": datetime.now().isoformat(),
                    "services": config_list
                }

                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                self.logger.info(f"配置已保存: {self.config_path}")
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                self.logger.critical(f"保存配置失败: {e}")

    def get_service_key(self, port: int, process_signature: str) -> str:
        return f"{port}_{process_signature}"

    def get_or_create_config(self, port: int, process_info: dict) -> dict:
        """获取或创建配置（核心方法）"""
        with self._lock:
            process_name = process_info.get('name', 'unknown')
            cmdline = process_info.get('cmdline', '')

            match = re.search(r'([\w-]+\.(py|js|jar))', cmdline)
            signature_file = match.group(1) if match else process_name

            process_signature = f"{process_name}_{signature_file}"
            key = self.get_service_key(port, process_signature)

            if key in self.configs:
                config = self.configs[key]
                self.logger.debug(
                    f"识别到已知服务: {config['display_name']} (端口:{port})"
                )
                return config

            # 新服务：创建配置
            self.logger.info(f"发现新服务: 端口{port}, 进程:{process_name}")
            temp_name = self._generate_temp_name(port, process_name, cmdline)

            config = {
                "id": key,
                "port": port,
                "process_signature": process_signature,
                "name": process_name,
                "process_name": process_name,
                "cmdline": cmdline,
                "display_name": temp_name,
                "restart_cmd": self._guess_restart_cmd(process_name, port),
                "startup_timeout": 30,
                "check_interval": 10,
                "fuse_enabled": True,
                "fuse_cooldown": 300,
                "fuse_retry_times": 0,
                "fuse_retry_count": 0,
                "auto_start": False,
                "learned": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            self.configs[key] = config
            self.save_configs()

            self.logger.warning(
                f"临时名称: {temp_name}，建议访问管理界面修改为业务名称"
            )
            return config

    def _generate_temp_name(self, port: int, process_name: str, cmdline: str) -> str:
        """智能生成临时名称"""
        name_lower = process_name.lower()

        if 'redis' in name_lower:
            return f"Redis缓存:{port}"
        elif 'mysql' in name_lower:
            return f"MySQL数据库:{port}"
        elif 'postgres' in name_lower:
            return f"PostgreSQL:{port}"
        elif 'nginx' in name_lower:
            return f"Nginx代理:{port}"
        elif 'python' in name_lower:
            match = re.search(r'/([\w-]+)/', cmdline)
            if match:
                app_name = match.group(1)
                return f"Python应用:{app_name}"

        return f"{process_name}:{port}"

    def _guess_restart_cmd(self, process_name: str, port: int) -> str:
        """猜测重启命令（兜底方案）"""
        name_lower = process_name.lower()

        if 'redis' in name_lower:
            return f"docker restart redis-{port}"
        elif 'mysql' in name_lower:
            return f"systemctl restart mysql"
        elif 'nginx' in name_lower:
            return f"nginx -s reload"
        else:
            return f"# 请手动配置重启命令: {process_name}"

    def update_display_name(self, port: int, process_signature: str, new_name: str):
        """更新显示名称"""
        with self._lock:
            key = self.get_service_key(port, process_signature)

            if key in self.configs:
                self.configs[key]["display_name"] = new_name
                self.configs[key]["learned"] = True
                self.configs[key]["updated_at"] = datetime.now().isoformat()
                self.save_configs()
                self.logger.info(f"已更新服务名称: {new_name}")
            else:
                self.logger.error(f"未找到服务配置: {key}")

    def get_enabled_services(self) -> List[dict]:
        """获取所有启用的服务"""
        enabled = [cfg for cfg in self.configs.values() if cfg.get("auto_start")]
        self.logger.debug(f"获取到 {len(enabled)} 个已启用的服务")
        return enabled