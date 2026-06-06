"""
TestRunner - 本地沙箱测试执行器（多语言增强版）

核心改进：
1. 多语言支持 - Python/JS/Go/Java/Rust 按需 subprocess 执行
2. FrameworkDetector 集成 - 自动检测 6 种测试框架
3. OutputParser 集成 - 统一解析多语言测试输出
4. ServiceContainerManager 集成 - Docker 不可用时仍可连接服务容器
5. 并发控制 - asyncio.Semaphore 限制同时运行数
6. 安全扫描统一 - 记录警告但不中止（与 DockerRunner 一致）
7. 包白名单扩展 - 合并 DockerRunner 白名单
"""

import asyncio
import logging
import os
import re
import shlex
import shutil
import signal
import sys
import tempfile
import venv as venv_mod
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from app.agent.tracing import traced
from app.agent.framework_detector import FrameworkDetector
from app.agent.output_parser import OutputParser

FORBIDDEN_PATTERNS = [
    r'os\.system\s*\(',
    r'subprocess\.(run|call|Popen)\s*\(',
    r'eval\s*\(',
    r'exec\s*\(',
    r'__import__\s*\(',
    r'open\s*\(["\']\/etc\/',
    r'shutil\.rmtree\s*\(',
    r'pty\.spawn\s*\(',
    r'pty\.fork\s*\(',
    r'socket\.socket\s*\(',
    r'http\.server\.',
]

ALLOWED_PIP_PACKAGES: Set[str] = {
    'pytest', 'pytest-asyncio', 'pytest-cov', 'pytest-timeout',
    'pytest-mock', 'pytest-xdist', 'nose', 'allure-pytest',

    'fastapi', 'starlette', 'uvicorn', 'gunicorn', 'hypercorn',
    'pydantic', 'pydantic-settings',

    'sqlalchemy', 'alembic', 'aiosqlite', 'aiomysql', 'pymysql',
    'psycopg2', 'psycopg2-binary', 'pymongo', 'redis', 'asyncpg',
    'aiofiles',

    'python-jose', 'cryptography', 'passlib', 'bcrypt',
    'python-multipart', 'email-validator', 'itsdangerous',

    'httpx', 'aiohttp', 'requests', 'urllib3', 'websockets',

    'python-dotenv', 'anyio', 'trio',
    'tenacity', 'cachetools', 'backoff',

    'pandas', 'numpy', 'scipy', 'matplotlib', 'seaborn', 'plotly',
    'scikit-learn', 'tiktoken', 'transformers', 'tokenizers',

    'beautifulsoup4', 'bs4', 'lxml', 'html5lib',
    'Pillow',

    'flask', 'django', 'bottle', 'falcon',
    'grpcio', 'grpcio-tools', 'slowapi', 'apscheduler',
    'structlog', 'python-json-logger', 'psutil',

    'pyyaml', 'toml', 'tomli', 'json5', 'orjson', 'ujson',
    'jinja2', 'markupsafe', 'sqlparse', 'typing-extensions', 'greenlet',

    'python-pptx', 'python-docx', 'openpyxl', 'xlrd', 'xlsxwriter',

    'coverage', 'unittest',
    'click', 'typer', 'rich', 'tqdm',

    'python-dateutil', 'pytz',

    'opencv-python', 'opencv-python-headless', 'scikit-image', 'imageio',
    'pygame', 'pyglet', 'arcade', 'pymunk',

    'hiredis',
}

ENV_WHITELIST: Set[str] = {
    'PATH', 'LANG', 'LC_ALL', 'LC_CTYPE',
    'TERM', 'TMPDIR', 'TEMP', 'TMP',
    'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE',
    'VIRTUAL_ENV', 'NODE_PATH',
    'HOME', 'GOPATH', 'GOCACHE', 'GOMODCACHE',
    'CARGO_HOME', 'JAVA_HOME', 'M2_HOME',
    'MYSQL_HOME', 'PGDATA',
}

