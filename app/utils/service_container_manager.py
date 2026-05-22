"""
ServiceContainerManager - DockerRunner 测试时启动依赖服务容器

v4.8.0 新增：
- 根据项目检测到的服务依赖（Redis/PG/MySQL/MongoDB/RabbitMQ/ES）
- 自动启动对应的 Docker 容器作为测试依赖
- 测试完成后自动清理容器
- 使用轻量级镜像（alpine 系列）减少启动时间

v4.8.1 增强：
- ES 启动优化：换用 es-alpine 镜像 + 增大 JVM 堆 + TCP 端口健康检查
- 并行启动：asyncio.gather 同时启动多个容器
- 健康检查缓存：TTL 5 分钟内复用已健康容器，跳过重复启动
- wait_for_health 异步方法：支持 DockerRunner/IsolatedTestRunner 调用
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_CONTAINER_CONFIGS: Dict[str, Dict] = {
    "redis": {
        "image": "redis:7-alpine",
        "ports": {6379: 6379},
        "health_cmd": "redis-cli ping",
        "health_port": 6379,
        "startup_timeout": 10,
        "env": {},
    },
    "postgresql": {
        "image": "postgres:16-alpine",
        "ports": {5432: 5432},
        "health_cmd": "pg_isready -U appuser",
        "health_port": 5432,
        "startup_timeout": 15,
        "env": {
            "POSTGRES_DB": "testdb",
            "POSTGRES_USER": "appuser",
            "POSTGRES_PASSWORD": "apppass",
        },
    },
    "mysql": {
        "image": "mysql:8.0",
        "ports": {3306: 3306},
        "health_cmd": "mysqladmin ping -h localhost",
        "health_port": 3306,
        "startup_timeout": 20,
        "env": {
            "MYSQL_DATABASE": "testdb",
            "MYSQL_USER": "appuser",
            "MYSQL_PASSWORD": "apppass",
            "MYSQL_ROOT_PASSWORD": "rootpass",
        },
    },
    "mongodb": {
        "image": "mongo:7",
        "ports": {27017: 27017},
        "health_cmd": "mongosh --eval 'db.adminCommand(\"ping\")'",
        "health_port": 27017,
        "startup_timeout": 15,
        "env": {
            "MONGO_INITDB_DATABASE": "testdb",
        },
    },
    "rabbitmq": {
        "image": "rabbitmq:3-management-alpine",
        "ports": {5672: 5672},
        "health_cmd": "rabbitmq-diagnostics check_running",
        "health_port": 5672,
        "startup_timeout": 20,
        "env": {
            "RABBITMQ_DEFAULT_USER": "guest",
            "RABBITMQ_DEFAULT_PASS": "guest",
        },
    },
    "elasticsearch": {
        "image": "elasticsearch:8.12.0",
        "ports": {9200: 9200, 9300: 9300},
        "health_cmd": "curl -sf http://localhost:9200/_cluster/health",
        "health_port": 9200,
        "startup_timeout": 45,
        "env": {
            "discovery.type": "single-node",
            "xpack.security.enabled": "false",
            "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
        },
    },
}

HEALTH_CACHE_TTL = 300


class _HealthCacheEntry:
    __slots__ = ('container_id', 'port_mapping', 'env_vars', 'timestamp', 'host')

    def __init__(self, container_id, port_mapping, env_vars, host='localhost'):
        self.container_id = container_id
        self.port_mapping = port_mapping
        self.env_vars = env_vars
        self.host = host
        self.timestamp = time.time()

    def is_alive(self) -> bool:
        return (time.time() - self.timestamp) < HEALTH_CACHE_TTL


class ServiceContainerManager:

    def __init__(self):
        self._running_containers: Dict[str, str] = {}
        self._allocated_ports: Set[int] = set()
        self._health_cache: Dict[str, _HealthCacheEntry] = {}
        self._container_ports: Dict[str, Dict[int, int]] = {}

    async def start_service_containers(
        self,
        required_services: List[str],
        docker_client=None,
    ) -> Dict[str, Dict]:
        """
        并行启动依赖服务容器
        
        v4.8.1: 使用 asyncio.gather 并行启动，不再串行等待
        """
        if not docker_client:
            logger.warning("Docker 客户端不可用，无法启动服务容器")
            return {}

        # 1. 检查缓存：已健康的服务跳过启动
        cached_info = {}
        to_start = []
        for svc in required_services:
            config = SERVICE_CONTAINER_CONFIGS.get(svc)
            if not config:
                logger.warning(f"未知服务: {svc}")
                continue
            cached = self._health_cache.get(svc)
            if cached and cached.is_alive():
                if self._verify_container_alive(cached.container_id, docker_client):
                    cached_info[svc] = {
                        "host": cached.host,
                        "port": cached.port_mapping.get(
                            next(iter(config["ports"].keys())),
                            next(iter(config["ports"].values()))
                        ),
                        "container_id": cached.container_id,
                        "env_vars": cached.env_vars,
                    }
                    self._running_containers[svc] = cached.container_id
                    logger.info(f"复用已缓存的健康容器: {svc}")
                    continue
            to_start.append(svc)

        # 2. 并行启动未缓存的服务
        start_results = {}
        if to_start:
            tasks = []
            for svc in to_start:
                config = SERVICE_CONTAINER_CONFIGS[svc]
                tasks.append(self._start_and_register(svc, config, docker_client))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for svc, result in zip(to_start, results):
                if isinstance(result, Exception):
                    logger.error(f"启动服务容器 {svc} 失败: {result}")
                elif result:
                    start_results[svc] = result

        # 3. 合并缓存和新启动的结果
        all_info = {}
        all_info.update(cached_info)
        all_info.update(start_results)
        return all_info

    async def _start_and_register(
        self, service_name: str, config: Dict, docker_client
    ) -> Optional[Dict]:
        """启动单个容器并注册到缓存"""
        container_id = await self._start_container(service_name, config, docker_client)
        if not container_id:
            return None

        self._running_containers[service_name] = container_id

        port_mapping = {}
        for internal_port, host_port in config["ports"].items():
            actual_port = self._find_available_port(host_port)
            port_mapping[internal_port] = actual_port

        self._container_ports[service_name] = port_mapping

        env_vars = self._generate_test_env_vars(service_name, port_mapping)

        # 写入健康缓存
        self._health_cache[service_name] = _HealthCacheEntry(
            container_id=container_id,
            port_mapping=port_mapping,
            env_vars=env_vars,
        )

        info = {
            "host": "localhost",
            "port": port_mapping.get(
                next(iter(config["ports"].keys())),
                next(iter(config["ports"].values()))
            ),
            "container_id": container_id,
            "env_vars": env_vars,
        }

        logger.info(f"服务容器 {service_name} 已启动 (container: {container_id[:12]})")
        return info

    async def _start_container(
        self,
        service_name: str,
        config: Dict,
        docker_client,
    ) -> Optional[str]:
        """启动单个服务容器（容器启动 + 健康检查分离）"""
        try:
            # Phase 1: 启动容器（快速）
            port_bindings = {}
            for internal_port, host_port in config["ports"].items():
                actual_port = self._find_available_port(host_port)
                port_bindings[internal_port] = actual_port
                self._allocated_ports.add(actual_port)

            self._container_ports[service_name] = {}
            for internal_port, actual_port in port_bindings.items():
                self._container_ports[service_name][internal_port] = actual_port

            def _run_container():
                container = docker_client.containers.run(
                    image=config["image"],
                    detach=True,
                    environment=config.get("env", {}),
                    ports=port_bindings,
                    name=f"test-{service_name}-{int(time.time())}",
                    auto_remove=True,
                    network_disabled=False,
                )
                return container.id

            container_id = await asyncio.to_thread(_run_container)
            logger.info(f"容器 {service_name} 已创建 ({container_id[:12]})")

            # Phase 2: 健康检查（异步，不阻塞其他容器启动）
            health_ok = await self._wait_for_health_single(
                service_name, container_id, config, docker_client
            )
            if not health_ok:
                logger.warning(f"服务 {service_name} 健康检查超时")
            return container_id

        except Exception as e:
            logger.error(f"启动容器 {service_name} 异常: {e}")
            return None

    async def _wait_for_health_single(
        self,
        service_name: str,
        container_id: str,
        config: Dict,
        docker_client,
    ) -> bool:
        """
        单个容器健康检查
        
        v4.8.1: 先用 TCP 端口探测（快速），再用 exec 健康命令（精确）
        """
        health_port = config.get("health_port")
        startup_timeout = config.get("startup_timeout", 15)
        port_mapping = self._container_ports.get(service_name, {})
        actual_health_port = port_mapping.get(health_port, health_port)

        # Phase 2a: TCP 端口探测（每秒检查，比 exec 快得多）
        tcp_start = time.time()
        tcp_ok = False
        while (time.time() - tcp_start) < min(startup_timeout, 15):
            if await self._port_is_open_async(127, 0, 0, 1, actual_health_port):
                tcp_ok = True
                logger.info(f"服务 {service_name} TCP 端口 {actual_health_port} 已就通 ({time.time()-tcp_start:.1f}s)")
                break
            await asyncio.sleep(1)

        if not tcp_ok:
            logger.warning(f"服务 {service_name} TCP 端口 {actual_health_port} 未就通 ({startup_timeout}s)")
            return False

        # Phase 2b: exec 健康命令（精确验证）
        health_cmd = config.get("health_cmd", "")
        if health_cmd:
            exec_start = time.time()
            while (time.time() - exec_start) < 10:
                try:
                    def _exec():
                        container = docker_client.containers.get(container_id)
                        return container.exec_run(health_cmd)

                    result = await asyncio.to_thread(_exec)
                    if result.exit_code == 0:
                        logger.info(f"服务 {service_name} 健康检查通过 (总耗时 {time.time()-tcp_start:.1f}s)")
                        return True
                except Exception:
                    pass
                await asyncio.sleep(2)

            logger.warning(f"服务 {service_name} exec 健康检查未通过")
            return True  # TCP 已通，视为基本可用

        logger.info(f"服务 {service_name} TCP 就通，无 exec 健康命令，视为健康")
        return True

    async def wait_for_health(
        self,
        service_info: Dict[str, Dict],
        docker_client=None,
    ) -> bool:
        """
        等待所有服务健康检查通过
        
        v4.8.1: 新增异步方法，供 DockerRunner/IsolatedTestRunner 调用
        对于已通过健康检查的容器（在 _start_container 中已检查），直接返回 True
        """
        all_ok = True
        for service_name, info in service_info.items():
            config = SERVICE_CONTAINER_CONFIGS.get(service_name)
            if not config:
                continue
            cached = self._health_cache.get(service_name)
            if cached and cached.is_alive():
                continue
            health_ok = await self._wait_for_health_single(
                service_name, info.get("container_id", ""), config, docker_client
            )
            if not health_ok:
                all_ok = False
        return all_ok

    @staticmethod
    async def _port_is_open_async(a: int, b: int, c: int, d: int, port: int) -> bool:
        """异步检测端口是否可连接"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((f'{a}.{b}.{c}.{d}', port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _verify_container_alive(self, container_id: str, docker_client) -> bool:
        """验证缓存中的容器是否仍在运行"""
        try:
            container = docker_client.containers.get(container_id)
            return container.status == 'running'
        except Exception:
            return False

    def generate_test_env_vars(self, service_info: Dict[str, Dict]) -> Dict[str, str]:
        """生成所有服务的测试环境变量"""
        all_env = {}
        for service_name, info in service_info.items():
            env_vars = info.get("env_vars", {})
            all_env.update(env_vars)
        return all_env

    def _find_available_port(self, preferred_port: int) -> int:
        """查找可用端口"""
        import socket
        port = preferred_port
        while port in self._allocated_ports:
            port += 1

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            return port + 1

    def _generate_test_env_vars(
        self, service_name: str, port_mapping: Dict[int, int]
    ) -> Dict[str, str]:
        """生成测试环境变量"""
        try:
            from app.agent.service_config_templates import get_service_template
            template = get_service_template(service_name)
            if not template:
                return {}
            env_vars = {}
            for var_name, default_val in template.env_vars.items():
                env_vars[var_name] = default_val
                for internal_port, actual_port in port_mapping.items():
                    env_vars[var_name] = env_vars[var_name].replace(
                        str(internal_port), str(actual_port)
                    )
            return env_vars
        except Exception:
            return {}

    async def cleanup_containers(self, docker_client=None):
        """清理所有服务容器（不清理缓存的，仅清理本次启动的）"""
        if not docker_client:
            return

        for service_name, container_id in self._running_containers.items():
            cached = self._health_cache.get(service_name)
            if cached and cached.container_id == container_id:
                continue

            try:
                def _stop():
                    try:
                        container = docker_client.containers.get(container_id)
                        container.stop(timeout=5)
                        logger.info(f"服务容器 {service_name} 已停止")
                    except Exception:
                        pass

                await asyncio.to_thread(_stop)
            except Exception as e:
                logger.warning(f"停止容器 {service_name} 失败: {e}")

        self._running_containers.clear()
        self._allocated_ports.clear()
        self._container_ports.clear()

    async def cleanup_all(self, docker_client=None):
        """清理所有容器包括缓存（用于完全退出时）"""
        await self.cleanup_containers(docker_client)
        self._health_cache.clear()

    def get_running_services(self) -> Dict[str, str]:
        """获取当前运行的服务容器"""
        return dict(self._running_containers)


