"""
Docker 容器化运行管理器
提供安全隔离的项目验证环境

安全特性:
- 文件系统隔离 (只读根文件系统)
- 网络隔离 (完全禁用或限制访问)
- 资源限制 (CPU/内存/进程数)
- 提权防护 (no-new-privileges)
- 能力限制 (丢弃所有 Linux capabilities)
- 自动清理 (运行后删除容器)

@author: Security Team
@version: 1.0.0
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

try:
    import docker
    from docker.models.containers import Container
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    Container = None  # type: ignore
    DockerException = Exception  # type: ignore
    NotFound = Exception  # type: ignore
    APIError = Exception  # type: ignore
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Docker 库未安装，容器化验证不可用")

logger = logging.getLogger(__name__)


@dataclass
class DockerSecurityConfig:
    """Docker 安全配置"""
    # 基础镜像
    image: str = "python:3.11-slim"

    # 资源限制
    cpu_quota: int = 200000  # CPU 限制 (2 核，单位：微秒)
    cpu_period: int = 100000
    mem_limit: str = "2g"  # 内存限制
    pids_limit: int = 100  # 进程数限制

    # 网络配置
    network_enabled: bool = False  # 是否启用网络（默认禁用，更安全）
    network_mode: str = "none"   # bridge/none

    # 文件系统安全
    read_only: bool = True  # 只读根文件系统
    tmpfs: Dict[str, str] = field(default_factory=lambda: {
        "/tmp": "rw,noexec,nosuid,size=512m",
        "/app": "rw,noexec,nosuid,size=1g"
    })

    # 安全选项
    security_opt: List[str] = field(default_factory=lambda: [
        "no-new-privileges:true",  # 禁止提权
    ])

    # Linux 能力限制
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])  # 丢弃所有能力
    cap_add: List[str] = field(default_factory=lambda: [])  # 不添加任何能力

    # 文件描述符限制
    ulimits: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "nofile", "soft": 1024, "hard": 2048},
        {"name": "nproc", "soft": 50, "hard": 100}
    ])

    # 工作目录
    working_dir: str = "/app"

    # 自动删除
    remove: bool = True  # 运行后自动删除容器


@dataclass
class ValidationResult:
    """验证结果"""
    success: bool = False
    method: str = "docker"
    exit_code: int = -1
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration: float = 0.0


class DockerRunner:
    """Docker 容器化运行器"""
    
    # 禁止的危险命令模式
    FORBIDDEN_PATTERNS = [
        r'os\.system\s*\(',
        r'subprocess\.(run|call|Popen)\s*\(',
        r'eval\s*\(',
        r'exec\s*\(',
        r'__import__\s*\(',
        r'open\s*\(["\']\/etc\/',
        r'shutil\.(rmtree|copy2)\s*\(',
        r'pty\.spawn\s*\(',
        r'pty\.fork\s*\(',
    ]
    
    # 允许安装的包白名单
    # 来自 requirements.txt + 常见 Python 包
    ALLOWED_PACKAGES = {
        # -----------------------------------------------------------------------------
        # FastAPI 生态
        # -----------------------------------------------------------------------------
        'fastapi', 'starlette', 'uvicorn', 'gunicorn', 'hypercorn',

        # -----------------------------------------------------------------------------
        # 数据库 (SQLAlchemy Async)
        # -----------------------------------------------------------------------------
        'sqlalchemy', 'alembic', 'aiosqlite', 'aiomysql', 'pymysql',
        'psycopg2', 'psycopg2-binary', 'pymongo', 'redis',

        # -----------------------------------------------------------------------------
        # Pydantic & Settings
        # -----------------------------------------------------------------------------
        'pydantic', 'pydantic-settings',

        # -----------------------------------------------------------------------------
        # Authentication & Security
        # -----------------------------------------------------------------------------
        'python-jose', 'cryptography', 'passlib', 'bcrypt',

        # -----------------------------------------------------------------------------
        # HTTP 客户端 & 文件处理
        # -----------------------------------------------------------------------------
        'httpx', 'aiohttp', 'requests', 'urllib3',
        'python-multipart', 'aiofiles',
        'Pillow', 'PIL',

        # -----------------------------------------------------------------------------
        # AI & NLP
        # -----------------------------------------------------------------------------
        'tiktoken', 'transformers', 'tokenizers',

        # -----------------------------------------------------------------------------
        # HTML 解析
        # -----------------------------------------------------------------------------
        'beautifulsoup4', 'bs4', 'lxml', 'html5lib',

        # -----------------------------------------------------------------------------
        # 日志 & 监控
        # -----------------------------------------------------------------------------
        'structlog', 'python-json-logger', 'psutil',

        # -----------------------------------------------------------------------------
        # 限流
        # -----------------------------------------------------------------------------
        'slowapi',

        # -----------------------------------------------------------------------------
        # 任务调度
        # -----------------------------------------------------------------------------
        'apscheduler',

        # -----------------------------------------------------------------------------
        # 缓存
        # -----------------------------------------------------------------------------
        'redis', 'hiredis', 'cachetools',

        # -----------------------------------------------------------------------------
        # WebSocket
        # -----------------------------------------------------------------------------
        'websockets',

        # -----------------------------------------------------------------------------
        # 工具库
        # -----------------------------------------------------------------------------
        'python-dotenv', 'anyio', 'tenacity',
        'click', 'typer', 'rich', 'tqdm', 'shutil',

        # -----------------------------------------------------------------------------
        # 数据处理 & 可视化
        # -----------------------------------------------------------------------------
        'pandas', 'numpy', 'scipy', 'matplotlib', 'seaborn', 'plotly',

        # -----------------------------------------------------------------------------
        # Office 文档
        # -----------------------------------------------------------------------------
        'python-pptx', 'python-docx', 'openpyxl', 'xlrd', 'xlwt', 'xlsxwriter',

        # -----------------------------------------------------------------------------
        # YAML/TOML/JSON
        # -----------------------------------------------------------------------------
        'pyyaml', 'toml', 'tomli', 'json5', 'orjson', 'ujson',

        # -----------------------------------------------------------------------------
        # 加密
        # -----------------------------------------------------------------------------
        'cryptography', 'pycryptodome', 'pyopenssl',

        # -----------------------------------------------------------------------------
        # 游戏开发
        # -----------------------------------------------------------------------------
        'pygame', 'pyglet', 'arcade', 'pymunk',

        # -----------------------------------------------------------------------------
        # 测试
        # -----------------------------------------------------------------------------
        'pytest', 'pytest-asyncio', 'pytest-cov', 'unittest', 'nose',
        'allure-pytest', 'pytest-mock', 'pytest-xdist',

        # -----------------------------------------------------------------------------
        # 图像处理 & CV
        # -----------------------------------------------------------------------------
        'opencv-python', 'opencv-python-headless', 'scikit-image', 'imageio',

        # -----------------------------------------------------------------------------
        # 机器学习
        # -----------------------------------------------------------------------------
        'scikit-learn', 'tensorflow', 'torch', 'keras',

        # -----------------------------------------------------------------------------
        # 网络 & API
        # -----------------------------------------------------------------------------
        'flask', 'django', 'bottle', 'falcon', 'grpcio', 'grpcio-tools',

        # -----------------------------------------------------------------------------
        # 日期时间
        # -----------------------------------------------------------------------------
        'python-dateutil', 'pytz', 'zoneinfo',

        # -----------------------------------------------------------------------------
        # 其他常用
        # -----------------------------------------------------------------------------
        'email-validator', 'itsdangerous', 'jinja2', 'markupsafe',
        'sqlparse', 'typing-extensions', 'greenlet', 'asyncpg',
        'aiosqlite', 'aiofiles', 'tenacity', 'cachetools',
        'fastapi-utils', 'python-multipart', 'python-jose[cryptography]',

        # -----------------------------------------------------------------------------
        # 容错 & 重试
        # -----------------------------------------------------------------------------
        'tenacity', 'cachetools', 'backoff',

        # -----------------------------------------------------------------------------
        # 临时文件 & 进程
        # -----------------------------------------------------------------------------
        'tempfile', 'tempdir', 'shutil', 'subprocess', 'multiprocessing',
    }
    
    def __init__(
        self,
        config: Optional[DockerSecurityConfig] = None,
        timeout: int = 300,
        enable_security_scan: bool = True
    ):
        """
        初始化 Docker 运行器

        Args:
            config: Docker 安全配置
            timeout: 容器运行超时 (秒)
            enable_security_scan: 是否启用安全扫描
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError("Docker 库未安装，请先执行：pip install docker")

        self.config = config or DockerSecurityConfig()
        self.timeout = timeout
        self.enable_security_scan = enable_security_scan
        self.client = None

        self._resource_config: Dict[str, str] = {}
        self._init_docker_client()
        self._pull_image()
        self._load_resource_config()

    async def _load_resource_config_async(self):
        """异步加载资源配置（从数据库）"""
        try:
            from app.services.resource_config import resource_config_service
            self._resource_config = await resource_config_service.get_all_configs()

            if self._resource_config.get("docker_max_memory"):
                self.config.mem_limit = self._resource_config.get("docker_max_memory")

            if self._resource_config.get("docker_initial_memory"):
                self.config.mem_reservation = self._resource_config.get("docker_initial_memory")

            docker_image = self._resource_config.get("docker_image")
            if docker_image:
                self.config.image = docker_image

            logger.info(f"资源配置已加载 | memory={self.config.mem_limit} | image={self.config.image}")
        except Exception as e:
            logger.warning(f"加载资源配置失败，使用默认配置: {e}")

    def _load_resource_config(self):
        """同步加载资源配置（尝试加载，失败时使用默认）"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._load_resource_config_async())
            else:
                loop.run_until_complete(self._load_resource_config_async())
        except Exception as e:
            logger.warning(f"同步加载资源配置失败，使用默认配置: {e}")

    async def get_max_containers(self) -> int:
        """获取最大容器数量"""
        try:
            from app.services.resource_config import resource_config_service
            value = await resource_config_service.get_config("docker_max_containers", "5")
            return int(value)
        except Exception:
            return 5

    async def can_run_container(self) -> tuple[bool, str]:
        """检查是否可以启动新容器"""
        max_containers = await self.get_max_containers()
        current_count = await self._get_running_container_count()

        if current_count >= max_containers:
            return False, f"容器数量已达上限 ({max_containers})"

        return True, "OK"

    async def _get_running_container_count(self) -> int:
        """获取当前运行的容器数量"""
        try:
            containers = self.client.containers.list(
                filters={"label": "ai.project.validator=true"}
            )
            return len(containers)
        except Exception as e:
            logger.warning(f"获取容器数量失败: {e}")
            return 0

    def _init_docker_client(self):
        """初始化 Docker 客户端"""
        try:
            self.client = docker.from_env()
            # 测试连接
            self.client.ping()
            logger.info("✅ Docker 客户端初始化成功")
        except DockerException as e:
            logger.error(f"❌ Docker 初始化失败：{e}")
            raise RuntimeError(f"Docker 不可用：{e}")
    
    def _pull_image(self):
        """拉取 Docker 镜像"""
        try:
            logger.info(f"[IMG] 检查镜像 | {self.config.image}")
            
            try:
                # 检查本地是否有镜像
                self.client.images.get(self.config.image)
                logger.info("✅ 镜像已存在")
            except NotFound:
                logger.info(f"⬇️  拉取镜像 | {self.config.image}")
                self.client.images.pull(self.config.image)
                logger.info("✅ 镜像拉取完成")
                
        except DockerException as e:
            logger.error(f"❌ 镜像拉取失败：{e}")
            raise RuntimeError(f"无法拉取镜像：{e}")
    
    def _scan_code_security(self, project_path: Path) -> List[str]:
        """
        安全扫描：检测代码中的危险模式
        
        Args:
            project_path: 项目路径
            
        Returns:
            警告信息列表
        """
        warnings = []
        
        if not self.enable_security_scan:
            return warnings
        
        logger.info(f"[SCAN] 开始安全扫描 | project: {project_path.name}")
        
        # 扫描 Python 文件
        py_files = list(project_path.rglob("*.py"))
        
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                lines = content.splitlines()
                
                for line_num, line in enumerate(lines, 1):
                    # 跳过注释
                    if line.strip().startswith('#'):
                        continue
                    
                    # 检查危险模式
                    for pattern in self.FORBIDDEN_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            warnings.append(
                                f"⚠️ {py_file.relative_to(project_path)}:{line_num} "
                                f"发现危险模式：{line.strip()[:100]}"
                            )
                
            except Exception as e:
                logger.debug(f"扫描文件失败 | {py_file}: {e}")

        if warnings:
            logger.warning(f"⚠️ 发现 {len(warnings)} 个安全警告")
        else:
            logger.info("✅ 安全扫描通过")

        return warnings

    async def run_validation(
        self,
        project_path: Path,
        requirements_path: Optional[Path] = None,
        test_command: str = "python main.py",
        install_deps: bool = True
    ) -> ValidationResult:
        """
        在 Docker 容器中运行项目验证
        
        Args:
            project_path: 项目路径
            requirements_path: requirements.txt 路径
            test_command: 测试命令
            install_deps: 是否安装依赖
            
        Returns:
            验证结果
        """
        result = ValidationResult()
        container = None
        start_time = asyncio.get_event_loop().time()

        try:
            # 检查是否可以启动容器
            can_run, reason = await self.can_run_container()
            if not can_run:
                result.error = reason
                result.success = False
                return result

            # 安全扫描
            security_warnings = self._scan_code_security(project_path)
            result.logs.extend(security_warnings)

            # 根据配置设置网络模式
            if self.config.network_enabled:
                self.config.network_mode = "bridge"
                logger.info("[NET] 网络模式: 启用 (用户明确要求)")
            else:
                self.config.network_mode = "none"
                logger.info("[SEC] 网络模式: 禁用 (默认安全模式)")

            # 准备容器配置
            config = self._prepare_container_config(project_path)
            
            logger.info(f"[DOCKER] 创建容器 | project: {project_path.name}")
            
            # 创建容器
            container = self.client.containers.create(**config)
            
            # 启动容器
            await asyncio.to_thread(container.start)
            logger.info(f"▶️ 容器已启动 | id: {container.short_id}")
            
            # 安装依赖
            if install_deps and requirements_path and requirements_path.exists():
                logger.info("[PKG] 安装依赖")
                install_result = await self._exec_command(
                    container,
                    "pip install --no-cache-dir --disable-pip-version-check -r requirements.txt"
                )
                result.logs.extend(install_result.logs)
                result.errors.extend(install_result.errors)
                
                if install_result.exit_code != 0:
                    result.error = "依赖安装失败"
                    result.logs.extend([
                        f"❌ 依赖安装失败，exit code: {install_result.exit_code}"
                    ])
                    return result
            
            # 运行测试
            logger.info(f"▶️ 运行测试 | cmd: {test_command}")
            test_result = await self._exec_command(container, test_command)
            result.logs.extend(test_result.logs)
            result.errors.extend(test_result.errors)
            result.exit_code = test_result.exit_code
            
            if test_result.exit_code == 0:
                result.success = True
                logger.info(f"✅ 验证通过 | project: {project_path.name}")
            else:
                result.error = "测试执行失败"
                logger.warning(f"⚠️ 验证失败 | project: {project_path.name} | exit_code: {result.exit_code}")
            
            return result
            
        except asyncio.TimeoutError:
            result.error = f"容器运行超时 ({self.timeout}秒)"
            logger.error(f"⏰ 超时 | project: {project_path.name}")
            result.errors.append(result.error)
            return result
            
        except DockerException as e:
            result.error = f"Docker 错误：{str(e)}"
            logger.error(f"❌ Docker 错误 | {e}")
            result.errors.append(result.error)
            return result
        
        except Exception as e:
            result.error = f"未知错误：{str(e)}"
            logger.error(f"❌ 未知错误 | {e}", exc_info=True)
            result.errors.append(result.error)
            return result
            
        finally:
            # 清理容器
            if container:
                await self._cleanup_container(container)
            
            result.duration = asyncio.get_event_loop().time() - start_time
            logger.info(f"⏱️ 验证耗时 | {result.duration:.2f}s")
    
    def _prepare_container_config(self, project_path: Path) -> Dict[str, Any]:
        """准备容器配置"""
        
        config = {
            "image": self.config.image,
            "command": "tail -f /dev/null",  # 保持容器运行
            "working_dir": self.config.working_dir,
            "detach": True,
            "remove": self.config.remove,
            
            # 资源限制
            "cpu_quota": self.config.cpu_quota,
            "cpu_period": self.config.cpu_period,
            "mem_limit": self.config.mem_limit,
            "mem_reservation": getattr(self.config, "mem_reservation", "256m"),
            "pids_limit": self.config.pids_limit,
            
            # 网络隔离
            "network_mode": self.config.network_mode,
            
            # 文件系统安全
            "read_only": self.config.read_only,
            "tmpfs": self.config.tmpfs,
            
            # 挂载项目目录
            "volumes": {
                str(project_path.resolve()): {
                    "bind": "/app",
                    "mode": "rw"
                }
            },
            
            # 安全选项
            "security_opt": self.config.security_opt,
            
            # Linux 能力限制
            "cap_drop": self.config.cap_drop,
            "cap_add": self.config.cap_add,
            
            # 文件描述符限制
            "ulimits": [
                docker.types.Ulimit(
                    name=ulimit["name"],
                    soft=ulimit["soft"],
                    hard=ulimit["hard"]
                )
                for ulimit in self.config.ulimits
            ],
            
            # 标签
            "labels": {
                "ai.project.validator": "true",
                "ai.project.path": str(project_path),
                "ai.created_at": str(asyncio.get_event_loop().time())
            }
        }
        
        logger.debug(
            f"[CFG] 容器配置 | "
            f"CPU: {self.config.cpu_quota/self.config.cpu_period:.0f}核, "
            f"Memory: {self.config.mem_limit}, "
            f"PIDs: {self.config.pids_limit}"
        )
        
        return config
    
    async def _exec_command(
        self,
        container: Container,
        command: str
    ) -> Dict[str, Any]:
        """
        在容器中执行命令
        
        Args:
            container: 容器实例
            command: 命令
            
        Returns:
            执行结果 {logs, errors, exit_code}
        """
        result = {
            "logs": [],
            "errors": [],
            "exit_code": -1
        }
        
        try:
            # 执行命令
            exec_result = await asyncio.to_thread(
                container.exec_run,
                cmd=command,
                demux=True,
                stdout=True,
                stderr=True,
                tty=False
            )
            
            result["exit_code"] = exec_result.exit_code
            
            # 解析输出
            if exec_result.output:
                stdout, stderr = exec_result.output
                
                if stdout:
                    lines = stdout.decode('utf-8', errors='ignore').splitlines()
                    result["logs"].extend(lines)
                    # 只记录前 10 行到日志，避免过多
                    for line in lines[:10]:
                        logger.debug(f"[LOG] STDOUT: {line[:200]}")
                    if len(lines) > 10:
                        logger.debug(f"... 还有 {len(lines) - 10} 行")
                
                if stderr:
                    lines = stderr.decode('utf-8', errors='ignore').splitlines()
                    result["errors"].extend(lines)
                    for line in lines[:10]:
                        logger.warning(f"⚠️ STDERR: {line[:200]}")
            
            return result
            
        except Exception as e:
            result["errors"].append(f"命令执行失败：{str(e)}")
            logger.error(f"❌ 命令执行失败 | {e}")
            return result
    
    async def _cleanup_container(self, container: Container):
        """清理容器"""
        try:
            logger.info(f"[CLEAN] 清理容器 | id: {container.short_id}")
            
            # 停止容器
            await asyncio.to_thread(container.stop, timeout=5)
            
            # 删除容器
            await asyncio.to_thread(container.remove, force=True)
            
            logger.info(f"✅ 容器已清理 | id: {container.short_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ 清理失败 | {e}")
    
    def get_container_stats(self, container_id: str) -> Optional[Dict[str, Any]]:
        """
        获取容器资源使用统计
        
        Args:
            container_id: 容器 ID
            
        Returns:
            资源使用统计
        """
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            return {
                "cpu_percent": stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0),
                "memory_usage": stats.get("memory_stats", {}).get("usage", 0),
                "memory_limit": stats.get("memory_stats", {}).get("limit", 0),
                "network_rx": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0),
                "network_tx": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0),
            }
        except Exception as e:
            logger.error(f"获取容器统计失败：{e}")
            return None


# 便捷函数
async def validate_project_in_docker(
    project_path: Path,
    requirements_path: Optional[Path] = None,
    test_command: str = "python main.py",
    timeout: int = 300,
    cpu_limit: float = 2.0,
    memory_limit: str = "2g",
    network_enabled: bool = False
) -> ValidationResult:
    """
    便捷函数：在 Docker 容器中验证项目

    Args:
        project_path: 项目路径
        requirements_path: requirements.txt 路径
        test_command: 测试命令
        timeout: 超时时间 (秒)
        cpu_limit: CPU 核心数限制
        memory_limit: 内存限制
        network_enabled: 是否启用网络（默认禁用，更安全）

    Returns:
        验证结果
    """
    # 创建安全配置
    config = DockerSecurityConfig(
        cpu_quota=int(cpu_limit * 100000),
        mem_limit=memory_limit,
        network_enabled=network_enabled
    )

    # 创建运行器
    runner = DockerRunner(config=config, timeout=timeout)

    # 运行验证
    return await runner.run_validation(
        project_path=project_path,
        requirements_path=requirements_path,
        test_command=test_command
    )
