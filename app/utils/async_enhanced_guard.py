# utils/async_enhanced_guard.py
import asyncio
import psutil
from typing import Dict, List, Optional
from app.utils.process_guard import AsyncProcessGuardian
from app.utils.service_config_manager import ServiceConfigManager
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker
import logging

logger = logging.getLogger(__name__)


class AsyncSmartGuardian(AsyncProcessGuardian):
    """异步智能守护：集成配置管理 + API 级熔断"""

    def __init__(self, check_interval: int = 10):
        """
        初始化智能守护

        :param check_interval: 检查间隔（秒）
        """
        super().__init__(check_interval)
        self.config_manager = ServiceConfigManager()
        self.monitor_task: Optional[asyncio.Task] = None
        self.logger = logger

        self._api_circuit_breaker = get_circuit_breaker(
            "guardian_api",
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout=60.0
            )
        )

    async def scan_and_learn(self, auto_enable_trusted: bool = False):
        """
        扫描并学习服务

        :param auto_enable_trusted: 是否自动启用可信服务
        """
        self.logger.info("扫描服务中（学习模式）...")

        # 扫描常见端口
        for port in [6379, 3306, 8000, 8080, 5000]:
            if not await self.is_port_open(port):
                continue

            pid = await self.find_pid_by_port(port)
            if not pid:
                continue

            # 获取进程信息
            try:
                process = psutil.Process(pid)
                process_info = {
                    "pid": pid,
                    "name": process.name(),
                    "cmdline": " ".join(process.cmdline())
                }
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                self.logger.warning(f"获取进程信息失败 PID={pid}: {e}")
                process_info = {"pid": pid, "name": "unknown", "cmdline": ""}

            # 获取或创建配置
            config = self.config_manager.get_or_create_config(port, process_info)

            # 自动启用可信服务
            if auto_enable_trusted and self.is_trusted(config):
                if not config["auto_start"]:
                    config["auto_start"] = True
                    self.config_manager.save_configs()
                    self.logger.info(f"自动启用监控: {config['display_name']}")

        self.logger.info(f"扫描完成，已学习 {len(self.config_manager.configs)} 个服务")

    async def start_monitoring_enabled_services(self):
        """启动所有已启用的监控"""
        services = self.config_manager.get_enabled_services()

        if services:
            self.monitor_task = asyncio.create_task(self.monitor_all(services))
            self.logger.info(f"已启动 {len(services)} 个服务的异步监控")
        else:
            self.logger.warning("没有已启用的服务需要监控")

    def is_trusted(self, config: dict) -> bool:
        """
        判断是否为可信服务

        策略：
        1. 常见基础设施服务（Redis/MySQL/Nginx等）
        2. 用户手动标记为启用的（auto_start=True）

        :param config: 服务配置
        :return: 是否可信
        """
        # 1. 基础设施服务（名称匹配）
        trusted_names = ["redis", "mysql", "postgres", "nginx"]
        name_lower = config["display_name"].lower()

        if any(t in name_lower for t in trusted_names):
            self.logger.debug(f"{config['display_name']} 是基础设施，标记为可信")
            return True

        # 2. 用户手动启用的（已经人工确认）
        if config.get("auto_start"):
            self.logger.debug(f"{config['display_name']} 已人工启用，标记为可信")
            return True

        return False

    async def shutdown(self):
        """优雅关闭：取消所有监控任务"""
        self.logger.info("正在停止异步进程守护...")

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("异步进程守护已停止")

    async def guarded_api_call(self, func, *args, **kwargs):
        """
        使用熔断器保护 API 调用

        当外部 API 连续失败时，快速返回错误，避免资源消耗

        Args:
            func: 要调用的异步函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerError: 熔断开启时
        """
        return await self._api_circuit_breaker.call(func, *args, **kwargs)

    def get_circuit_breaker_status(self) -> dict:
        """获取 API 熔断器状态"""
        return self._api_circuit_breaker.get_status()