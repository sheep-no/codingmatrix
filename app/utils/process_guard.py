import asyncio
import psutil
import socket
import platform
from datetime import datetime
from typing import Optional, Dict, List, Any
import os
import time
import logging
logger=logging.getLogger(__name__)


class AsyncProcessGuardian:
    """异步进程守护：单线程高效监控多个服务"""

    def __init__(self, check_interval: int = 10, max_restart_attempts: int = 3):
        self.check_interval = check_interval
        self.max_restart_attempts = max_restart_attempts
        self.restart_count: Dict[str, int] = {}
        self.service_state: Dict[str, dict] = {}
        self.logger = logger
        self.config_manager = None  # 由子类注入

    async def is_port_open(self, port: int, host: str = "127.0.0.1") -> bool:
        """异步端口检测"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=2
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            self.logger.error(f"端口检测异常 {host}:{port} - {e}")
            return False

    async def find_pid_by_port(self, port: int) -> Optional[int]:
        """异步查找PID"""
        system = platform.system()

        try:
            if system == "Windows":
                cmd = f"netstat -ano | findstr :{port}"
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                if proc.returncode == 0:
                    lines = stdout.decode().strip().split('\n')
                    for line in lines:
                        if f":{port}" in line and "LISTENING" in line:
                            parts = line.split()
                            return int(parts[-1])
            else:
                cmd = f"lsof -i :{port} -t"
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                if proc.returncode == 0:
                    return int(stdout.decode().strip())

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            self.logger.error(f"查找PID失败 端口{port} - {e}")

        return None

    async def kill_process(self, pid: int, graceful: bool = True) -> bool:
        """异步终止进程"""
        try:
            process = psutil.Process(pid)

            if graceful:
                self.logger.warning(f"发送SIGTERM到进程 {pid}")
                process.terminate()
                try:
                    await asyncio.wait_for(self._wait_process_exit(process), timeout=5)
                    self.logger.info(f"进程 {pid} 已优雅退出")
                    return True
                except asyncio.TimeoutError:
                    self.logger.warning(f"进程 {pid} 不响应SIGTERM，强制杀死")

            process.kill()
            self.logger.info(f"进程 {pid} 已强制终止")
            return True

        except psutil.NoSuchProcess:
            self.logger.warning(f"进程 {pid} 已不存在")
            return True
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            self.logger.error(f"终止进程 {pid} 失败 - {e}")
            return False

    async def _wait_process_exit(self, process: psutil.Process):
        """辅助协程：等待进程退出"""
        while process.is_running():
            await asyncio.sleep(0.1)

    async def restart_service(
            self,
            restart_cmd: str,
            cwd: Optional[str] = None,
            port: Optional[int] = None,
            startup_timeout: int = 30
    ) -> bool:
        """重启服务并等待其真正就绪"""
        try:
            self.logger.info(f"执行重启命令: {restart_cmd}")
            start_time = datetime.now()

            proc = await asyncio.create_subprocess_shell(
                restart_cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                self.logger.error(f"重启命令失败，返回码: {proc.returncode}")
                if stderr:
                    self.logger.error(f"错误信息: {stderr.decode().strip()}")
                return False

            self.logger.info("重启命令执行完成，开始等待服务就绪...")

            if port:
                if await self._wait_for_service_ready(port, startup_timeout):
                    elapsed = (datetime.now() - start_time).total_seconds()
                    self.logger.info(f"服务已就绪，总耗时: {elapsed:.2f}秒")
                    return True
                else:
                    self.logger.error(f"服务在 {startup_timeout} 秒内未能就绪")
                    return False
            else:
                self.logger.warning(f"未提供端口，无法主动探测，等待 {min(startup_timeout, 5)} 秒")
                await asyncio.sleep(min(startup_timeout, 5))
                return True

        except asyncio.TimeoutError:
            self.logger.error(f"重启命令超时")
            return False
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            self.logger.error(f"重启过程异常: {e}")
            return False

    async def _wait_for_service_ready(self, port: int, timeout: int) -> bool:
        """循环等待服务端口开放"""
        start_time = time.time()
        check_interval = 0.5

        while time.time() - start_time < timeout:
            if await self.is_port_open(port):
                wait_time = time.time() - start_time
                self.logger.info(f"端口 {port} 已开放，等待时间: {wait_time:.2f}秒")
                return True
            await asyncio.sleep(check_interval)

        self.logger.error(f"端口 {port} 在 {timeout} 秒内未开放")
        return False

    async def watch_port(self, config: dict):
        """异步监控单个服务（带用户配置的熔断策略）"""
        name = config["name"]
        port = config["port"]
        restart_cmd = config["restart_cmd"]
        cwd = config.get("cwd")
        startup_timeout = config.get("startup_timeout", 30)
        check_interval = config.get("check_interval", self.check_interval)

        # 熔断配置（用户可选项）
        fuse_enabled = config.get("fuse_enabled", True)
        fuse_cooldown = config.get("fuse_cooldown", 300)
        fuse_retry_times = config.get("fuse_retry_times", 0)

        if name not in self.restart_count:
            self.restart_count[name] = 0

        # 初始化熔断状态
        if name not in self.service_state:
            self.service_state[name] = {
                "state": "normal",
                "fuse_retry_count": 0,
                "last_fuse_time": 0.0,
                "cooldown": fuse_cooldown
            }

        self.logger.info(f"开始监控 {name} (端口:{port}) [熔断: {'启用' if fuse_enabled else '禁用'}]")

        while True:
            try:
                state = self.service_state[name]

                # 熔断状态处理 =====
                if state["state"] == "fused":
                    if not fuse_enabled:
                        self.logger.warning(f"{name} 熔断已禁用，永久停止监控")
                        break

                    elapsed = time.time() - state["last_fuse_time"]
                    remaining = state["cooldown"] - elapsed

                    if remaining > 0:
                        if int(remaining) % 60 == 0:
                            self.logger.debug(f"{name} 熔断冷却中，{int(remaining)}秒后重试")
                        await asyncio.sleep(check_interval)
                        continue
                    else:
                        # 检查重试次数限制
                        if fuse_retry_times > 0 and state["fuse_retry_count"] >= fuse_retry_times:
                            self.logger.critical(
                                f"{name} 熔断重试次数已达上限 {fuse_retry_times}，永久停止监控"
                            )
                            break

                        self.logger.info(
                            f"{name} 熔断冷却结束，第 {state['fuse_retry_count'] + 1} 次重试"
                        )
                        state["state"] = "normal"
                        self.restart_count[name] = 0

                # 正常监控逻辑 =====
                if not await self.is_port_open(port):
                    self.logger.error(f"{name} 端口{port} 失联！")

                    old_pid = await self.find_pid_by_port(port)
                    if old_pid:
                        self.logger.warning(f"发现旧进程PID {old_pid} 占用端口")
                        await self.kill_process(old_pid, graceful=True)

                    success = await self.restart_service(
                        restart_cmd, cwd, port, startup_timeout
                    )

                    if success:
                        self.restart_count[name] = 0
                        if state["fuse_retry_count"] > 0:
                            self.logger.info(f"{name} 恢复成功，熔断重试计数清零")
                            state["fuse_retry_count"] = 0
                    else:
                        self.restart_count[name] += 1
                        self.logger.warning(f"重启失败 {name} (第{self.restart_count[name]}次)")

                        if self.restart_count[name] >= self.max_restart_attempts:
                            if fuse_enabled:
                                state["state"] = "fused"
                                state["last_fuse_time"] = time.time()
                                state["cooldown"] = fuse_cooldown
                                state["fuse_retry_count"] += 1

                                self.logger.critical(
                                    f"{name} 触发熔断（累计失败 {state['fuse_retry_count']} 次），"
                                    f"冷却 {fuse_cooldown} 秒后重试"
                                )

                                # 持久化熔断计数
                                if self.config_manager:
                                    config["fuse_retry_count"] = state["fuse_retry_count"]
                                    key = f"{port}_{config['process_signature']}"
                                    self.config_manager.configs[key] = config
                                    self.config_manager.save_configs()
                            else:
                                self.logger.critical(
                                    f"{name} 连续失败 {self.max_restart_attempts} 次且熔断禁用，永久停止"
                                )
                                break
                else:
                    if self.restart_count.get(name, 0) > 0:
                        self.logger.info(f"{name} 状态正常，重置重启计数")
                        self.restart_count[name] = 0

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                self.logger.info(f"监控任务 {name} 被取消")
                break
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                self.logger.error(f"监控异常 {name}: {e}")
                await asyncio.sleep(check_interval)

    async def monitor_all(self, services: List[dict]):
        """异步监控所有服务"""
        tasks = [
            asyncio.create_task(self.watch_port(svc), name=f"monitor-{svc['name']}")
            for svc in services
        ]

        self.logger.info(f"已启动 {len(tasks)} 个监控任务")

        await asyncio.gather(*tasks, return_exceptions=True)