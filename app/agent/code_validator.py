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
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
from pathlib import Path

from app.agent.markup_syntax import css_structure_errors, html_structure_errors


logger = logging.getLogger(__name__)


def _imports_symbol_from_module(source: str, module: str, symbol: str) -> bool:
    """源码中是否存在 `from <module> import <symbol>`（AST 精确匹配符号名）。

    文本子串匹配会把 `CORSMiddleware`/`GZipMiddleware` 等 fastapi 顶层合法再导出
    误判为 `Middleware`。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module == module:
            if any(alias.name == symbol for alias in node.names):
                return True
    return False


# 模块级复合语句：其中的定义同样对外可见（如 `try: from x import y`、
# `if TYPE_CHECKING:` 之外的普通 if 分支赋值）。
_MODULE_LEVEL_CONTAINERS = (
    ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While,
)


# 标准库顶层模块名。优先用解释器自带清单，缺失时退回常见子集。
_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", ())) or frozenset({
    'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing', 'asyncio', 'logging',
    'collections', 'functools', 'itertools', 'math', 'string', 'io', 'copy', 'time',
    'enum', 'dataclasses', 'abc', 'contextlib', 'urllib', 'http', 'email', 'hashlib',
    'hmac', 'secrets', 'base64', 'struct', 'textwrap', 'difflib', 'unittest', 'doctest',
    'pdb', 'traceback', 'warnings', 'weakref', 'types', 'importlib',
})


# 模块对象天然具备的属性：`from mod import __doc__` 等合法，但源码里没有定义。
_IMPLICIT_MODULE_ATTRS = frozenset({
    '__doc__', '__name__', '__file__', '__spec__', '__loader__',
    '__package__', '__path__', '__builtins__', '__cached__',
})


def _iter_module_scope(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """遍历模块作用域内的语句（进入复合语句，但不进入函数/类体）。"""
    for node in body:
        yield node
        if isinstance(node, _MODULE_LEVEL_CONTAINERS):
            yield from _iter_module_scope(node.body)
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    yield from _iter_module_scope(handler.body)
            # With/AsyncWith 没有 orelse/finalbody，用 getattr 兼容
            yield from _iter_module_scope(getattr(node, "orelse", ()) or ())
            yield from _iter_module_scope(getattr(node, "finalbody", ()) or ())


def _module_level_exports(tree: ast.Module) -> Dict[str, set]:
    """模块对外可见的类/函数/变量名（忽略函数与类体内部的局部定义）。"""
    exports: Dict[str, set] = {"classes": set(), "functions": set(), "variables": set()}
    for node in _iter_module_scope(tree.body):
        if isinstance(node, ast.ClassDef):
            exports["classes"].add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            exports["functions"].add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exports["variables"].add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            # `SECRET_KEY: str = "x"` 与 `x = 1` 一样是模块级导出
            exports["variables"].add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # 模块级导入的名字对外可见（再导出），如
            # __init__.py 里的 `from .factory import create_app`
            for alias in node.names:
                if alias.name != '*':
                    exports["variables"].add(alias.asname or alias.name)
    return exports


class CodeValidator:
    """代码验证器 - 语法、依赖、运行时、跨文件一致性验证（带缓存优化）"""

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
        self.project_path = Path(project_path).resolve()
        # 校验缓存与统计按实例隔离（CV7）：此前为类级属性，所有项目实例共享同一个
        # OrderedDict。全项目校验键是「文件内容拼接 hash」，不含项目路径，跨实例命中
        # 会返回另一个项目的错误列表；hits/misses 也相互串扰。`_validation_cache` 是
        # 既有外部读取点（orchestrator_files）引用的别名，仍指向同一实例缓存。
        self._lru_cache: OrderedDict = OrderedDict()
        self._validation_cache = self._lru_cache
        self._max_cache_bytes = 50 * 1024 * 1024
        self._cache_size_bytes = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def _import_search_paths(self, file_path: Path) -> List[str]:
        """Return the candidate directory and configured project roots for imports."""
        paths = [file_path.parent.resolve(), self.project_path]
        src_dir = self.project_path / "src"
        if src_dir.is_dir():
            paths.append(src_dir.resolve())
        return list(dict.fromkeys(str(path) for path in paths if path.is_dir()))

    def _project_top_level_packages(self) -> List[str]:
        """项目根下可被 `import X` 命中的顶层包/模块名。

        含 `__init__.py` 的目录是常规包；不含 `__init__.py` 但含 `.py` 文件的
        目录是 PEP 420 命名空间包（典型 `src/` 布局），同样可被 `import src.x`
        命中，不能当作第三方依赖。
        """
        names = []
        try:
            for entry in self.project_path.iterdir():
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue
                if entry.is_dir():
                    if (entry / "__init__.py").exists() or any(entry.glob("*.py")):
                        names.append(entry.name)
                elif entry.suffix == ".py":
                    names.append(entry.stem)
        except OSError:
            return []
        return names

    def _resolve_project_module(self, module: str) -> Optional[Path]:
        """把绝对模块名解析为项目内的源文件/包目录；项目外返回 None。

        直接按文件定位，绕开 sys.modules 与 sys.path：Agent 自身与生成项目
        常有同名包（如 app/），且并发校验时不应改写全局导入状态。
        """
        parts = module.split('.')
        if not all(parts):
            return None
        roots = [self.project_path]
        src_dir = self.project_path / "src"
        if src_dir.is_dir():
            roots.append(src_dir)
        for root in roots:
            base = root.joinpath(*parts)
            module_file = base.with_suffix('.py')
            if module_file.is_file():
                return module_file
            init_file = base / '__init__.py'
            if init_file.is_file():
                return init_file
            # PEP 420 命名空间包：目录无 __init__.py 也可被导入
            if base.is_dir() and any(base.glob('*.py')):
                return base
        return None

    def _missing_project_symbols(self, module: str, names: Iterable[str]) -> List[str]:
        """`from <module> import <name>` 中项目模块未导出的符号名。"""
        path = self._resolve_project_module(module)
        if path is None or not path.is_file():
            return []
        package_dir = path.parent if path.name == '__init__.py' else None
        try:
            exports = _module_level_exports(ast.parse(path.read_text(encoding='utf-8')))
        except (OSError, SyntaxError, ValueError):
            # 语法错误由 validate_syntax 负责，这里不重复报错
            return []
        available = exports["classes"] | exports["functions"] | exports["variables"]
        missing = []
        for name in names:
            if not name or name == '*' or name in available or name in _IMPLICIT_MODULE_ATTRS:
                continue
            sub_paths = []
            if package_dir is not None:
                # from pkg import mod -> pkg/mod.py；from pkg import sub -> pkg/sub/__init__.py
                sub_paths = [package_dir / f"{name}.py", package_dir / name / "__init__.py"]
            if not any(p.exists() for p in sub_paths):
                missing.append(name)
        return missing

    def _python_third_party_imports(self) -> List[str]:
        """项目中来自第三方包的顶层 Python 导入名（排序去重）。

        只用标准库或项目内模块的项目不需要依赖清单；该判断同样避免了把
        "只打印一段文字" 的单文件脚本判为缺少 requirements.txt。
        """
        local_modules = set(self._project_top_level_packages())
        found = set()
        for py_file in self.project_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source)
            except (OSError, SyntaxError, ValueError):
                # 无法解析的文件由语法校验负责，这里不重复报错
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level or not node.module:
                        continue
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name and name not in _STDLIB_MODULES and name not in local_modules:
                        found.add(name)
        return sorted(found)

    @classmethod
    def _compute_content_hash(cls, file_content: str) -> str:
        """计算文件内容的 SHA256 哈希"""
        import hashlib
        return hashlib.sha256(file_content.encode('utf-8')).hexdigest()[:16]

    def _clear_old_cache(self):
        now = time.time()
        expired_keys = []
        for key, entry in list(self._lru_cache.items()):
            ttl = self.SUCCESS_CACHE_TTL if entry[0].get("is_valid", False) else self.FAILURE_CACHE_TTL
            if now - entry[1] > ttl:
                expired_keys.append(key)
        for key in expired_keys:
            entry = self._lru_cache.pop(key)
            self._cache_size_bytes -= sys.getsizeof(key) + sys.getsizeof(entry)
        while self._cache_size_bytes > self._max_cache_bytes and self._lru_cache:
            oldest_key, oldest_entry = self._lru_cache.popitem(last=False)
            self._cache_size_bytes -= sys.getsizeof(oldest_key) + sys.getsizeof(oldest_entry)

    def get_cached_validation(self, file_path: Path) -> Optional[Dict]:
        cache_key = None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content_hash = self._compute_content_hash(content)
            cache_key = f"{file_path}:{content_hash}"
            if cache_key in self._lru_cache:
                result, timestamp = self._lru_cache[cache_key]
                ttl = self.SUCCESS_CACHE_TTL if result.get("is_valid", False) else self.FAILURE_CACHE_TTL
                if time.time() - timestamp <= ttl:
                    self._lru_cache.move_to_end(cache_key)
                    self._cache_hits += 1
                    return result
                else:
                    entry = self._lru_cache.pop(cache_key)
                    self._cache_size_bytes -= sys.getsizeof(cache_key) + sys.getsizeof(entry)
            self._cache_misses += 1
            return None
        except Exception as e:
            logger.debug(f"缓存读取失败 {cache_key or file_path}：{e}")
            self._cache_misses += 1
            return None

    def cache_validation(self, file_path: Path, result: Dict):
        cache_key = None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content_hash = self._compute_content_hash(content)
            cache_key = f"{file_path}:{content_hash}"
            self.store_validation(cache_key, result)
        except Exception as e:
            logger.debug(f"缓存写入失败 {cache_key or file_path}：{e}")

    def store_validation(self, cache_key: str, result: Dict):
        """按内容哈希键写入校验缓存。

        调用方可能已持有内存中的内容、文件尚未落盘，因此这里按 key 直接写入，
        不再读盘。缓存条目统一为 `(result, timestamp)` 元组，任何绕开本方法
        的裸结果写入都会让 `_clear_old_cache` 在 `entry[0]` 处抛错。
        """
        if cache_key in self._lru_cache:
            old_entry = self._lru_cache.pop(cache_key)
            self._cache_size_bytes -= sys.getsizeof(cache_key) + sys.getsizeof(old_entry)
        entry = (result, time.time())
        self._lru_cache[cache_key] = entry
        self._lru_cache.move_to_end(cache_key)
        self._cache_size_bytes += sys.getsizeof(cache_key) + sys.getsizeof(entry)
        self._clear_old_cache()

    def get_cached_validation_by_key(self, cache_key: str) -> Optional[Dict]:
        """按键读取校验结果（键由调用方构造，非文件路径）。

        `get_cached_validation` 面向真实文件路径（先读盘、再按内容算键），而
        `run_full_validation` 的键是「全项目内容 hash」合成串，无法作为文件
        打开，因此需要这个直接按键查表的入口。
        """
        entry = self._lru_cache.get(cache_key)
        if entry is None:
            self._cache_misses += 1
            return None
        result, timestamp = entry
        ttl = self.SUCCESS_CACHE_TTL if result.get("is_valid", False) else self.FAILURE_CACHE_TTL
        if time.time() - timestamp <= ttl:
            self._lru_cache.move_to_end(cache_key)
            self._cache_hits += 1
            return result
        self._lru_cache.pop(cache_key, None)
        self._cache_size_bytes -= sys.getsizeof(cache_key) + sys.getsizeof(entry)
        self._cache_misses += 1
        return None

    def get_cache_stats(self) -> Dict[str, Any]:
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0
        return {
            "entries": len(self._lru_cache),
            "size_bytes": self._cache_size_bytes,
            "max_bytes": self._max_cache_bytes,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
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

            # 用 ast 提取真实导入语句。按行文本解析会把 docstring/注释里的
            # "示例: from x import y" 也当成导入，并给相对导入生成假模块名。
            imports = set()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                # 语法错误由 validate_syntax 报告，这里不重复报错
                return True, []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split('.')[0]
                        if top:
                            imports.add(top)
                elif isinstance(node, ast.ImportFrom):
                    # 相对导入（level > 0）在项目包上下文外无法用 find_spec 判断，
                    # 交由完整性/符号校验处理，这里跳过以免误报。
                    if node.level or not node.module:
                        continue
                    top = node.module.split('.')[0]
                    if top:
                        imports.add(top)

            # 检查是否可以导入
            errors = []
            standard_libs = _STDLIB_MODULES

            # Include the project root even when a generated project has no src/tests directory.
            added_paths = []
            try:
                for import_path in reversed(self._import_search_paths(file_path)):
                    if import_path not in sys.path:
                        sys.path.insert(0, import_path)
                        added_paths.append(import_path)
            except Exception as e:
                logger.debug(f"sys.path 操作失败：{e}")

            for imp in imports:
                if imp in standard_libs:
                    continue
                try:
                    spec = importlib.util.find_spec(imp)
                    if spec is None:
                        errors.append(f"缺少依赖: {imp}")
                except (ImportError, ValueError):
                    errors.append(f"缺少依赖: {imp}")

            # Cleanup added paths
            for p in added_paths:
                if p in sys.path:
                    sys.path.remove(p)

            return len(errors) == 0, errors
        except Exception as e:
            return False, [f"导入验证失败: {str(e)}"]

    async def validate_runtime_imports(self, file_path: Path) -> Tuple[bool, List[str]]:
        """运行时导入验证：静态解析导入，不执行被校验代码。

        原实现用 `spec.loader.exec_module` 真实执行模块级代码：会触发被校验
        代码的副作用（连数据库、发请求、写文件），无超时；模块级阻塞 I/O 还会
        占住事件循环，使 `run_full_validation` 的 `asyncio.gather` 整体卡死，
        且 `asyncio.wait_for` 对同步阻塞无效。现改为 AST + 项目文件定位做静态
        检查：仍能检出项目内的缺失模块/符号，且不再改写 sys.path/sys.modules，
        并发校验安全。被校验代码模块级行为本身（AttributeError/TypeError 等）
        不再拦截，交由本地 Agent Host 运行时验证。
        """
        if file_path.suffix != '.py':
            return True, []

        # __init__.py 的导入依赖包上下文，单独校验易误报，交由跨文件校验处理
        if file_path.name == '__init__.py':
            return True, []

        errors: List[str] = []
        try:
            source = file_path.read_text(encoding='utf-8')
        except Exception as e:
            return False, [f"运行时验证异常: {str(e)}"]

        # 检查 passlib 错误导入模式（文本规则，与执行无关）
        if 'import passlib.hash.bcrypt' in source:
            errors.append("passlib 导入错误: 应使用 'from passlib.hash import bcrypt' 而非 'import passlib.hash.bcrypt'")
        if 'import passlib.hash' in source and 'from passlib.hash import' not in source:
            errors.append("passlib 导入错误: 'import passlib.hash' 无法使用 bcrypt，应改为 'from passlib.hash import bcrypt'")

        try:
            tree = ast.parse(source)
        except SyntaxError:
            # 语法错误由 validate_syntax 报告，这里不重复报错
            return len(errors) == 0, errors

        project_top_levels = set(self._project_top_level_packages())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split('.')[0]
                    if self._resolve_project_module(alias.name) is None and top in project_top_levels:
                        errors.append(f"运行时导入失败: No module named '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                # 相对导入（level > 0）需要包上下文，交由跨文件校验处理
                if node.level or not node.module:
                    continue
                top = node.module.split('.')[0]
                if self._resolve_project_module(node.module) is None:
                    # 第三方包未安装/拼写错误取决于 Agent 执行环境，不算生成代码缺陷
                    if top in project_top_levels:
                        errors.append(f"运行时导入失败: No module named '{node.module}'")
                    continue
                for name in self._missing_project_symbols(
                    node.module, [alias.name for alias in node.names]
                ):
                    errors.append(f"运行时导入失败: 无法从 '{node.module}' 导入 '{name}'")

        return len(errors) == 0, errors

    async def validate_api_compatibility(self, file_path: Path) -> Tuple[bool, List[str]]:
        """API 兼容性检查：已知库的版本不兼容问题"""
        if file_path.suffix != '.py':
            return True, []

        errors = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # FastAPI OAuth2PasswordBearer 参数名：现代版本为 camelCase 的
            # tokenUrl，snake_case 的 token_url 是早期写法。方向取自
            # API_COMPATIBILITY_RULES 声明，避免两处规则各说一套。
            oauth_rename = self.API_COMPATIBILITY_RULES["fastapi"]["OAuth2PasswordBearer"]
            legacy_param, current_param = next(iter(oauth_rename.items()))
            if (
                'OAuth2PasswordBearer' in source
                and f'{legacy_param}=' in source
                and f'{current_param}=' not in source
            ):
                errors.append(
                    f"FastAPI 兼容性: OAuth2PasswordBearer 参数应为 "
                    f"'{current_param}=' 而非 '{legacy_param}='"
                )

            # FastAPI Middleware 导入位置变更（只匹配精确符号：CORSMiddleware 等
            # 由 fastapi 顶层正常再导出，子串匹配会误判合法导入）
            if _imports_symbol_from_module(source, 'fastapi', 'Middleware'):
                errors.append("FastAPI 兼容性: Middleware 已从 fastapi 移至 fastapi.middleware.cors")

            # SQLAlchemy 2.0: DeclarativeBase vs Base + BaseModel MRO 冲突
            if 'class' in source and 'Base' in source and 'BaseModel' in source:
                if re.search(r'class\s+\w+\(.*Base.*BaseModel.*\)', source):
                    errors.append("SQLAlchemy 兼容性: 不能同时继承 Base 和 BaseModel (MRO 冲突)")

            # APIRouter.exception_handler 不存在（app.exception_handler 是合法写法）
            router_names = set(re.findall(r'(\w+)\s*=\s*APIRouter\s*\(', source))
            if any(f'{name}.exception_handler' in source for name in router_names):
                errors.append("FastAPI 兼容性: APIRouter 没有 exception_handler 属性，应改用 router.add_exception_handler 或 app 级别注册")

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
            # 负返回码表示 node 被信号终止（如 OOM），属环境异常而非语法错误，
            # 不能据此判为无效代码。
            if proc.returncode < 0:
                logger.warning("node 被信号终止，跳过 JS 语法校验: %s", proc.returncode)
                return True, []
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

            errors = html_structure_errors(content)
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

            errors = css_structure_errors(content)
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
                rel = f.relative_to(self.project_path)
                if rel.name == '__init__.py':
                    # 包入口对外就是包本身：app/__init__.py -> app
                    module_name = '.'.join(rel.parent.parts)
                else:
                    module_name = '.'.join(rel.with_suffix('').parts)
                defined_symbols[module_name] = _module_level_exports(tree)
            except Exception as e:
                logger.debug(f"AST 解析失败 {f}（语法错误跳过）：{e}")
                pass  # 语法错误的文件跳过

        # 2. 检查 main.py 中的导入是否匹配实际模块和符号
        main_file = self.project_path / 'main.py'
        if main_file.exists():
            try:
                with open(main_file, 'r', encoding='utf-8') as f:
                    main_content = f.read()

                # 用 ast 提取 from X import Y。按行文本解析会把 `import Y as Z`、
                # 括号折行和注释都拼成假名字，产生假的「未导出」报错。
                from_imports = []
                try:
                    main_tree = ast.parse(main_content)
                except SyntaxError:
                    main_tree = None
                if main_tree is not None:
                    for node in ast.walk(main_tree):
                        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                            from_imports.append(
                                (node.module, [alias.name for alias in node.names])
                            )
                for module, imported_names in from_imports:
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
                                    # 可能是从子模块或子包导入：
                                    # from pkg import mod   -> pkg/mod.py
                                    # from pkg import sub   -> pkg/sub/__init__.py
                                    module_dir = module.replace('.', '/')
                                    sub_module_paths = (
                                        self.project_path / module_dir / f"{name}.py",
                                        self.project_path / module_dir / name / "__init__.py",
                                    )
                                    if not any(p.exists() for p in sub_module_paths):
                                        errors.append(f"跨文件引用: '{module}' 模块未导出 '{name}' (实际导出: {', '.join(sorted(all_symbols)) if all_symbols else '无'})")
            except Exception as e:
                logger.debug(f"跨文件引用检查失败：{e}")

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
            # 导入检查结果只作为诊断信息：包是否安装取决于 Agent 执行环境，
            # 不代表生成代码有缺陷，因此不参与 is_valid（与 validate_requirements 一致）。
            _import_ok, import_errs = await self.validate_imports(file_path)
            runtime_ok, runtime_errs = await self.validate_runtime_imports(file_path)
            api_ok, api_errs = await self.validate_api_compatibility(file_path)

            results["syntax_errors"].extend(syntax_errs)
            results["import_errors"].extend(import_errs)
            results["runtime_errors"].extend(runtime_errs)
            results["api_errors"].extend(api_errs)

            if not syntax_ok or not runtime_ok or not api_ok:
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

    @staticmethod
    def _packages_from_pipfile(pipfile: Path) -> List[str]:
        """解析 Pipfile 依赖名。

        Pipfile 是 TOML 格式，用标准库 `tomllib`（3.11+）解析。此前用第三方
        `toml` 包，而它未在依赖中声明，环境缺包时异常被吞掉，依赖校验会静默
        通过。
        """
        import tomllib
        with open(pipfile, 'rb') as f:
            pipdata = tomllib.load(f)
        deps = list(pipdata.get('packages', {}).keys()) + list(pipdata.get('dev-packages', {}).keys())
        return [d.lower().replace('-', '_').split('[')[0] for d in deps if not d.startswith(('.', '/'))]

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
            except Exception as e:
                logger.debug(f"requirements.txt 解析失败：{e}")
        elif pipfile.exists():
            found_file = pipfile
            try:
                required = self._packages_from_pipfile(pipfile)
            except Exception as e:
                logger.debug(f"Pipfile 解析失败：{e}")

        if not found_file:
            # 非 Python 项目（如纯前端工程）就没有 Python 依赖清单，不算缺陷；
            # 只用标准库/项目内模块的 Python 代码同样无需依赖清单。
            if not any(self.project_path.rglob('*.py')):
                return True, []
            third_party = self._python_third_party_imports()
            if not third_party:
                return True, []
            return False, [
                "缺少 requirements.txt / pyproject.toml / Pipfile"
                f"（项目导入了第三方包: {', '.join(third_party)}）"
            ]

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

        # 包是否安装取决于 Agent 执行环境，不代表生成代码有缺陷，因此不计入
        # 代码有效性，避免把环境缺包误判为生成失败。
        if missing:
            logger.warning(
                "依赖清单中的包在当前环境未安装（不计入代码有效性）: %s",
                ", ".join(missing),
            )
        return True, []

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

        # 检查是否有缓存结果（使用所有文件的哈希作为缓存 key）
        if all_files:
            all_contents = ""
            for f in all_files:
                try:
                    all_contents += f.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    all_contents += str(f)
            content_hash = self._compute_content_hash(all_contents)
            cache_key = f"full_validation:{content_hash}"
            cached = self.get_cached_validation_by_key(cache_key)
            if cached:
                results.update(cached)
                results["cache_hit"] = True
                return results

        # 并发验证 Python 文件
        async def validate_py_file(py_file: Path) -> Tuple[List[str], List[str], List[str], List[str]]:
            syntax_ok, syntax_errs = await self.validate_syntax(py_file)
            _import_ok, import_errs = await self.validate_imports(py_file)
            runtime_ok, runtime_errs = await self.validate_runtime_imports(py_file)
            api_ok, api_errs = await self.validate_api_compatibility(py_file)
            return (
                syntax_errs if not syntax_ok else [],
                import_errs,
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
                    # import_errs 只上报环境缺包等诊断信息，不参与有效性判定
                    if syntax_errs or runtime_errs or api_errs:
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
        if all_files:
            self.store_validation(cache_key, {
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