SKIP_COPY_DIRS = {
    '__pycache__', 'node_modules', '.git', '.venv', 'venv',
    'dist', 'build', '.next', 'coverage', '.pytest_cache',
    'playwright-report', 'test-results', '.turbo', 'cache',
    '.tox', '.mypy_cache', '.ruff_cache', 'htmlcov',
    'target',
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

MAX_CONCURRENT_TESTS = 5


class _SemaphoreHolder:
    semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    if _SemaphoreHolder.semaphore is None:
        _SemaphoreHolder.semaphore = asyncio.Semaphore(MAX_CONCURRENT_TESTS)
    return _SemaphoreHolder.semaphore


@dataclass
class TestResult:
    success: bool
    total_tests: int
    passed: int
    failed: int
    errors: int
    logs: str
    failed_tests: List[str]
    security_warnings: List[str] = field(default_factory=list)
    method: str = "local_sandbox"
    language: str = "python"
    framework: str = "pytest"


class IsolatedTestRunner:
    """
    多语言本地沙箱测试执行器

    支持 Python/JS/Go/Java/Rust 5 种语言的按需 subprocess 测试执行。
    使用 FrameworkDetector 自动检测项目语言和测试框架，
    使用 OutputParser 统一解析多语言输出。
    """

    def __init__(
        self,
        project_path: Path,
        timeout: int = 120,
        max_log_bytes: int = 50000,
        enable_security_scan: bool = True,
        required_services: Optional[List[str]] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.timeout = timeout
        self.max_log_bytes = max_log_bytes
        self.enable_security_scan = enable_security_scan
        self.required_services = required_services or []

        self._temp_dir: Optional[Path] = None
        self._venv_dir: Optional[Path] = None
        self._work_dir: Optional[Path] = None
        self._venv_python: Optional[str] = None
        self._detected_config = None
        self._framework_detector = FrameworkDetector()

        self._service_container_mgr = None
        self._service_env_vars: Dict[str, str] = {}

    @traced("test.run", attributes={"component": "testing"})
    async def run_tests(
        self,
        test_paths: Optional[List[str]] = None,
        test_command: Optional[str] = None,
    ) -> TestResult:
        result = TestResult(
            success=False, total_tests=0, passed=0,
            failed=0, errors=0, logs="", failed_tests=[]
        )

        sem = _get_semaphore()
        async with sem:
            temp_dir_path: Optional[str] = None
            language = "python"
            framework = "unknown"

            try:
                # 1. 安全扫描（记录警告但不中止）
                if self.enable_security_scan:
                    result.security_warnings = self._scan_security()
                    if result.security_warnings:
                        logger.warning(
                            f"安全扫描发现 {len(result.security_warnings)} 个警告，继续运行测试"
                        )
                        result.logs = "\n".join(result.security_warnings[:20]) + "\n"

                # 2. 检测语言和测试框架
                self._detected_config = self._framework_detector.detect(self.project_path)
                language = self._detected_config.language
                framework = self._detected_config.framework
                result.language = language
                result.framework = framework
                logger.info(f"检测到语言/框架: {language}/{framework}")

                # 3. 尝试启动依赖服务容器
                await self._start_service_containers()

                # 4. 对于 Python 项目，使用 venv 隔离
                if language == "python":
                    temp_dir_path = tempfile.mkdtemp(prefix="cm_test_")
                    self._temp_dir = Path(temp_dir_path)
                    self._venv_dir = self._temp_dir / "venv"
                    self._work_dir = self._temp_dir / "project"

                    logger.info(f"创建 Python 隔离沙箱: {self._temp_dir}")

                    await self._create_venv()
                    if not self._venv_python:
                        result.logs = "无法创建虚拟环境"
                        return result

                    await self._copy_project()
                    if not self._work_dir.exists():
                        result.logs = "项目复制失败"
                        return result

                    install_ok = await self._install_dependencies()
                    if not install_ok:
                        logger.warning("部分依赖安装失败，继续尝试运行测试")

                # 5. 非 Python 项目直接在原目录执行
                else:
                    self._work_dir = self.project_path
                    logger.info(f"非 Python 项目，直接在原目录执行: {language}")

                # 6. 构建测试命令
                cmd = await self._build_test_command(test_paths, test_command)
                targets = test_paths or self._find_test_files()
                if not targets and not test_command and language == "python":
                    result.success = True
                    result.logs = "未找到测试文件"
                    return result

                # 7. 执行测试
                logger.info(f"执行测试: {cmd} (语言: {language})")
                result = await self._execute_test(cmd)

                # 8. 使用 OutputParser 解析输出
                result = self._parse_with_output_parser(result)

            except Exception as e:
                logger.error(f"测试执行异常: {e}", exc_info=True)
                result.logs = f"执行异常: {str(e)}"
                result.errors = 1

            finally:
                await self._cleanup_service_containers()

                if language == "python":
                    await self._cleanup()
                    if temp_dir_path and Path(temp_dir_path).exists():
                        try:
                            shutil.rmtree(temp_dir_path, ignore_errors=True)
                        except Exception as e:
                            logger.debug(f"清理临时目录失败 {temp_dir_path}：{e}")

        return result

    # ==================== 服务容器集成 ====================

    LOCAL_SERVICE_PORTS = {
        'redis': 6379,
        'postgresql': 5432,
        'mysql': 3306,
        'mongodb': 27017,
        'rabbitmq': 5672,
        'elasticsearch': 9200,
    }

    LOCAL_SERVICE_START_COMMANDS = {
        'redis': 'redis-server 或 docker run -d -p 6379:6379 redis:7-alpine',
        'postgresql': 'systemctl start postgresql 或 docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass postgres:16-alpine',
        'mysql': 'systemctl start mysql 或 docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=pass mysql:8.0',
        'mongodb': 'systemctl start mongod 或 docker run -d -p 27017:27017 mongo:7',
        'rabbitmq': 'systemctl start rabbitmq-server 或 docker run -d -p 5672:5672 rabbitmq:3-management-alpine',
        'elasticsearch': 'systemctl start elasticsearch 或 docker run -d -p 9200:9200 -e discovery.type=single-node elasticsearch:8.12.0',
    }

    LOCAL_SERVICE_ENV_VARS = {
        'redis': {'REDIS_URL': 'redis://127.0.0.1:6379'},
        'postgresql': {
            'DATABASE_URL': 'postgresql://appuser:apppass@127.0.0.1:5432/testdb',
            'POSTGRES_HOST': '127.0.0.1',
            'POSTGRES_PORT': '5432',
            'POSTGRES_DB': 'testdb',
            'POSTGRES_USER': 'appuser',
            'POSTGRES_PASSWORD': 'apppass',
        },
        'mysql': {
            'DATABASE_URL': 'mysql://appuser:apppass@127.0.0.1:3306/testdb',
            'MYSQL_HOST': '127.0.0.1',
            'MYSQL_PORT': '3306',
            'MYSQL_DB': 'testdb',
            'MYSQL_USER': 'appuser',
            'MYSQL_PASSWORD': 'apppass',
        },
        'mongodb': {
            'MONGODB_URL': 'mongodb://127.0.0.1:27017/testdb',
            'MONGO_HOST': '127.0.0.1',
            'MONGO_PORT': '27017',
            'MONGO_DB': 'testdb',
        },
        'rabbitmq': {
            'RABBITMQ_URL': 'amqp://guest:guest@127.0.0.1:5672',
        },
        'elasticsearch': {
            'ES_URL': 'http://127.0.0.1:9200',
        },
    }

    async def _start_service_containers(self):
        """
        启动项目依赖的服务

        Docker 可用 -> 自动启动容器
        Docker 不可用 -> 检测本地服务，未运行则提示启动指南 + 设置 Mock 环境变量
        """
        if not self.required_services:
            return

        try:
            import docker
            client = docker.from_env()
            client.ping()
        except Exception as e:
            logger.info(f"Docker 不可用，检测本地服务: {e}")
            await self._check_local_services(self.required_services)
            return

        try:
            from app.utils.service_container_manager import ServiceContainerManager
            self._service_container_mgr = ServiceContainerManager()
            service_containers = await self._service_container_mgr.start_service_containers(
                self.required_services, client
            )

            if service_containers:
                self._service_env_vars = self._service_container_mgr.generate_test_env_vars(
                    service_containers
                )
                logger.info(f"服务容器已启动: {list(service_containers.keys())}")

                health_ok = await self._service_container_mgr.wait_for_health(
                    service_containers, client
                )
                if not health_ok:
                    logger.warning("依赖服务健康检查失败")
                else:
                    logger.info("所有服务健康检查通过")

        except Exception as e:
            logger.warning(f"启动服务容器失败: {e}")

    async def _check_local_services(self, services: List[str]):
        """Docker 不可用时检测本地服务，未运行则提示并降级"""
        missing = []
        found_env = {}

        for svc in services:
            port = self.LOCAL_SERVICE_PORTS.get(svc)
            if port and await self._port_is_open(127, 0, 0, 1, port):
                logger.info(f"本地 {svc} 已运行 (端口 {port})")
                found_env.update(self.LOCAL_SERVICE_ENV_VARS.get(svc, {}))
            else:
                missing.append(svc)

        if found_env:
            self._service_env_vars = found_env

        if missing:
            logger.warning("")
            logger.warning("=" * 55)
            logger.warning("本地服务未运行，测试可能失败")
            logger.warning("=" * 55)
            for svc in missing:
                cmd = self.LOCAL_SERVICE_START_COMMANDS.get(svc, f'请手动启动 {svc}')
                logger.warning(f"  {svc}: {cmd}")
            logger.warning("")
            logger.warning("建议安装 Docker 以自动管理服务容器")
            logger.warning("=" * 55)

            self._service_env_vars.setdefault('USE_MOCK_SERVICES', 'true')
            self._service_env_vars['MISSING_SERVICES'] = ','.join(missing)

    @staticmethod
    async def _port_is_open(a: int, b: int, c: int, d: int, port: int) -> bool:
        """检测指定 IP:端口 是否有服务监听"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((f'{a}.{b}.{c}.{d}', port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"端口检测异常 {a}.{b}.{c}.{d}:{port}：{e}")
            return False

    async def _cleanup_service_containers(self):
        if self._service_container_mgr:
            try:
                import docker
                client = docker.from_env()
                await self._service_container_mgr.cleanup_containers(client)
                logger.info("服务容器已清理")
            except Exception as e:
                logger.warning(f"清理服务容器失败: {e}")
            self._service_container_mgr = None

    # ==================== Python 隔离环境 ====================

    async def _create_venv(self):
        try:
            venv_mod.create(
                str(self._venv_dir),
                with_pip=True,
                clear=True,
            )
            if sys.platform == 'win32':
                self._venv_python = str(self._venv_dir / "Scripts" / "python.exe")
            else:
                self._venv_python = str(self._venv_dir / "bin" / "python")
            logger.info(f"venv 创建成功: {self._venv_python}")
        except Exception as e:
            logger.error(f"venv 创建失败: {e}")
            self._venv_python = None

    async def _copy_project(self):
        src = self.project_path
        dst = self._work_dir

        def _should_copy(item: Path) -> bool:
            name = item.name
            if name in SKIP_COPY_DIRS:
                return False
            if name.startswith('.') and name not in ('.env.example', '.coveragerc'):
                return False
            if item.is_file() and item.stat().st_size > MAX_FILE_SIZE_BYTES:
                return False
            return True

        try:
            for item in src.iterdir():
                if not _should_copy(item):
                    continue
                rel = item.relative_to(src)
                target = dst / rel
                if item.is_dir():
                    shutil.copytree(
                        str(item), str(target),
                        ignore=shutil.ignore_patterns(*SKIP_COPY_DIRS)
                    )
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(target))
            logger.info(f"项目复制完成: {src} -> {dst}")
        except Exception as e:
            logger.error(f"项目复制失败: {e}")

    async def _install_dependencies(self) -> bool:
        ok = True

        req_files = [
            self._work_dir / "requirements.txt",
            self._work_dir / "requirements-test.txt",
        ]
        for req_file in req_files:
            if not req_file.exists():
                continue
            filtered_req = self._temp_dir / f"filtered_{req_file.name}"
            filtered = self._filter_requirements(req_file, filtered_req)
            if not filtered:
                logger.warning(f"{req_file.name}: 无白名单内依赖可安装")
                continue
            ok &= await self._pip_install(str(filtered_req))

        pkg_json = self._work_dir / "package.json"
        if pkg_json.exists():
            node_modules = self._work_dir / "node_modules"
            src_node = self.project_path / "node_modules"
            if src_node.exists() and not node_modules.exists():
                shutil.copytree(str(src_node), str(node_modules))
                logger.info("复用已有 node_modules")

        return ok

    def _filter_requirements(self, req_file: Path, output: Path) -> bool:
        allowed_lines = []
        try:
            content = req_file.read_text(encoding='utf-8', errors='ignore')
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                pkg_name = re.split(r'[=<>!\s\[;]', line)[0].strip().lower()
                pkg_base = re.split(r'\[', pkg_name)[0].strip()
                if pkg_base in ALLOWED_PIP_PACKAGES or pkg_name in ALLOWED_PIP_PACKAGES:
                    allowed_lines.append(line)
        except Exception as e:
            logger.warning(f"读取 requirements 失败: {e}")
            return False

        if not allowed_lines:
            return False

        output.write_text("\n".join(allowed_lines) + "\n", encoding='utf-8')
        logger.info(f"依赖过滤: {len(allowed_lines)} 个白名单包通过")
        return True

    async def _pip_install(self, req_file: str) -> bool:
        cmd = [
            self._venv_python, '-m', 'pip', 'install',
            '--no-cache-dir',
            '--disable-pip-version-check',
            '--quiet',
            '-r', req_file,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                err = stderr.decode('utf-8', errors='replace')[:500]
                logger.warning(f"pip install 失败: {err}")
                return False
            return True
        except asyncio.TimeoutError:
            logger.warning("pip install 超时 (120s)")
            proc.kill()
            return False
        except Exception as e:
            logger.warning(f"pip install 异常: {e}")
            return False

    # ==================== 多语言测试命令构建 ====================

    def _find_test_files(self) -> List[str]:
        tests = []
        for d in ['tests', 'test', '__tests__']:
            if (self._work_dir / d).exists():
                tests.append(str(self._work_dir / d))
        if not tests:
            for f in self._work_dir.rglob('test_*.py'):
                if '__pycache__' not in str(f):
                    tests.append(str(f))
        if not tests:
            for f in self._work_dir.rglob('*_test.py'):
                if '__pycache__' not in str(f):
                    tests.append(str(f))
        return tests

    async def _build_test_command(
        self,
        test_paths: Optional[List[str]],
        test_command: Optional[str],
    ) -> List[str]:
        if test_command:
            return shlex.split(test_command)

        if self._detected_config and self._detected_config.test_command:
            cmd = self._detected_config.test_command
            language = self._detected_config.language

            if language == "python":
                targets = test_paths or self._find_test_files()
                if not targets:
                    targets = [str(self._work_dir)]
                return [
                    self._venv_python, '-m', 'pytest',
                    *targets,
                    '-v', '--tb=short', '--color=no',
                ]

            return shlex.split(cmd)

        targets = test_paths or self._find_test_files()
        if not targets:
            targets = [str(self._work_dir)]

        pkg_json = self._work_dir / "package.json"
        if pkg_json.exists():
            npm_cmd = 'pnpm' if (self._work_dir / 'pnpm-lock.yaml').exists() else 'npm'
            return [npm_cmd, 'run', 'test']

        return [
            self._venv_python or sys.executable, '-m', 'pytest',
            *targets,
            '-v', '--tb=short', '--color=no',
        ]

    # ==================== 测试执行 ====================

    async def _execute_test(self, cmd: List[str]) -> TestResult:
        env = self._build_sandbox_env()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._work_dir),
                env=env,
                preexec_fn=os.setsid if sys.platform != 'win32' else None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                if sys.platform != 'win32':
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                else:
                    proc.kill()
                await proc.wait()
                return TestResult(
                    success=False, total_tests=0, passed=0,
                    failed=0, errors=0,
                    logs=f"测试超时 ({self.timeout}s)，进程已终止",
                    failed_tests=[], method="local_sandbox",
                    language=self._detected_config.language if self._detected_config else "python",
                    framework=self._detected_config.framework if self._detected_config else "pytest",
                )

            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            combined = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"
            if len(combined) > self.max_log_bytes:
                combined = combined[:self.max_log_bytes] + f"\n...截断 (原始 {len(combined)} bytes)"

            language = self._detected_config.language if self._detected_config else "python"

            return TestResult(
                success=proc.returncode == 0,
                total_tests=0,
                passed=0,
                failed=0,
                errors=0,
                logs=combined,
                failed_tests=[],
                method="local_sandbox",
                language=language,
                framework=self._detected_config.framework if self._detected_config else "pytest",
            )

        except Exception as e:
            logger.error(f"测试执行异常: {e}")
            return TestResult(
                success=False, total_tests=0, passed=0,
                failed=0, errors=1, logs=str(e),
                failed_tests=[], method="local_sandbox",
                language=self._detected_config.language if self._detected_config else "python",
                framework=self._detected_config.framework if self._detected_config else "pytest",
            )

    # ==================== 环境隔离 ====================

    def _build_sandbox_env(self) -> Dict[str, str]:
        env = {}

        for key in ENV_WHITELIST:
            if key in os.environ:
                env[key] = os.environ[key]

        if self._venv_dir:
            venv_bin = str(self._venv_dir / "bin")
            existing_path = env.get('PATH', os.environ.get('PATH', '/usr/bin:/bin'))
            env['PATH'] = f"{venv_bin}:{existing_path}"
            env['PYTHONPATH'] = str(self._work_dir)
            env['PYTHONSAFEPATH'] = '1'
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env['VIRTUAL_ENV'] = str(self._venv_dir)
            env['DATABASE_URL'] = f'sqlite+aiosqlite:///{self._work_dir / "test_sandbox.db"}'
        else:
            existing_path = env.get('PATH', os.environ.get('PATH', '/usr/bin:/bin'))
            env['PATH'] = existing_path

        env['ENV'] = 'test'
        env['TESTING'] = '1'

        # 注入服务容器环境变量
        env.update(self._service_env_vars)

        return env

    # ==================== 安全扫描 ====================

    def _scan_security(self) -> List[str]:
        warnings = []
        py_files = list(self.project_path.rglob("*.py"))
        scan_limit = min(len(py_files), 100)

        for py_file in py_files[:scan_limit]:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                lines = content.splitlines()
                for line_num, line in enumerate(lines, 1):
                    if line.strip().startswith('#'):
                        continue
                    for pattern in FORBIDDEN_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            rel = py_file.relative_to(self.project_path)
                            warnings.append(
                                f"{rel}:{line_num} - {line.strip()[:120]}"
                            )
            except Exception as e:
                logger.debug(f"扫描文件失败 {py_file}：{e}")
                continue

        if warnings:
            logger.warning(f"安全扫描: {len(warnings)} 个警告")
        else:
            logger.info("安全扫描通过")

        return warnings

    # ==================== OutputParser 集成 ====================

    def _parse_with_output_parser(self, result: TestResult) -> TestResult:
        output_format = "pytest_xml"
        if self._detected_config:
            output_format = self._detected_config.output_format

        parsed = OutputParser.parse(result.logs, output_format)

        result.passed = parsed.passed
        result.failed = parsed.failed
        result.total_tests = parsed.passed + parsed.failed

        if parsed.errors:
            result.errors = len(parsed.errors)
            result.failed_tests = [e[:100] for e in parsed.errors[:20]]

        if result.total_tests == 0 and result.passed == 0 and result.failed == 0:
            passed = failed = errors_count = 0

            m_pass = re.search(r'(\d+)\s+passed', result.logs)
            if m_pass:
                passed = int(m_pass.group(1))
            m_fail = re.search(r'(\d+)\s+failed', result.logs)
            if m_fail:
                failed = int(m_fail.group(1))
            m_err = re.search(r'(\d+)\s+error', result.logs)
            if m_err:
                errors_count = int(m_err.group(1))

            result.passed = passed
            result.failed = failed
            result.errors = errors_count
            result.total_tests = passed + failed + errors_count
            result.failed_tests = re.findall(r'FAILED\s+(\S+)', result.logs)

        return result

    # ==================== 资源释放 ====================

    async def _cleanup(self):
        if self._temp_dir and self._temp_dir.exists():
            try:
                await asyncio.sleep(0.5)
                shutil.rmtree(str(self._temp_dir), ignore_errors=True)
                logger.info(f"临时资源已释放: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"临时目录清理失败: {e}")

            self._temp_dir = None
            self._venv_dir = None
            self._work_dir = None
            self._venv_python = None

        if self.project_path.exists():
            for pycache in self.project_path.rglob("__pycache__"):
                try:
                    shutil.rmtree(str(pycache), ignore_errors=True)
                except Exception as e:
                    logger.debug(f"清理 pycache 失败 {pycache}：{e}")


class TestRunner(IsolatedTestRunner):
    def __init__(
        self,
        project_path: Path,
        timeout: int = 120,
    ):
        super().__init__(
            project_path=project_path,
            timeout=timeout,
            enable_security_scan=True,
        )
