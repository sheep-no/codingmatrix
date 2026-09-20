"""
配置热重载

支持运行时动态修改配置，无需重启服务
"""
import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """配置变更记录"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: float


class ConfigWatcher:
    """
    配置文件监听器

    监听配置文件变化，触发回调
    """

    def __init__(
        self,
        config_file: str = ".env",
        poll_interval: float = 5.0,
        on_change: Optional[Callable[[str, Any, Any], None]] = None,
    ):
        self.config_file = Path(config_file)
        self.poll_interval = poll_interval
        self._last_mtime: float = 0
        self._callbacks: Dict[str, Callable] = {}
        # 变更记录钩子，由 HotReloadConfig 注入 record_change
        self._on_change = on_change
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

    def watch(self, key: str, callback: Callable):
        """
        监听配置项变化

        Args:
            key: 配置项名
            callback: 变更回调，签名为 (key, old_value, new_value) -> None
        """
        self._callbacks[key] = callback
        logger.info(f"配置监听已注册 | key={key}")

    def unwatch(self, key: str):
        """取消监听"""
        if key in self._callbacks:
            del self._callbacks[key]
            logger.info(f"配置监听已取消 | key={key}")

    async def _poll(self):
        """轮询配置文件变化"""
        while self._running:
            try:
                if self.config_file.exists():
                    current_mtime = self.config_file.stat().st_mtime

                    if current_mtime != self._last_mtime and self._last_mtime > 0:
                        logger.info(f"配置文件变化检测到 | file={self.config_file}")
                        await self._reload_config()
                        self._last_mtime = current_mtime

                    elif self._last_mtime == 0:
                        self._last_mtime = current_mtime

            except Exception as e:
                logger.error(f"配置轮询异常: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _reload_config(self):
        """重新加载配置"""
        try:
            from dotenv import dotenv_values
            new_config = dotenv_values(self.config_file)
        except Exception as e:
            logger.error(f"配置重载失败: {e}")
            return

        for key, callback in self._callbacks.items():
            if key not in new_config:
                continue

            old_value = getattr(self._get_settings(), key, None)
            new_value = new_config[key]
            if str(old_value) == str(new_value):
                continue

            logger.info(f"配置变更 | key={key} | old={old_value} | new={new_value}")
            if self._on_change is not None:
                try:
                    self._on_change(key, old_value, new_value)
                except Exception as e:
                    logger.error(f"配置变更记录失败 | key={key} | error={e}")
            await self._invoke_callback(key, callback, old_value, new_value)

    async def _invoke_callback(self, key: str, callback: Callable, old_value: Any, new_value: Any):
        """执行单个变更回调，隔离异常并兼容 async 回调"""
        try:
            result = callback(key, old_value, new_value)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.error(f"配置变更回调执行失败 | key={key} | error={e}")

    def _get_settings(self):
        """获取当前设置"""
        try:
            from app.core.config import settings
            return settings
        except Exception:
            return None

    async def start(self):
        """启动监听"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._poll())
        logger.info(f"配置监听已启动 | file={self.config_file} | interval={self.poll_interval}s")

    async def stop(self):
        """停止监听"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("配置监听已停止")


class HotReloadConfig:
    """
    热重载配置管理器

    支持：
    - 配置变更监听
    - 动态更新应用配置
    - 变更历史记录
    """

    def __init__(self):
        self._watchers: Dict[str, ConfigWatcher] = {}
        self._change_history: list[ConfigChange] = []
        self._max_history = 100
        self._lock = threading.RLock()

    def register_watcher(self, name: str, config_file: str = ".env", poll_interval: float = 5.0):
        """注册配置监听器"""
        if name not in self._watchers:
            self._watchers[name] = ConfigWatcher(
                config_file, poll_interval, on_change=self.record_change
            )
        return self._watchers[name]

    def get_watcher(self, name: str) -> Optional[ConfigWatcher]:
        """获取监听器"""
        return self._watchers.get(name)

    async def start_all(self):
        """启动所有监听器"""
        for watcher in self._watchers.values():
            await watcher.start()

    async def stop_all(self):
        """停止所有监听器"""
        for watcher in self._watchers.values():
            await watcher.stop()

    def record_change(self, key: str, old_value: Any, new_value: Any):
        """记录配置变更"""
        with self._lock:
            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=new_value,
                timestamp=time.time()
            )
            self._change_history.append(change)

            if len(self._change_history) > self._max_history:
                self._change_history.pop(0)

    def get_change_history(self, key: Optional[str] = None, limit: int = 10) -> list:
        """获取变更历史"""
        with self._lock:
            if key:
                history = [c for c in self._change_history if c.key == key]
            else:
                history = list(self._change_history)
            return history[-limit:]


_hot_reload_config: Optional[HotReloadConfig] = None


def get_hot_reload_config() -> HotReloadConfig:
    """获取热重载配置单例"""
    global _hot_reload_config
    if _hot_reload_config is None:
        _hot_reload_config = HotReloadConfig()
    return _hot_reload_config
