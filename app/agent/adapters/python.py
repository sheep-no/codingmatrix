"""
PythonLanguageAdapter - Python 语言适配器

处理 Python 特有的：
- 导入语法 (import xxx, from xxx import yyy)
- 包结构 (__init__.py)
- 文件类型推断
- 符号定义提取
"""

import ast
import builtins
from functools import lru_cache
import re
import symtable
import sysconfig
from typing import Dict, List, Mapping, Tuple
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

        # 应用入口
        ("main.py", "entry"),
        ("app.py", "entry"),
        ("server.py", "entry"),

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

    def source_diagnostics(self, content: str, file_path: str = "") -> Tuple[str, ...]:
        """Report unresolved globals and eager annotations using Python semantics."""
        try:
            tree = ast.parse(content, filename=file_path)
            symbol_table = symtable.symtable(content, file_path, "exec")
        except SyntaxError:
            return ()

        diagnostics: list[str] = []
        has_star_import = any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        )
        module_bound_names = {
            symbol.get_name()
            for symbol in symbol_table.get_symbols()
            if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
        }
        implicit_names = {
            "__builtins__", "__cached__", "__doc__", "__file__", "__loader__",
            "__name__", "__package__", "__spec__",
        }
        available_names = module_bound_names | set(dir(builtins)) | implicit_names
        undefined_names = self._undefined_global_names(symbol_table, available_names)
        if undefined_names and not has_star_import:
            diagnostics.append(
                "Python module uses undefined global names: "
                + ", ".join(sorted(undefined_names))
            )

        if not self._defers_annotations(tree):
            forward_names = self._eager_forward_annotation_names(tree)
            if forward_names:
                diagnostics.append(
                    "Python module evaluates annotations before definitions are available: "
                    + ", ".join(sorted(forward_names))
                )
        for module, names in self._unavailable_import_symbols(tree).items():
            diagnostics.append(
                f"Python module {module} does not export: {', '.join(names)}"
            )
        incompatible_constructors = self._incompatible_local_constructor_calls(tree)
        if incompatible_constructors:
            diagnostics.append(
                "Python local classes do not accept the supplied constructor arguments: "
                + ", ".join(incompatible_constructors)
            )
        return tuple(diagnostics)

    def extract_contract_facts(
        self,
        content: str,
        file_path: str = "",
    ) -> Mapping[str, Tuple[str, ...]]:
        facts = dict(super().extract_contract_facts(content, file_path))
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return facts
        facts["base_classes"] = tuple(
            base.id if isinstance(base, ast.Name) else base.attr
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for base in node.bases
            if isinstance(base, (ast.Name, ast.Attribute))
        )
        return facts

    def repair_source(
        self,
        content: str,
        file_path: str,
        diagnostics: Tuple[str, ...],
    ) -> str | None:
        repaired = content
        if any("does not export" in item for item in diagnostics):
            repaired = self._remove_unused_unavailable_imports(repaired, file_path)
        if any("uses undefined global names" in item for item in diagnostics):
            repaired = self._add_uniquely_available_imports(repaired, file_path)
        if any("evaluates annotations before definitions" in item for item in diagnostics):
            repaired = self.defer_annotations(repaired, file_path) or repaired
        return repaired if repaired != content else None

    @staticmethod
    def _undefined_global_names(
        symbol_table: symtable.SymbolTable,
        available_names: set[str],
    ) -> set[str]:
        undefined_names: set[str] = set()
        pending_tables = [symbol_table]
        while pending_tables:
            current_table = pending_tables.pop()
            pending_tables.extend(current_table.get_children())
            undefined_names.update(
                symbol.get_name()
                for symbol in current_table.get_symbols()
                if symbol.is_referenced()
                and symbol.is_global()
                and symbol.get_name() not in available_names
            )
        return undefined_names

    def _unavailable_import_symbols(self, tree: ast.Module) -> Dict[str, Tuple[str, ...]]:
        unavailable: Dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if self.is_project_module(node.module):
                continue
            exports = self._static_module_exports(node.module)
            if exports is None:
                continue
            missing = tuple(sorted(
                alias.name
                for alias in node.names
                if alias.name != "*" and alias.name not in exports
            ))
            if missing:
                unavailable.setdefault(node.module, set()).update(missing)
        return {
            module: tuple(sorted(names))
            for module, names in unavailable.items()
        }

    @staticmethod
    def _incompatible_local_constructor_calls(tree: ast.Module) -> Tuple[str, ...]:
        classes_without_constructors = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and not node.bases
            and not node.keywords
            and not node.decorator_list
            and not any(
                isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and member.name in {"__init__", "__new__"}
                for member in node.body
            )
        }
        return tuple(sorted({
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in classes_without_constructors
            and (node.args or node.keywords)
        }))

    def _remove_unused_unavailable_imports(self, content: str, file_path: str) -> str:
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return content
        unavailable = self._unavailable_import_symbols(tree)
        if not unavailable:
            return content
        referenced = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        lines = content.splitlines(keepends=True)
        line_offsets = []
        offset = 0
        for line in lines:
            line_offsets.append(offset)
            offset += len(line)
        replacements: list[tuple[int, int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            missing = set(unavailable.get(node.module, ()))
            if not missing:
                continue
            removable = {
                alias.name
                for alias in node.names
                if alias.name in missing
                and (alias.asname or alias.name) not in referenced
            }
            if not removable:
                continue
            retained = [alias for alias in node.names if alias.name not in removable]
            replacement = ""
            if retained:
                names = ", ".join(
                    alias.name + (f" as {alias.asname}" if alias.asname else "")
                    for alias in retained
                )
                replacement = f"from {node.module} import {names}"
            start = line_offsets[node.lineno - 1] + node.col_offset
            end = line_offsets[node.end_lineno - 1] + node.end_col_offset
            replacements.append((start, end, replacement))
        for start, end, replacement in reversed(replacements):
            content = content[:start] + replacement + content[end:]
        return content

    def _add_uniquely_available_imports(self, content: str, file_path: str) -> str:
        try:
            tree = ast.parse(content, filename=file_path)
            table = symtable.symtable(content, file_path, "exec")
        except SyntaxError:
            return content
        bound_names = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
        }
        available_names = bound_names | set(dir(builtins)) | {
            "__builtins__", "__cached__", "__doc__", "__file__", "__loader__",
            "__name__", "__package__", "__spec__",
        }
        undefined = self._undefined_global_names(table, available_names)
        import_nodes = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and not node.level
            and node.module
            and not self.is_project_module(node.module)
            and all(alias.name != "*" for alias in node.names)
        ]
        providers: Dict[str, list[ast.ImportFrom]] = {}
        for node in import_nodes:
            exports = self._static_module_exports(node.module)
            if exports is None:
                continue
            for name in undefined & set(exports):
                providers.setdefault(name, []).append(node)
        additions: Dict[int, set[str]] = {}
        nodes_by_id = {id(node): node for node in import_nodes}
        for name, nodes in providers.items():
            unique_modules = {node.module for node in nodes}
            if len(unique_modules) == 1:
                additions.setdefault(id(nodes[0]), set()).add(name)
        if not additions:
            return content
        lines = content.splitlines(keepends=True)
        line_offsets = []
        offset = 0
        for line in lines:
            line_offsets.append(offset)
            offset += len(line)
        replacements: list[tuple[int, int, str]] = []
        for node_id, names_to_add in additions.items():
            node = nodes_by_id[node_id]
            names = [
                alias.name + (f" as {alias.asname}" if alias.asname else "")
                for alias in node.names
            ]
            names.extend(sorted(names_to_add))
            start = line_offsets[node.lineno - 1] + node.col_offset
            end = line_offsets[node.end_lineno - 1] + node.end_col_offset
            replacements.append((
                start,
                end,
                f"from {node.module} import {', '.join(names)}",
            ))
        for start, end, replacement in reversed(replacements):
            content = content[:start] + replacement + content[end:]
        return content

    @staticmethod
    @lru_cache(maxsize=256)
    def _static_module_exports(module: str) -> frozenset[str] | None:
        relative_path = Path(*module.split("."))
        roots = tuple(dict.fromkeys(
            Path(path)
            for key, path in sysconfig.get_paths().items()
            if key in {"stdlib", "platstdlib", "purelib", "platlib"} and path
        ))
        source_path = next(
            (
                candidate
                for root in roots
                for candidate in (
                    root / relative_path.with_suffix(".py"),
                    root / relative_path / "__init__.py",
                    root / relative_path.with_suffix(".pyi"),
                    root / relative_path / "__init__.pyi",
                )
                if candidate.is_file()
            ),
            None,
        )
        if source_path is None:
            return None
        try:
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
            table = symtable.symtable(source, str(source_path), "exec")
        except (OSError, UnicodeError, SyntaxError):
            return None
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__getattr__"
            for node in tree.body
        ) or any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in tree.body
        ):
            return None
        exports = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
        }
        return frozenset(exports)

    @staticmethod
    def _defers_annotations(tree: ast.Module) -> bool:
        return any(
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
            for node in tree.body
        )

    @classmethod
    def _eager_forward_annotation_names(cls, tree: ast.Module) -> set[str]:
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        available = set(dir(builtins))
        unresolved: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                available.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
                continue
            if isinstance(node, ast.ImportFrom):
                available.update(alias.asname or alias.name for alias in node.names)
                continue
            annotations: list[ast.AST] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                annotations.extend(arg.annotation for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs) if arg.annotation)
                if node.args.vararg and node.args.vararg.annotation:
                    annotations.append(node.args.vararg.annotation)
                if node.args.kwarg and node.args.kwarg.annotation:
                    annotations.append(node.args.kwarg.annotation)
                if node.returns:
                    annotations.append(node.returns)
            elif isinstance(node, ast.ClassDef):
                annotations.extend(
                    statement.annotation
                    for statement in node.body
                    if isinstance(statement, ast.AnnAssign)
                )
            elif isinstance(node, ast.AnnAssign):
                annotations.append(node.annotation)
            for annotation in annotations:
                unresolved.update(
                    child.id
                    for child in ast.walk(annotation)
                    if isinstance(child, ast.Name)
                    and child.id in definitions
                    and child.id not in available
                )
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                available.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                available.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
        return unresolved

    @staticmethod
    def defer_annotations(content: str, file_path: str = "") -> str | None:
        """Return a minimal candidate that safely defers annotation evaluation."""
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return None
        if PythonLanguageAdapter._defers_annotations(tree):
            return None
        lines = content.splitlines(keepends=True)
        insertion = 0
        if tree.body and isinstance(tree.body[0], ast.Expr):
            value = tree.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                insertion = getattr(tree.body[0], "end_lineno", tree.body[0].lineno)
        lines.insert(insertion, "from __future__ import annotations\n")
        return "".join(lines)

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

        filename = Path(file_path).name.lower()
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return "test"

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
