"""
PythonLanguageAdapter - Python 语言适配器

处理 Python 特有的：
- 导入语法 (import xxx, from xxx import yyy)
- 包结构 (__init__.py)
- 文件类型推断
- 符号定义提取
"""

import re
from typing import Dict, List
from pathlib import Path

from .language_adapter import (
    LanguageAdapter, LanguageAdapterRegistry,
    ImportInfo, SymbolDefinition
)


class PythonLanguageAdapter(LanguageAdapter):
    """Python 语言适配器"""

    language = "python"
    extensions = [".py", ".pyw", ".pyi"]
    package_init_filename = "__init__.py"

    # Python 标准库常见模块
    PYTHON_BUILTINS = {
        'os', 'sys', 'pathlib', 'typing', 're', 'json', 'logging', 'datetime',
        'collections', 'functools', 'itertools', 'abc', 'dataclasses', 'enum',
        'io', 'copy', 'hashlib', 'hmac', 'secrets', 'uuid', 'time', 'random',
        'math', 'decimal', 'fractions', 'statistics', 'string', 'textwrap',
        'unicodedata', 'struct', 'codecs', 'contextlib', 'weakref', 'types',
        'inspect', 'importlib', 'pkgutil', 'traceback', 'linecache', 'pickle',
        'shelve', 'sqlite3', 'xml', 'html', 'csv', 'configparser', 'argparse',
        'getopt', 'cmd', 'shlex', 'shutil', 'glob', 'fnmatch', 'tempfile',
        'gzip', 'bz2', 'lzma', 'zipfile', 'tarfile', 'signal', 'mmap',
        'threading', 'multiprocessing', 'concurrent', 'asyncio', 'socket',
        'ssl', 'select', 'selectors', 'http', 'ftplib', 'smtplib', 'email',
        'urllib', 'webbrowser', 'wsgiref', 'array', 'queue', 'heapq', 'bisect',
        'graphlib', 'unittest', 'doctest', 'pdb', 'profile', 'timeit',
        'venv', 'sysconfig', 'builtins', 'operator', 'platform',
        'ctypes', 'struct', 'errno',
    }

    # 常见第三方库
    COMMON_THIRD_PARTY = {
        'fastapi', 'flask', 'django', 'requests', 'httpx', 'aiohttp',
        'sqlalchemy', 'pydantic', 'numpy', 'pandas', 'torch', 'tensorflow',
        'scipy', 'matplotlib', 'seaborn', 'plotly', 'sklearn', 'cv2',
        'PIL', 'Pillow', 'boto3', 'google', 'azure', 'redis', 'celery',
        'pytest', 'mock', 'click', 'typer', 'rich', 'tqdm',
        'uvicorn', 'gunicorn', 'nginx', 'jinja2', 'mako', 'alembic',
        'pymongo', 'psycopg2', 'mysql', 'elasticsearch', 'kafka',
        'websockets', 'socketio', 'grpc', 'protobuf', 'msgpack',
        'cryptography', 'jwt', 'oauthlib', 'passlib', 'bcrypt',
        'pillow', 'openai', 'anthropic', 'langchain', 'llama_index',
        'transformers', 'huggingface_hub', 'diffusers', 'safetensors',
        'beautifulsoup4', 'scrapy', 'selenium', 'playwright',
    }

    # 文件路径到类型的映射规则
    PATH_TYPE_RULES = [
        # 配置
        ("requirements.txt", "config"),
        (".env", "env"),
        (".env.example", "env"),
        (".env.local", "env"),
        ("Dockerfile", "dockerfile"),
        ("docker-compose.yml", "docker_compose"),
        ("docker-compose.yaml", "docker_compose"),
        ("pyproject.toml", "config"),
        ("setup.py", "config"),
        ("Makefile", "config"),

        # 服务连接配置
        ("redis_config.py", "service_config"),
        ("redis_connection.py", "service_config"),
        ("database_config.py", "service_config"),
        ("db_connection.py", "service_config"),
        ("mongodb_config.py", "service_config"),
        ("connections.py", "service_config"),

        # Python 配置
        ("config.py", "config"),
        ("settings.py", "config"),
        ("config/", "config"),
        ("settings/", "config"),

        # 数据库
        ("database.py", "database"),
        ("database/", "database"),
        ("db.py", "database"),

        # 模型
        ("models.py", "model"),
        ("models/", "model"),
        ("model/", "model"),
        ("entities/", "model"),
        ("entity/", "model"),

        # Repository
        ("crud.py", "repository"),
        ("crud/", "repository"),
        ("repositories/", "repository"),
        ("repository/", "repository"),
        ("repos/", "repository"),
        ("dao/", "repository"),

        # 类型/Schema
        ("types.py", "types"),
        ("types/", "types"),
        ("schemas.py", "schema"),
        ("schemas/", "schema"),
        ("dto/", "schema"),

        # 工具
        ("utils/", "utils"),
        ("utils.py", "utils"),
        ("helpers/", "utils"),
        ("helpers.py", "utils"),
        ("constants.py", "constants"),
        ("constants/", "constants"),

        # API/Routes
        ("routes/", "api"),
        ("api/", "api"),
        ("endpoints/", "api"),
        ("views/", "api"),
        ("controllers/", "api"),
        ("handlers/", "api"),

        # Service
        ("services/", "service"),
        ("service/", "service"),

        # 测试
        ("tests/", "test"),
        ("test/", "test"),
        ("test_", "test"),
        ("_test.py", "test"),

        # 前端
        ("templates/", "template"),
        ("static/", "frontend_static"),
        ("frontend/", "frontend"),
        ("web/", "frontend"),

        # 文档
        ("README.md", "readme"),
        ("docs/", "docs"),
    ]

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        """解析 Python 导入语句"""
        imports = []

        if not content:
            return imports

        for line in content.split('\n'):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('#'):
                continue

            # from xxx import yyy
            match = re.match(r'^from\s+([\w.]*)\s+import\s+(.+)', stripped)
            if match:
                module = match.group(1)
                symbols_str = match.group(2)
                is_relative = module.startswith('.') or module == ''

                # 解析导入的符号
                symbols = self._parse_import_symbols(symbols_str)

                # 处理相对导入
                if is_relative:
                    module = module.lstrip('.')

                imports.append(ImportInfo(
                    module=module,
                    symbols=symbols,
                    is_relative=is_relative,
                    raw_line=stripped
                ))
                continue

            # import xxx
            match = re.match(r'^import\s+([\w.]+)(?:\s+as\s+(\w+))?', stripped)
            if match:
                module = match.group(1)
                alias = match.group(2)

                imports.append(ImportInfo(
                    module=module,
                    symbols=[],
                    is_relative=False,
                    alias=alias,
                    raw_line=stripped
                ))
                continue

        return imports

    def _parse_import_symbols(self, symbols_str: str) -> List[str]:
        """解析 from xxx import 中的符号列表"""
        symbols = []

        # 处理括号包裹的情况: from xxx import (a, b, c)
        symbols_str = symbols_str.strip('()')

        for part in symbols_str.split(','):
            part = part.strip()
            if not part:
                continue

            # 处理 from xxx import yyy as zzz
            if ' as ' in part:
                symbol = part.split(' as ')[-1].strip()
            elif part == '*':
                symbol = '*'
            else:
                symbol = part.strip()

            if symbol:
                symbols.append(symbol)

        return symbols

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        """将导入路径解析为文件路径"""
        candidates = []
        module = import_info.module

        if not module:
            return candidates

        # 相对导入处理
        if import_info.is_relative:
            current_dir = str(Path(current_file).parent)
            base_path = current_dir if current_dir != '.' else ''
            if base_path:
                candidates.append(f"{base_path}/{module.replace('.', '/')}.py")
                candidates.append(f"{base_path}/{module.replace('.', '/')}/__init__.py")
            return candidates

        # 绝对导入
        # app.models -> app/models.py
        file_path = module.replace('.', '/') + '.py'
        candidates.append(file_path)

        # app.models -> app/models/__init__.py (包)
        init_path = module.replace('.', '/') + '/__init__.py'
        candidates.append(init_path)

        return candidates

    def infer_file_type(self, file_path: str) -> str:
        """根据文件路径推断文件类型"""
        # __init__.py 是包配置文件
        if file_path.endswith('__init__.py'):
            return "config"

        # 检查路径规则
        for pattern, file_type in self.PATH_TYPE_RULES:
            if pattern.endswith('/'):
                # 目录匹配
                if f"/{pattern}" in f"{file_path}/" or file_path.startswith(pattern):
                    return file_type
            else:
                # 文件名匹配
                if file_path.endswith(pattern) or f"/{pattern}" in file_path:
                    return file_type

        # 基于目录名的推断
        parts = Path(file_path).parts
        for part in parts:
            part_lower = part.lower()
            if part_lower in ('models', 'model', 'entities', 'entity'):
                return "model"
            elif part_lower in ('api', 'routes', 'routers', 'endpoints', 'views', 'controllers', 'handlers'):
                return "api"
            elif part_lower in ('services', 'service'):
                return "service"
            elif part_lower in ('repositories', 'repository', 'repos', 'dao'):
                return "repository"
            elif part_lower in ('utils', 'helpers', 'common'):
                return "utils"
            elif part_lower in ('tests', 'test'):
                return "test"
            elif part_lower in ('config', 'settings', 'conf'):
                return "config"
            elif part_lower in ('pydantic', 'schemas', 'dto'):
                return "types"

        return "unknown"

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        """提取 Python 文件中的符号定义"""
        definitions = {}
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('#'):
                continue

            # 函数定义
            func_match = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)', stripped)
            if func_match:
                func_name = func_match.group(1)
                signature = func_match.group(2)
                definitions[func_name] = SymbolDefinition(
                    name=func_name,
                    symbol_type="function",
                    line_number=i,
                    signature=signature,
                    is_exported=not func_name.startswith('_')
                )
                continue

            # 类定义
            class_match = re.match(r'^class\s+(\w+)(?:\s*\([^)]*\))?\s*:', stripped)
            if class_match:
                class_name = class_match.group(1)
                definitions[class_name] = SymbolDefinition(
                    name=class_name,
                    symbol_type="class",
                    line_number=i,
                    is_exported=not class_name.startswith('_')
                )
                continue

            # 变量定义（模块级别）
            if not line.startswith(' ') and not line.startswith('\t'):
                var_match = re.match(r'^(\w+)\s*=', stripped)
                if var_match:
                    var_name = var_match.group(1)
                    # 跳过导入的模块名
                    if var_name not in ('import', 'from'):
                        symbol_type = "constant" if var_name.isupper() else "variable"
                        definitions[var_name] = SymbolDefinition(
                            name=var_name,
                            symbol_type=symbol_type,
                            line_number=i,
                            is_exported=not var_name.startswith('_')
                        )

        return definitions

    def get_package_init_file(self, package_path: str) -> str:
        """获取 Python 包的入口文件"""
        return f"{package_path}/__init__.py"

    def is_project_module(self, module_name: str) -> bool:
        """判断是否是项目内模块"""
        if not module_name:
            return False

        top_level = module_name.split('.')[0]

        # 标准库
        if top_level in self.PYTHON_BUILTINS:
            return False

        # 第三方库
        if top_level in self.COMMON_THIRD_PARTY:
            return False

        # 相对导入
        if module_name.startswith('.'):
            return True

        # 常见项目模块前缀
        project_prefixes = ['app', 'src', 'lib', 'pkg', 'internal', 'core']
        if top_level in project_prefixes:
            return True

        return False

    def validate_package_structure(self, package_path: str, files: Dict[str, str]) -> List[str]:
        """验证 Python 包结构"""
        missing = []
        init_path = self.get_package_init_file(package_path)

        if init_path not in files:
            missing.append(init_path)

        return missing

    def get_required_package_files(self, package_path: str) -> List[str]:
        """获取 Python 包所需的文件"""
        return [self.get_package_init_file(package_path)]


# 注册适配器
LanguageAdapterRegistry.register(PythonLanguageAdapter())
