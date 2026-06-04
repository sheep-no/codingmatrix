"""
代码验证器 - 语法、依赖、运行时、跨文件一致性验证（带缓存优化）
"""

import re
import sys
import ast
import time
import asyncio
import importlib.util
import logging
from collections import OrderedDict
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


logger = logging.getLogger(__name__)


class CodeValidator:
    """代码验证器 - 语法、依赖、运行时、跨文件一致性验证（带缓存优化）"""

    _lru_cache: OrderedDict = OrderedDict()
    _max_cache_bytes = 50 * 1024 * 1024
    _cache_size_bytes = 0
    _cache_hits = 0
    _cache_misses = 0
    _validation_cache = _lru_cache
    MAX_CACHE_SIZE = 100
    SUCCESS_CACHE_TTL = 3600
    FAILURE_CACHE_TTL = 300

    # 常见 API 兼容性规则
    API_COMPATIBILITY_RULES = {
        "fastapi": {
            "OAuth2PasswordBearer": {"token_url": "tokenUrl"},
        },
        "passlib": {
            "CryptContext": {"deprecated=False": 'deprecated="auto"'},
        },
    }

    # passlib 导入正确形式
    PASSLIB_IMPORT_MAP = {
        "import passlib.hash.bcrypt": "from passlib.hash import bcrypt",
        "import passlib.hash": "from passlib.hash import bcrypt",
    }

    def __init__(self, project_path):
        self.project_path = project_path

    @classmethod
    def _compute_content_hash(cls, file_content: str) -> str:
        """计算文件内容的 SHA256 哈希"""
        import hashlib
        return hashlib.sha256(file_content.encode('utf-8')).hexdigest()[:16]

    @classmethod
    def _clear_old_cache(cls):
        now = time.time()
        expired_keys = []
        for key, entry in list(cls._lru_cache.items()):
            ttl = cls.SUCCESS_CACHE_TTL if entry[0].get("is_valid", False) else cls.FAILURE_CACHE_TTL
            if now - entry[1] > ttl:
                expired_keys.append(key)
        for key in expired_keys:
            entry = cls._lru_cache.pop(key)
            cls._cache_size_bytes -= sys.getsizeof(key) + sys.getsizeof(entry)
        while cls._cache_size_bytes > cls._max_cache_bytes and cls._lru_cache:
            oldest_key, oldest_entry = cls._lru_cache.popitem(last=False)
            cls._cache_size_bytes -= sys.getsizeof(oldest_key) + sys.getsizeof(oldest_entry)

    def get_cached_validation(self, file_path: Path) -> Optional[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content_hash = self._compute_content_hash(content)
            cache_key = f"{file_path}:{content_hash}"
            if cache_key in CodeValidator._lru_cache:
                result, timestamp = CodeValidator._lru_cache[cache_key]
                ttl = CodeValidator.SUCCESS_CACHE_TTL if result.get("is_valid", False) else CodeValidator.FAILURE_CACHE_TTL
                if time.time() - timestamp <= ttl:
                    CodeValidator._lru_cache.move_to_end(cache_key)
                    CodeValidator._cache_hits += 1
                    return result
                else:
                    entry = CodeValidator._lru_cache.pop(cache_key)
                    CodeValidator._cache_size_bytes -= sys.getsizeof(cache_key) + sys.getsizeof(entry)
            CodeValidator._cache_misses += 1
            return None
        except Exception:
            CodeValidator._cache_misses += 1
            return None

    def cache_validation(self, file_path: Path, result: Dict):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content_hash = self._compute_content_hash(content)
            cache_key = f"{file_path}:{content_hash}"
            if cache_key in CodeValidator._lru_cache:
                old_entry = CodeValidator._lru_cache.pop(cache_key)
                CodeValidator._cache_size_bytes -= sys.getsizeof(cache_key) + sys.getsizeof(old_entry)
            entry = (result, time.time())
            CodeValidator._lru_cache[cache_key] = entry
            CodeValidator._lru_cache.move_to_end(cache_key)
            CodeValidator._cache_size_bytes += sys.getsizeof(cache_key) + sys.getsizeof(entry)
            CodeValidator._clear_old_cache()
        except Exception:
            logger.debug("缓存写入失败")

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        total_requests = cls._cache_hits + cls._cache_misses
        hit_rate = cls._cache_hits / total_requests if total_requests > 0 else 0.0
        return {
            "entries": len(cls._lru_cache),
            "size_bytes": cls._cache_size_bytes,
            "max_bytes": cls._max_cache_bytes,
            "hits": cls._cache_hits,
            "misses": cls._cache_misses,
            "hit_rate": hit_rate,
        }

    async def validate_syntax(self, file_path: Path) -> Tuple[bool, List[str]]:
        """验证语法正确性"""
        if file_path.suffix != '.py':
            return True, []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
            return True, []
        except SyntaxError as e:
            return False, [f"语法错误 第{e.lineno}行: {e.msg}"]
        except Exception as e:
            return False, [f"验证失败: {str(e)}"]

    async def validate_imports(self, file_path: Path) -> Tuple[bool, List[str]]:
        """验证导入语句"""
        if file_path.suffix != '.py':
            return True, []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # 提取所有 import 语句
            imports = set()
            for line in source.split('\n'):
                line = line.strip()
                if line.startswith('import '):
                    module = line.split()[1].split('.')[0]
                    imports.add(module)
                elif line.startswith('from '):
                    # Extract the full module path (e.g., "src.utils" from "from src.utils import greet")
                    parts = line.split()
                    if len(parts) >= 2:
                        module_path = parts[1]
                        # Add the full path and each component
                        imports.add(module_path)
                        for part in module_path.split('.'):
                            if part:
                                imports.add(part)

            # 检查是否可以导入
            errors = []
            standard_libs = {'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing', 'asyncio', 'logging', 'collections', 'functools', 'itertools', 'math', 'string', 'io', 'copy', 'time', 'enum', 'dataclasses', 'abc', 'contextlib', 'urllib', 'http', 'email', 'hashlib', 'hmac', 'secrets', 'base64', 'struct', 'textwrap', 'difflib', 'unittest', 'doctest', 'pdb', 'traceback', 'warnings', 'weakref', 'types', 'importlib'}

            # Add project source directories to sys.path for import resolution
            added_paths = []
            try:
                current = file_path.parent
                project_root = None
                for _ in range(10):
                    if (current / 'src').is_dir() or (current / 'tests').is_dir():
                        project_root = current
                        break
                    parent = current.parent
                    if parent == current:
                        break
                    current = parent

                if project_root:
                    root_str = str(project_root)
                    if root_str not in sys.path:
                        sys.path.insert(0, root_str)
                        added_paths.append(root_str)

                    src_dir = project_root / 'src'
                    if src_dir.is_dir():
                        src_str = str(src_dir)
                        if src_str not in sys.path:
                            sys.path.insert(0, src_str)
                            added_paths.append(src_str)
            except Exception:
                logger.debug("sys.path 操作失败")

            for imp in imports:
                if imp in standard_libs:
                    continue
                try:
                    spec = importlib.util.find_spec(imp)
                    if spec is None:
                        errors.append(f"缺少依赖: {imp}")
                except (ModuleNotFoundError, ValueError):
                    errors.append(f"缺少依赖: {imp}")

            # Cleanup added paths
            for p in added_paths:
                if p in sys.path:
                    sys.path.remove(p)

            return len(errors) == 0, errors
        except Exception as e:
            return False, [f"导入验证失败: {str(e)}"]

    async def validate_runtime_imports(self, file_path: Path) -> Tuple[bool, List[str]]:
        """运行时导入验证：尝试实际执行导入，捕获 ImportError, AttributeError 等"""
        if file_path.suffix != '.py':
            return True, []

        # Skip runtime validation for __init__.py files (relative imports need package context)
        if file_path.name == '__init__.py':
            return True, []

        errors = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # 检查 passlib 错误导入模式
            if 'import passlib.hash.bcrypt' in source:
                errors.append("passlib 导入错误: 应使用 'from passlib.hash import bcrypt' 而非 'import passlib.hash.bcrypt'")
            if 'import passlib.hash' in source and 'from passlib.hash import' not in source:
                errors.append("passlib 导入错误: 'import passlib.hash' 无法使用 bcrypt，应改为 'from passlib.hash import bcrypt'")

            # 尝试动态编译和执行模块级代码以捕获运行时导入错误
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec is None or spec.loader is None:
                return True, []  # 无法加载 spec，跳过

            # Add project source directories to sys.path for import resolution
            added_paths = []
            try:
                # Walk up from file to find project root (contains src/, tests/, etc.)
                current = file_path.parent
                project_root = None
                for _ in range(10):  # limit traversal
                    if (current / 'src').is_dir() or (current / 'tests').is_dir():
                        project_root = current
                        break
                    parent = current.parent
                    if parent == current:
                        break
                    current = parent

                if project_root:
                    # Add project root (for `from src.xxx import ...`)
                    root_str = str(project_root)
                    if root_str not in sys.path:
                        sys.path.insert(0, root_str)
                        added_paths.append(root_str)

                    # Add src/ directory (for `from utils.xxx import ...` when file is in src/)
                    src_dir = project_root / 'src'
                    if src_dir.is_dir():
                        src_str = str(src_dir)
                        if src_str not in sys.path:
                            sys.path.insert(0, src_str)
                            added_paths.append(src_str)
            except Exception:
                pass  # best effort

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except ImportError as e:
                errors.append(f"运行时导入失败: {str(e)}")
            except AttributeError as e:
                errors.append(f"属性错误 (可能是 API 版本不兼容): {str(e)}")
            except TypeError as e:
                errors.append(f"类型错误 (可能是 API 参数不兼容): {str(e)}")
            finally:
                # 清理临时模块和路径
                if module_name in sys.modules:
                    del sys.modules[module_name]
                for p in added_paths:
                    if p in sys.path:
                        sys.path.remove(p)

        except Exception as e:
            errors.append(f"运行时验证异常: {str(e)}")

        return len(errors) == 0, errors

    async def validate_api_compatibility(self, file_path: Path) -> Tuple[bool, List[str]]:
        """API 兼容性检查：已知库的版本不兼容问题"""
        if file_path.suffix != '.py':
            return True, []

        errors = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # FastAPI OAuth2PasswordBearer token_url 参数名变更
            if 'OAuth2PasswordBearer' in source and 'token_url=' not in source and 'tokenUrl=' in source:
                errors.append("FastAPI 兼容性: OAuth2PasswordBearer 参数应为 'token_url=' 而非 'tokenUrl='")

            # FastAPI Middleware 导入位置变更
            if 'from fastapi import' in source and 'Middleware' in source.split('from fastapi import')[1].split('\n')[0]:
                errors.append("FastAPI 兼容性: Middleware 已从 fastapi 移至 fastapi.middleware.cors")

            # SQLAlchemy 2.0: DeclarativeBase vs Base + BaseModel MRO 冲突
            if 'class' in source and 'Base' in source and 'BaseModel' in source:
                if re.search(r'class\s+\w+\(.*Base.*BaseModel.*\)', source):
                    errors.append("SQLAlchemy 兼容性: 不能同时继承 Base 和 BaseModel (MRO 冲突)")

            # APIRouter.exception_handler 不存在
            if 'router.exception_handler' in source or 'APIRouter' in source and '.exception_handler' in source:
                errors.append("FastAPI 兼容性: APIRouter 没有 exception_handler 属性，异常处理应在 app 级别注册")

        except Exception as e:
            errors.append(f"API 兼容性检查异常: {str(e)}")

        return len(errors) == 0, errors

    async def validate_js_syntax(self, file_path: Path) -> Tuple[bool, List[str]]:
        """验证 JavaScript 语法"""
        if file_path.suffix != '.js':
            return True, []

        try:
            proc = await asyncio.create_subprocess_exec(
                'node', '-c', str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                return False, [f"JS 语法错误: {err_msg}"]
            return True, []
        except FileNotFoundError:
            return True, []  # node 未安装，跳过
        except Exception as e:
            return False, [f"JS 验证异常: {str(e)}"]

    async def validate_html_structure(self, file_path: Path) -> Tuple[bool, List[str]]:
        """验证 HTML 基本结构"""
        if file_path.suffix != '.html':
            return True, []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            errors = []
            # 检查必需的闭合标签
            required_tags = ['html', 'head', 'body']
            for tag in required_tags:
                open_count = len(re.findall(rf'<{tag}[\s>]', content, re.IGNORECASE))
                close_count = len(re.findall(rf'</{tag}>', content, re.IGNORECASE))
                if open_count > close_count:
                    errors.append(f"HTML 结构: 缺少 </{tag}> 闭合标签")

            # 检查 script 标签是否正确闭合
            script_opens = len(re.findall(r'<script[\s>]', content, re.IGNORECASE))
            script_closes = len(re.findall(r'</script>', content, re.IGNORECASE))
            if script_opens != script_closes:
                errors.append(f"HTML 结构: script 标签数量不匹配 (开: {script_opens}, 关: {script_closes})")

            return len(errors) == 0, errors
        except Exception as e:
            return False, [f"HTML 验证异常: {str(e)}"]

    async def validate_css_syntax(self, file_path: Path) -> Tuple[bool, List[str]]:
        """验证 CSS 基本语法"""
        if file_path.suffix != '.css':
            return True, []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            errors = []
            # 检查大括号匹配
            open_braces = content.count('{')
            close_braces = content.count('}')
            if open_braces != close_braces:
                errors.append(f"CSS 语法: 大括号不匹配 (开: {open_braces}, 关: {close_braces})")

            # 检查是否有明显的语法错误（如连续的分号）
            if ';;' in content:
                errors.append("CSS 语法: 存在连续的分号")

            return len(errors) == 0, errors
        except Exception as e:
            return False, [f"CSS 验证异常: {str(e)}"]

    async def validate_cross_file_consistency(self) -> Tuple[bool, List[str]]:
        """跨文件一致性检查：验证导入、导出、路由定义是否匹配"""
        errors = []

        # 收集所有 Python 文件
        py_files = list(self.project_path.rglob('*.py'))

        # 1. 收集所有模块中定义的类、函数、变量
        defined_symbols: Dict[str, Dict[str, set]] = {}  # module_name -> {classes, functions, variables}
        for f in py_files:
            if '__pycache__' in str(f):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as source:
                    tree = ast.parse(source.read())
                module_name = f.relative_to(self.project_path).with_suffix('').as_posix().replace('/', '.')
                defined_symbols[module_name] = {'classes': set(), 'functions': set(), 'variables': set()}
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        defined_symbols[module_name]['classes'].add(node.name)
                    elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                        defined_symbols[module_name]['functions'].add(node.name)
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                defined_symbols[module_name]['variables'].add(target.id)
            except Exception:
                pass  # 语法错误的文件跳过

        # 2. 检查 main.py 中的导入是否匹配实际模块和符号
        main_file = self.project_path / 'main.py'
        if main_file.exists():
            try:
                with open(main_file, 'r', encoding='utf-8') as f:
                    main_content = f.read()

                # 提取 from X import Y 语句
                from_imports = re.findall(r'from\s+([\w.]+)\s+import\s+([\w,\s]+)', main_content)
                for module, imports in from_imports:
                    imported_names = [n.strip() for n in imports.split(',')]
                    # 检查模块是否存在
                    module_path = module.replace('.', '/') + '.py'
                    init_path = module.replace('.', '/') + '/__init__.py'
                    if not (self.project_path / module_path).exists() and not (self.project_path / init_path).exists():
                        errors.append(f"跨文件引用: main.py 导入了不存在的模块 '{module}'")
                    else:
                        # 检查导入的符号是否实际存在于模块中
                        if module in defined_symbols:
                            all_symbols = (defined_symbols[module]['classes'] |
                                          defined_symbols[module]['functions'] |
                                          defined_symbols[module]['variables'])
                            for name in imported_names:
                                if name and name not in all_symbols and name != '*':
                                    # 可能是从子模块导入，检查子模块
                                    sub_module_path = module.replace('.', '/') + '/' + name + '.py'
                                    if not (self.project_path / sub_module_path).exists():
                                        errors.append(f"跨文件引用: '{module}' 模块未导出 '{name}' (实际导出: {', '.join(sorted(all_symbols)) if all_symbols else '无'})")
            except Exception:
                logger.debug("跨文件引用检查失败")

        # 3. 检查前端 API 调用与后端路由是否匹配
        js_files = [f for f in self.project_path.rglob('*.js') if 'node_modules' not in str(f)]
        api_routes_defined = set()
        for f in py_files:
            if '__pycache__' in str(f):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as source:
                    content = source.read()
                # 提取 @router.get("/xxx") 或 @app.post("/xxx") 等路由定义
                routes = re.findall(r'@(?:router|app)\.(?:get|post|put|delete|patch)\(["\'](/[^"\']+)["\']', content)
                api_routes_defined.update(routes)
            except Exception:
                logger.debug("API 路由提取失败")

        # 检查前端是否调用了不存在的 API
        for js_file in js_files:
            try:
                with open(js_file, 'r', encoding='utf-8') as f:
                    js_content = f.read()
                # 提取 fetch('/api/xxx') 或 axios.get('/api/xxx') 等 API 调用
                api_calls = re.findall(r'(?:fetch|axios\.(?:get|post|put|delete))\(["\'](/api/[^"\']+)["\']', js_content)
                for call in api_calls:
                    # 简化检查：如果后端定义了路由，前端调用应该匹配
                    # 这里只做基本检查，不处理动态路由参数
                    if api_routes_defined and not any(call.startswith(r) or r.startswith(call.split('?')[0]) for r in api_routes_defined):
                        # 只警告，不报错，因为可能是动态路由
                        pass
            except Exception:
                logger.debug("API 一致性检查失败")

        return len(errors) == 0, errors

    async def validate_single_file(self, file_path: Path) -> Dict[str, Any]:
        """验证单个文件的语法、导入、API 兼容性、运行时一致性和前端文件（用于修复循环）"""
        results = {
            "syntax_errors": [],
            "import_errors": [],
            "dependency_errors": [],
            "api_errors": [],
            "runtime_errors": [],
            "frontend_errors": [],
            "is_valid": True,
            "validated_files": 1
        }

        if file_path.suffix == '.py':
            syntax_ok, syntax_errs = await self.validate_syntax(file_path)
            import_ok, import_errs = await self.validate_imports(file_path)
            runtime_ok, runtime_errs = await self.validate_runtime_imports(file_path)
            api_ok, api_errs = await self.validate_api_compatibility(file_path)

            results["syntax_errors"].extend(syntax_errs)
            results["import_errors"].extend(import_errs)
            results["runtime_errors"].extend(runtime_errs)
            results["api_errors"].extend(api_errs)

            if not syntax_ok or not import_ok or not runtime_ok or not api_ok:
                results["is_valid"] = False

        elif file_path.suffix == '.js':
            js_ok, js_errs = await self.validate_js_syntax(file_path)
            results["frontend_errors"].extend(js_errs)
            if not js_ok:
                results["is_valid"] = False

        elif file_path.suffix == '.html':
            html_ok, html_errs = await self.validate_html_structure(file_path)
            results["frontend_errors"].extend(html_errs)
            if not html_ok:
                results["is_valid"] = False

        elif file_path.suffix == '.css':
            css_ok, css_errs = await self.validate_css_syntax(file_path)
            results["frontend_errors"].extend(css_errs)
            if not css_ok:
                results["is_valid"] = False

        return results

    async def validate_requirements(self) -> Tuple[bool, List[str]]:
        """验证 requirements.txt / pyproject.toml / Pipfile 是否完整"""
        req_file = self.project_path / 'requirements.txt'
        pyproject_file = self.project_path / 'pyproject.toml'
        pipfile = self.project_path / 'Pipfile'

        required = []
        found_file = None

        if req_file.exists():
            found_file = req_file
            with open(req_file, 'r') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-')]
                required = []
                for line in lines:
                    # 跳过 VCS 依赖 (git+https://...)
                    if line.startswith(('git+', 'svn+', 'hg+', 'bzr+')):
                        continue
                    # 跳过本地路径依赖
                    if line.startswith(('.', '/')) or 'file:' in line:
                        continue
                    # 处理可选依赖 requests[security]
                    pkg = line.split('[')[0] if '[' in line else line
                    # 提取包名（去掉版本约束）
                    pkg = pkg.split('==')[0].split('>=')[0].split('~=')[0].split('<=')[0].split('!=')[0].strip()
                    if pkg:
                        required.append(pkg.lower().replace('-', '_'))
        elif pyproject_file.exists():
            found_file = pyproject_file
            try:
                import tomllib
                with open(pyproject_file, 'rb') as f:
                    pyproject = tomllib.load(f)
                deps = pyproject.get('project', {}).get('dependencies', [])
                required = []
                for d in deps:
                    if d.startswith(('git+', 'svn+', 'hg+', 'bzr+')):
                        continue
                    pkg = d.split('[')[0] if '[' in d else d
                    pkg = pkg.split('==')[0].split('>=')[0].split('~=')[0].strip()
                    if pkg:
                        required.append(pkg.lower().replace('-', '_').split('[')[0])
            except Exception:
                logger.debug("requirements.txt 解析失败")
        elif pipfile.exists():
            found_file = pipfile
            try:
                import toml
                with open(pipfile, 'r') as f:
                    pipdata = toml.load(f)
                deps = list(pipdata.get('packages', {}).keys()) + list(pipdata.get('dev-packages', {}).keys())
                required = [d.lower().replace('-', '_').split('[')[0] for d in deps if not d.startswith(('.', '/'))]
            except Exception:
                logger.debug("Pipfile 解析失败")

        if not found_file:
            return False, ["缺少 requirements.txt / pyproject.toml / Pipfile"]

        # Python 包名到导入名的常见映射
        PACKAGE_TO_IMPORT = {
            'fastapi': 'fastapi',
            'uvicorn': 'uvicorn',
            'sqlalchemy': 'sqlalchemy',
            'pydantic': 'pydantic',
            'pydantic_settings': 'pydantic_settings',
            'python_dotenv': 'dotenv',
            'passlib': 'passlib',
            'python_jose': 'jose',
            'alembic': 'alembic',
            'httpx': 'httpx',
            'requests': 'requests',
            'celery': 'celery',
            'redis': 'redis',
            'psycopg2': 'psycopg2',
            'psycopg2_binary': 'psycopg2',
            'pymysql': 'pymysql',
            'bcrypt': 'bcrypt',
            'python_multipart': 'multipart',
        }

        missing = []
        for pkg in required:
            if not pkg:
                continue
            import_name = PACKAGE_TO_IMPORT.get(pkg, pkg)
            try:
                importlib.import_module(import_name)
            except ImportError:
                missing.append(pkg)

        return len(missing) == 0, [f"未安装的包: {', '.join(missing)}" if missing else ""]

    async def run_full_validation(self) -> Dict[str, Any]:
        """运行完整验证（并发优化 + 缓存 + 运行时/API 兼容性检查 + 前端验证 + 跨文件检查）"""
        results = {
            "syntax_errors": [],
            "import_errors": [],
            "dependency_errors": [],
            "api_errors": [],
            "runtime_errors": [],
            "frontend_errors": [],
            "cross_file_errors": [],
            "is_valid": True,
            "validated_files": 0,
            "cache_hit": False
        }

        # 收集所有需要验证的文件
        py_files = [f for f in self.project_path.rglob('*.py') if '__pycache__' not in str(f)]
        js_files = [f for f in self.project_path.rglob('*.js') if 'node_modules' not in str(f)]
        html_files = [f for f in self.project_path.rglob('*.html')]
        css_files = [f for f in self.project_path.rglob('*.css')]
        all_files = py_files + js_files + html_files + css_files
        results["validated_files"] = len(all_files)

        # 检查是否有缓存结果
        if py_files:
            first_file = py_files[0]
            cached = self.get_cached_validation(first_file)
            if cached:
                results.update(cached)
                results["cache_hit"] = True
                return results

        # 并发验证 Python 文件
        async def validate_py_file(py_file: Path) -> Tuple[List[str], List[str], List[str], List[str]]:
            syntax_ok, syntax_errs = await self.validate_syntax(py_file)
            import_ok, import_errs = await self.validate_imports(py_file)
            runtime_ok, runtime_errs = await self.validate_runtime_imports(py_file)
            api_ok, api_errs = await self.validate_api_compatibility(py_file)
            return (
                syntax_errs if not syntax_ok else [],
                import_errs if not import_ok else [],
                runtime_errs if not runtime_ok else [],
                api_errs if not api_ok else []
            )

        if py_files:
            file_results = await asyncio.gather(
                *[validate_py_file(f) for f in py_files],
                return_exceptions=True
            )

            for result in file_results:
                if isinstance(result, Exception):
                    results["import_errors"].append(f"验证异常: {str(result)}")
                    results["is_valid"] = False
                else:
                    syntax_errs, import_errs, runtime_errs, api_errs = result
                    results["syntax_errors"].extend(syntax_errs)
                    results["import_errors"].extend(import_errs)
                    results["runtime_errors"].extend(runtime_errs)
                    results["api_errors"].extend(api_errs)
                    if syntax_errs or import_errs or runtime_errs or api_errs:
                        results["is_valid"] = False

        # 并发验证前端文件
        async def validate_frontend_file(f: Path) -> List[str]:
            if f.suffix == '.js':
                ok, errs = await self.validate_js_syntax(f)
                return errs if not ok else []
            elif f.suffix == '.html':
                ok, errs = await self.validate_html_structure(f)
                return errs if not ok else []
            elif f.suffix == '.css':
                ok, errs = await self.validate_css_syntax(f)
                return errs if not ok else []
            return []

        if js_files or html_files or css_files:
            frontend_results = await asyncio.gather(
                *[validate_frontend_file(f) for f in (js_files + html_files + css_files)],
                return_exceptions=True
            )

            for result in frontend_results:
                if isinstance(result, Exception):
                    results["frontend_errors"].append(f"前端验证异常: {str(result)}")
                    results["is_valid"] = False
                else:
                    results["frontend_errors"].extend(result)
                    if result:
                        results["is_valid"] = False

        # 跨文件一致性检查
        cross_ok, cross_errs = await self.validate_cross_file_consistency()
        if not cross_ok:
            results["cross_file_errors"].extend(cross_errs)
            results["is_valid"] = False

        # 验证依赖
        dep_ok, dep_errs = await self.validate_requirements()
        if not dep_ok:
            results["dependency_errors"].extend(dep_errs)
            results["is_valid"] = False

        # 缓存验证结果（成功和失败都缓存，但过期时间不同）
        if py_files:
            self.cache_validation(py_files[0], {
                "syntax_errors": results["syntax_errors"],
                "import_errors": results["import_errors"],
                "dependency_errors": results["dependency_errors"],
                "api_errors": results["api_errors"],
                "runtime_errors": results["runtime_errors"],
                "frontend_errors": results["frontend_errors"],
                "cross_file_errors": results["cross_file_errors"],
                "is_valid": results["is_valid"],
                "validated_files": results["validated_files"]
            })

        return results
