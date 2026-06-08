"""
IntegrityValidator - 完整性验证器

核心理念：在所有文件生成后，检查跨文件引用一致性。
确保所有被引用的模块都存在，所有导入路径都正确。

工作流程：
1. 提取每个文件的导入语句
2. 验证导入的模块是否在生成的文件中
3. 检查包的入口文件是否存在（支持多语言）
4. 验证前端与后端的 API 契约一致性
"""

import re
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IntegrityIssue:
    """完整性问题"""
    file_path: str
    issue_type: str  # missing_module, missing_init, import_error, api_mismatch
    message: str
    severity: str = "error"  # error, warning
    suggestion: Optional[str] = None


@dataclass
class IntegrityResult:
    """完整性验证结果"""
    passed: bool = True
    issues: List[IntegrityIssue] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    fixed_files: List[str] = field(default_factory=list)

    def add_issue(self, issue: IntegrityIssue):
        self.issues.append(issue)
        if issue.severity == "error":
            self.passed = False

    @property
    def error_count(self) -> int:
        return len([i for i in self.issues if i.severity == "error"])

    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.severity == "warning"])


class IntegrityValidator:
    """
    完整性验证器 - 检查跨文件引用一致性

    验证内容：
    1. 导入验证：所有导入的模块都存在
    2. 包完整性：包有入口文件（Python: __init__.py, JS: index.js/ts）
    3. 导入路径：导入路径与实际文件路径匹配
    4. API 契约：前端请求与后端响应一致（可选）
    """

    # Python 内置模块（不需要项目内文件）
    PYTHON_BUILTINS = {
        'os', 'sys', 'json', 're', 'time', 'datetime', 'logging',
        'typing', 'pathlib', 'collections', 'asyncio', 'functools',
        'itertools', 'abc', 'copy', 'hashlib', 'hmac', 'secrets',
        'uuid', 'math', 'random', 'string', 'io', 'contextlib',
        'dataclasses', 'enum', 'struct', 'pickle', 'shelve', 'dbm',
        'sqlite3', 'csv', 'configparser', 'argparse', 'unittest',
        'threading', 'multiprocessing', 'subprocess', 'signal',
        'socket', 'ssl', 'http', 'urllib', 'email', 'html', 'xml',
        'base64', 'binascii', 'codecs', 'locale', 'gettext',
        'platform', 'ctypes', 'concurrent', 'queue', 'array',
        'weakref', 'types', 'operator', 'dis', 'ast', 'token',
        'keyword', 'tokenize', 'inspect', 'site', 'traceback',
        'linecache', 'warnings', 'importlib', 'pkgutil', 'modulefinder',
        'runpy', 'py_compile', 'compileall', 'zipfile', 'tarfile',
        'gzip', 'bz2', 'lzma', 'zlib', 'shutil', 'glob', 'fnmatch',
        'tempfile', 'filecmp', 'stat', 'fileinput', 'calendar',
        'pprint', 'textwrap', 'difflib', 'unicodedata', 'stringprep',
        'readline', 'rlcompleter', 'struct', 'codecs',
    }

    # 常见第三方库（不需要项目内文件）
    COMMON_THIRD_PARTY = {
        'fastapi', 'flask', 'django', 'sqlalchemy', 'pydantic',
        'uvicorn', 'gunicorn', 'requests', 'httpx', 'aiohttp',
        'numpy', 'pandas', 'scipy', 'matplotlib', 'sklearn',
        'torch', 'tensorflow', 'pytest', 'unittest', 'celery',
        'redis', 'pymongo', 'psycopg2', 'mysql', 'sqlite3',
        'jwt', 'jose', 'passlib', 'bcrypt', 'cryptography',
        'multipart', 'starlette', 'httpx', 'orjson', 'ujson',
        'alembic', 'tortoise', 'peewee', 'sqlmodel',
    }

    def __init__(self, project_type: str = "python", language_adapter=None):
        self.project_type = project_type
        self.language_adapter = language_adapter

    def validate(self, generated_files: Dict[str, str]) -> IntegrityResult:
        """
        验证生成文件的完整性

        Args:
            generated_files: {文件路径: 文件内容}

        Returns:
            IntegrityResult 验证结果
        """
        result = IntegrityResult()

        # 1. 检查包的入口文件
        self._check_package_init(generated_files, result)

        # 2. 提取并验证所有导入
        self._validate_imports(generated_files, result)

        # 3. 检查前端与后端 API 契约（如果有前端文件）
        frontend_extensions = {'.html', '.js', '.vue', '.jsx', '.tsx', '.ts', '.svelte', '.css'}
        backend_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        has_frontend = any(Path(f).suffix in frontend_extensions for f in generated_files)
        has_backend = any(Path(f).suffix in backend_extensions for f in generated_files)
        if has_frontend and has_backend:
            self._validate_api_contracts(generated_files, result)

        return result

    def _check_package_init(self, files: Dict[str, str], result: IntegrityResult):
        """检查包的入口文件是否存在（支持多语言）"""
        packages = set()

        # 自动检测语言适配器（如果未提供）
        adapter = self.language_adapter
        if not adapter:
            from app.agent.adapters.language_adapter import LanguageAdapterRegistry
            # 从文件扩展名推断语言
            extensions = {Path(f).suffix for f in files}
            if extensions & {'.js', '.jsx', '.ts', '.tsx'}:
                adapter = LanguageAdapterRegistry.get_adapter('javascript')
            elif extensions & {'.go'}:
                adapter = LanguageAdapterRegistry.get_adapter('go')
            elif extensions & {'.java'}:
                adapter = LanguageAdapterRegistry.get_adapter('java')
            if adapter:
                self.language_adapter = adapter

        # 提取所有包路径
        for file_path in files:
            if '/' in file_path:
                parts = Path(file_path).parts
                # 检查每一级目录是否是包
                for i in range(1, len(parts)):
                    pkg_path = '/'.join(parts[:i])
                    if pkg_path and pkg_path not in packages:
                        packages.add(pkg_path)

        # 检查每个包是否有入口文件
        for pkg in packages:
            if adapter:
                missing = adapter.validate_package_structure(pkg, files)
                for init_path in missing:
                    if init_path not in files:
                        result.add_issue(IntegrityIssue(
                            file_path=pkg,
                            issue_type="missing_init",
                            message=f"包缺少入口文件: {pkg}",
                            severity="error",
                            suggestion=f"创建 {init_path}"
                        ))
                        result.missing_files.append(init_path)
            else:
                # Fallback: 使用通用包结构检查
                init_file = "index.js"  # 通用默认值
                init_path = f"{pkg}/{init_file}"
                if init_path not in files:
                    result.add_issue(IntegrityIssue(
                        file_path=pkg,
                        issue_type="missing_init",
                        message=f"包缺少入口文件: {pkg}",
                        severity="error",
                        suggestion=f"创建 {init_path}"
                    ))
                    result.missing_files.append(init_path)

    def _validate_imports(self, files: Dict[str, str], result: IntegrityResult):
        """验证所有导入语句"""
        for file_path, content in files.items():
            # 使用语言适配器
            if self.language_adapter:
                imports = self.language_adapter.parse_imports(content, file_path)

                for imp in imports:
                    # 跳过相对导入和第三方库
                    if imp.is_relative or not self.language_adapter.is_project_module(imp.module):
                        continue

                    # 检查导入的模块是否存在
                    candidates = self.language_adapter.resolve_import_to_file(imp, file_path)
                    exists = any(c in files for c in candidates)

                    if not exists:
                        result.add_issue(IntegrityIssue(
                            file_path=file_path,
                            issue_type="missing_module",
                            message=f"导入的模块不存在: {imp.module}",
                            severity="error",
                            suggestion=f"确保 {imp.module} 在 file_plan 中有对应文件"
                        ))
            else:
                # Fallback: 通用导入检查
                extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
                file_ext = Path(file_path).suffix
                if file_ext not in extensions:
                    continue

                imports = self._extract_imports(content)

                for imp in imports:
                    # 跳过内置模块和第三方库
                    if self._is_builtin_or_third_party(imp):
                        continue

                    # 检查导入的模块是否存在
                    if not self._module_exists(imp, files):
                        result.add_issue(IntegrityIssue(
                            file_path=file_path,
                            issue_type="missing_module",
                            message=f"导入的模块不存在: {imp}",
                            severity="error",
                            suggestion=f"确保 {imp} 在 file_plan 中有对应文件"
                        ))

    def _extract_imports(self, content: str) -> List[str]:
        """提取 Python 文件中的所有导入"""
        imports = []

        # 匹配 import xxx 和 from xxx import yyy
        import_patterns = [
            r'^import\s+([\w.]+)',  # import xxx
            r'^from\s+([\w.]+)\s+import',  # from xxx import yyy
        ]

        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                continue

            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module = match.group(1)
                    # 只处理 app. 开头的项目内模块
                    if module.startswith('app') or module.startswith('src'):
                        imports.append(module)

        return imports

    def _is_builtin_or_third_party(self, module: str) -> bool:
        """判断是否是内置模块或第三方库"""
        # 获取顶级模块名
        top_level = module.split('.')[0]

        if top_level in self.PYTHON_BUILTINS:
            return True
        if top_level in self.COMMON_THIRD_PARTY:
            return True
        # 相对导入
        if module.startswith('.'):
            return True

        return False

    def _module_exists(self, module: str, files: Dict[str, str]) -> bool:
        """检查模块是否在生成的文件中存在"""
        # 使用语言适配器
        if self.language_adapter:
            from app.agent.adapters.language_adapter import ImportInfo
            imp = ImportInfo(module=module, is_relative=False)
            candidates = self.language_adapter.resolve_import_to_file(imp, "")
            return any(c in files for c in candidates)

        # Fallback: 通用检查
        extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        pkg_path = module.replace('.', '/')

        # 检查各种可能的文件路径
        for ext in extensions:
            file_path = f"{pkg_path}{ext}"
            if file_path in files:
                return True

        # 检查是否是包（入口文件）
        if self.language_adapter:
            init_file = self.language_adapter.get_package_init_file(pkg_path)
            if init_file in files:
                return True

        # 检查是否是包内的模块
        for f in files:
            if f.startswith(pkg_path + '/'):
                return True

        return False

    def _validate_api_contracts(self, files: Dict[str, str], result: IntegrityResult):
        """验证前端与后端的 API 契约一致性"""
        # 提取后端 API 端点和响应模型
        backend_apis = self._extract_backend_apis(files)
        # 提取前端 API 调用
        frontend_calls = self._extract_frontend_api_calls(files)

        # 检查前端调用的 API 是否存在
        for call in frontend_calls:
            endpoint = call['endpoint']
            file_path = call['file']

            # 检查端点是否存在
            if not self._api_endpoint_exists(endpoint, backend_apis):
                result.add_issue(IntegrityIssue(
                    file_path=file_path,
                    issue_type="api_mismatch",
                    message=f"前端调用的 API 端点可能不存在: {endpoint}",
                    severity="warning",
                    suggestion=f"确保后端有对应的路由处理 {endpoint}"
                ))

    def _extract_backend_apis(self, files: Dict[str, str]) -> List[Dict]:
        """提取后端 API 端点"""
        apis = []
        backend_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}

        for file_path, content in files.items():
            if Path(file_path).suffix not in backend_extensions:
                continue

            # 匹配 FastAPI/Flask 路由装饰器
            # @app.get("/xxx") 或 @router.get("/xxx")
            pattern = r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
            for match in re.finditer(pattern, content):
                method = match.group(1).upper()
                path = match.group(2)
                apis.append({
                    'method': method,
                    'path': path,
                    'file': file_path
                })

        return apis

    def _extract_frontend_api_calls(self, files: Dict[str, str]) -> List[Dict]:
        """提取前端 API 调用"""
        calls = []

        for file_path, content in files.items():
            if not file_path.endswith(('.js', '.ts', '.vue', '.jsx', '.tsx')):
                continue

            # 匹配 fetch/axios 调用
            # fetch("/api/xxx") 或 axios.get("/api/xxx")
            patterns = [
                r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']',
                r'axios\.\w+\s*\(\s*[`"\']([^`"\']+)[`"\']',
                r'\.get\s*\(\s*[`"\']([^`"\']+)[`"\']',
                r'\.post\s*\(\s*[`"\']([^`"\']+)[`"\']',
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    endpoint = match.group(1)
                    # 跳过模板字符串中的变量
                    if '${' in endpoint:
                        continue
                    calls.append({
                        'endpoint': endpoint,
                        'file': file_path
                    })

        return calls

    def _api_endpoint_exists(self, endpoint: str, apis: List[Dict]) -> bool:
        """检查 API 端点是否存在"""
        # 简化检查：路径是否匹配
        for api in apis:
            api_path = api['path']
            # 处理路径参数：/todos/{id} -> /todos/xxx
            api_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', api_path)
            if re.match(f'^{api_pattern}$', endpoint):
                return True
            # 检查是否是前缀匹配
            if endpoint.startswith(api_path) or api_path.startswith(endpoint):
                return True
        return False

    def generate_fixes(self, result: IntegrityResult, generated_files: Dict[str, str]) -> Dict[str, str]:
        """
        根据验证结果生成修复文件

        Args:
            result: 验证结果
            generated_files: 已生成的文件

        Returns:
            需要新增/修改的文件 {文件路径: 文件内容}
        """
        fixes = {}

        # 生成缺失的包入口文件
        for missing in result.missing_files:
            if missing not in generated_files:
                # 确认是包入口文件（通过检查父目录是否存在）
                parent = str(Path(missing).parent)
                if parent in [str(Path(m).parent) for m in result.missing_files if m != missing]:
                    continue  # 跳过，父目录也是缺失的
                # 生成入口文件内容
                init_filename = self.language_adapter.package_init_filename if self.language_adapter else '__init__.py'
                if init_filename and missing.endswith(init_filename):
                    fixes[missing] = '"""Package initialization"""\n'
                elif missing.endswith('index.js') or missing.endswith('index.ts'):
                    fixes[missing] = '// Package initialization\n'
                else:
                    fixes[missing] = ''
                result.fixed_files.append(missing)
                logger.info(f"自动生成修复文件: {missing}")

        return fixes