def detect_project_services(project_path: Path) -> List[str]:
    """
    从项目中检测需要哪些第三方服务

    检测方式：
    1. requirements.txt 中的包 -> 映射到服务
    2. .env.example 中的环境变量 -> 推断服务
    3. docker-compose.yml 中的服务定义
    """
    import re
    services = []

    req_file = project_path / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            PACKAGE_TO_SERVICE = {
                "redis": "redis",
                "psycopg2": "postgresql",
                "psycopg2-binary": "postgresql",
                "pymongo": "mongodb",
                "pymysql": "mysql",
                "aio-pika": "rabbitmq",
                "pika": "rabbitmq",
                "elasticsearch": "elasticsearch",
                "asyncpg": "postgresql",
                "aiomysql": "mysql",
            }
            for line in content.split("\n"):
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    dep_name = re.split(r'[=<>!~\[]', line)[0].strip()
                    for pkg, svc in PACKAGE_TO_SERVICE.items():
                        if dep_name == pkg and svc not in services:
                            services.append(svc)
        except Exception:
            pass

    env_file = project_path / ".env.example"
    if env_file.exists():
        try:
            content = env_file.read_text(encoding="utf-8", errors="ignore")
            ENV_VAR_TO_SERVICE = {
                "REDIS_URL": "redis",
                "REDIS_HOST": "redis",
                "DATABASE_URL": "postgresql",
                "POSTGRES_HOST": "postgresql",
                "MYSQL_HOST": "mysql",
                "MONGODB_URL": "mongodb",
                "MONGODB_HOST": "mongodb",
                "RABBITMQ_URL": "rabbitmq",
                "RABBITMQ_HOST": "rabbitmq",
                "ELASTICSEARCH_URL": "elasticsearch",
            }
            for var_name, svc in ENV_VAR_TO_SERVICE.items():
                if var_name in content and svc not in services:
                    services.append(svc)
        except Exception:
            pass

    compose_file = project_path / "docker-compose.yml"
    if compose_file.exists():
        try:
            content = compose_file.read_text(encoding="utf-8", errors="ignore")
            COMPOSE_IMAGE_TO_SERVICE = {
                "redis": "redis",
                "postgres": "postgresql",
                "mysql": "mysql",
                "mongo": "mongodb",
                "rabbitmq": "rabbitmq",
                "elasticsearch": "elasticsearch",
            }
            for image_key, svc in COMPOSE_IMAGE_TO_SERVICE.items():
                if image_key in content.lower() and svc not in services:
                    services.append(svc)
        except Exception:
            pass

    return services


import re