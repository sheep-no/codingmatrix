"""
测试热重载
"""
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from app.utils.hot_reload import (
    ConfigWatcher,
    HotReloadConfig,
    get_hot_reload_config
)


class TestConfigWatcher:
    """测试配置监听器"""

    def test_create_watcher(self):
        """测试创建监听器"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST=value\n")
            temp_path = f.name

        try:
            watcher = ConfigWatcher(temp_path, poll_interval=1.0)
            assert watcher.config_file == Path(temp_path)
            assert watcher.poll_interval == 1.0
        finally:
            os.unlink(temp_path)

    def test_watch_unwatch(self):
        """测试监听和取消监听"""
        watcher = ConfigWatcher(".env")
        callback_called = []

        def callback(key, old, new):
            callback_called.append((key, old, new))

        watcher.watch("TEST_KEY", callback)
        assert "TEST_KEY" in watcher._callbacks

        watcher.unwatch("TEST_KEY")
        assert "TEST_KEY" not in watcher._callbacks


class TestHotReloadConfig:
    """测试热重载配置"""

    def test_singleton(self):
        """测试单例"""
        config1 = get_hot_reload_config()
        config2 = get_hot_reload_config()
        assert config1 is config2

    def test_register_watcher(self):
        """测试注册监听器"""
        config = get_hot_reload_config()
        watcher = config.register_watcher("test", ".env", poll_interval=5.0)
        assert watcher is not None
        assert config.get_watcher("test") is watcher

    def test_record_change(self):
        """测试记录变更"""
        config = get_hot_reload_config()
        config.record_change("LOG_LEVEL", "INFO", "DEBUG")
        config.record_change("MAX_CONNECTIONS", 100, 200)

        history = config.get_change_history()
        assert len(history) == 2

        filtered = config.get_change_history(key="LOG_LEVEL")
        assert len(filtered) == 1
        assert filtered[0].new_value == "DEBUG"


class TestConfigWatcherIntegration:
    """测试配置监听集成"""

    @pytest.mark.asyncio
    async def test_poll_detection(self):
        """测试轮询检测变化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("KEY1=value1\n")
            temp_path = f.name

        try:
            changes = []

            def on_change(key, old, new):
                changes.append((key, old, new))

            watcher = ConfigWatcher(temp_path, poll_interval=0.1)
            watcher.watch("KEY1", on_change)

            await watcher.start()
            await asyncio.sleep(0.2)

            with open(temp_path, 'w') as f:
                f.write("KEY1=newvalue1\n")

            await asyncio.sleep(0.3)

            await watcher.stop()

        finally:
            os.unlink(temp_path)
