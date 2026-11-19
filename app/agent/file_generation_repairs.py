"""代码生成后的校验与修复辅助函数。

从 ``app.agent.orchestrator_files`` 拆分而来，保持行为不变。
"""

import ast
import builtins
import importlib.util
import json
import logging
import re
import subprocess
import symtable
from pathlib import Path

logger = logging.getLogger(__name__)

# 写入类工具名称（用于编辑标记检测）
_WRITE_TOOLS = {"partial_update", "insert_content", "regex_replace"}


def _python_module_name(file_path: str) -> str:
    normalized = file_path.replace('\\', '/').removesuffix('.py')
    normalized = normalized.removesuffix('/__init__')
    return normalized.replace('/', '.')


def _python_project_module_aliases(all_project_files: list[str], current_file: str) -> dict[str, str]:
    """Resolve unique short imports such as ``models`` from planned paths."""
    candidates: dict[str, set[str]] = {}
    for path in all_project_files:
        if not path.endswith('.py') or path == current_file:
            continue
        module = _python_module_name(path)
        parts = module.split('.')
        aliases = {module, parts[-1]}
        if len(parts) > 1:
            aliases.add(parts[-2])
        for alias in aliases:
            candidates.setdefault(alias, set()).add(module)
    return {
        alias: next(iter(modules))
        for alias, modules in candidates.items()
        if len(modules) == 1
    }


def _python_exports(content: str) -> set[str]:
    tree = ast.parse(content)
    exports = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    exports.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                exports.add(alias.asname or alias.name.split('.', 1)[0])
    return exports


def _python_defined_exports(content: str) -> set[str]:
    """Return symbols defined by a module, excluding imported re-exports."""
    tree = ast.parse(content)
    exports = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            exports.update(target.id for target in targets if isinstance(target, ast.Name))
    return exports


def _structured_import_diagnostics(errors: list[str]) -> list[dict[str, str]]:
    """将静态门禁文本转换为模型可直接执行的诊断项。"""
    diagnostics = []
    for error in errors:
        diagnostic = {"message": error}
        match = re.match(r"(.+?\.py) 未导出符号 (.+)，", error)
        if match:
            diagnostic.update({
                "type": "missing_export",
                "dependency_file": match.group(1),
                "symbol": match.group(2),
            })
        elif "名称 " in error and "未定义或导入" in error:
            symbol = error.split("名称 ", 1)[1].split(" 在", 1)[0]
            diagnostic.update({"type": "undefined_global", "symbol": symbol})
        elif error.startswith("调用 "):
            diagnostic["type"] = "signature_mismatch"
        elif "禁止混用" in error:
            diagnostic["type"] = "database_abstraction_mismatch"
        elif error.startswith("修复响应无效"):
            diagnostic["type"] = "repair_response_invalid"
        else:
            diagnostic["type"] = "static_validation_error"
        diagnostics.append(diagnostic)
    return diagnostics


def _repair_python_known_imports(content: str, errors: list[str]) -> str:
    """Add unambiguous framework imports reported as undefined globals."""
    if "模块 sqlalchemy.ext.session 当前运行时不可导入" in errors:
        content = re.sub(
            r"^from[ \t]+sqlalchemy\.ext\.session[ \t]+import[ \t]+sessionmaker[ \t]*$",
            "from sqlalchemy.orm import sessionmaker",
            content,
            flags=re.MULTILINE,
        )
    known_imports = {
        "datetime": "from datetime import datetime",
        "Depends": "from fastapi import Depends",
        "FastAPI": "from fastapi import FastAPI",
        "HTTPException": "from fastapi import HTTPException",
        "TestClient": "from fastapi.testclient import TestClient",
        "Session": "from sqlalchemy.orm import Session",
        "create_engine": "from sqlalchemy import create_engine",
        "pytest": "import pytest",
        "List": "from typing import List",
        "Optional": "from typing import Optional",
        "Dict": "from typing import Dict",
        "Tuple": "from typing import Tuple",
        "Set": "from typing import Set",
        "Any": "from typing import Any",
        "Union": "from typing import Union",
        "Literal": "from typing import Literal",
        "Annotated": "from typing import Annotated",
        "Callable": "from typing import Callable",
        "Iterable": "from typing import Iterable",
        "Sequence": "from typing import Sequence",
        "Mapping": "from typing import Mapping",
    }
    missing_names = {
        match.group(1)
        for error in errors
        if (match := re.fullmatch(r"名称 (\w+) 在模块全局作用域中未定义或导入", error))
    }
    imports = [
        statement
        for name, statement in known_imports.items()
        if name in missing_names and statement not in content
    ]
    if not imports:
        return content
    return "\n".join(imports) + "\n" + content.lstrip("\n")


def _repair_python_sqlalchemy_text_execute(content: str, file_path: str) -> str:
    """Wrap raw SQL passed to execute() for SQLAlchemy 2 compatibility."""
    if not file_path.endswith(".py") or ".execute(" not in content:
        return content
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content

    lines = content.splitlines(keepends=True)
    line_offsets = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line)

    def source_offset(line_number: int, byte_column: int) -> int:
        line = lines[line_number - 1]
        char_column = len(line.encode("utf-8")[:byte_column].decode("utf-8"))
        return line_offsets[line_number - 1] + char_column

    replacements = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        receiver = node.func.value
        if (
            isinstance(receiver, ast.Name)
            and receiver.id in {"conn", "connection", "cursor"}
            and "sqlite3.connect" in content
        ):
            continue
        argument = node.args[0]
        start = source_offset(argument.lineno, argument.col_offset)
        end = source_offset(argument.end_lineno, argument.end_col_offset)
        replacements.append((start, end))

    if not replacements:
        return content
    for start, end in sorted(replacements, reverse=True):
        content = content[:start] + f"text({content[start:end]})" + content[end:]
    if not re.search(r"^from\s+sqlalchemy\s+import\s+.*\btext\b", content, re.MULTILINE):
        content = "from sqlalchemy import text\n" + content.lstrip("\n")
    return content


def _repair_python_fastapi_class_route_registration(content: str, file_path: str) -> str:
    """Convert malformed FastAPI class route declarations to app.add_api_route calls."""
    if not file_path.endswith(".py") or "app.include_router" not in content:
        return content
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content
    function_names = {node.name for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    lines = content.splitlines(keepends=True)
    offsets, current = [], 0
    for line in lines:
        offsets.append(current)
        current += len(line)

    def source_offset(line_number: int, byte_column: int) -> int:
        line = lines[line_number - 1]
        column = len(line.encode("utf-8")[:byte_column].decode("utf-8"))
        return offsets[line_number - 1] + column

    def handler_for(method: str, path: str) -> str | None:
        resource = path.rstrip("/").split("/")[-1]
        has_id = "{" in resource
        if has_id:
            resource = path.rstrip("/").split("/")[-2]
        singular = resource.rstrip("s")
        prefixes = {
            "POST": ("create_",),
            "GET": (("get_",) if has_id else ("list_", "get_all_")),
            "PUT": ("update_",),
            "DELETE": ("delete_",),
        }[method]
        candidates = [f"{prefix}{name}" for prefix in prefixes for name in (singular, resource)]
        return next((name for name in candidates if name in function_names), None)

    replacements = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "app"
                and node.func.attr == "include_router" and node.args):
            continue
        router = node.args[0]
        routes_keyword = next((keyword for keyword in getattr(router, "keywords", [])
                               if keyword.arg == "routes"), None)
        if not (isinstance(router, ast.Call) and isinstance(router.func, ast.Name)
                and router.func.id == "FastAPI" and routes_keyword
                and isinstance(routes_keyword.value, ast.List)):
            continue
        prefix_keyword = next((keyword for keyword in router.keywords if keyword.arg == "prefix"), None)
        prefix = (prefix_keyword.value.value.rstrip("/")
                  if prefix_keyword and isinstance(prefix_keyword.value, ast.Constant)
                  and isinstance(prefix_keyword.value.value, str) else "")
        route_lines = []
        for route in routes_keyword.value.elts:
            if not (isinstance(route, ast.Call) and isinstance(route.func, ast.Attribute)
                    and isinstance(route.func.value, ast.Name) and route.func.value.id == "FastAPI"
                    and route.args and isinstance(route.args[0], ast.Constant)
                    and isinstance(route.args[0].value, str)):
                route_lines = []
                break
            method = route.func.attr.upper()
            route_path = route.args[0].value
            handler = handler_for(method, route_path)
            if not handler:
                route_lines = []
                break
            kwargs = [f'methods=["{method}"]']
            for keyword in route.keywords:
                if keyword.arg in {"response_model", "status_code", "summary", "description"}:
                    value = ast.get_source_segment(content, keyword.value)
                    if value:
                        kwargs.append(f"{keyword.arg}={value}")
            route_lines.append(f"app.add_api_route({(prefix + route_path)!r}, {handler}, {', '.join(kwargs)})")
        if route_lines:
            replacements.append((source_offset(node.lineno, node.col_offset),
                                 source_offset(node.end_lineno, node.end_col_offset),
                                 "\n".join(route_lines)))
    for start, end, replacement in sorted(replacements, reverse=True):
        content = content[:start] + replacement + content[end:]
    return content


def _repair_python_sqlite_connection_url(content: str, file_path: str) -> str:
    """Convert SQLAlchemy-style SQLite URLs passed to sqlite3.connect."""
    if not file_path.endswith(".py") or "sqlite3.connect" not in content:
        return content
    return re.sub(r"sqlite3\.connect\(\s*(['\"])sqlite:///([^'\"]+)\1\s*\)",
                  r"sqlite3.connect(\1\2\1)", content)


def _repair_python_invalid_code_marker(content: str, file_path: str) -> str:
    """Remove generated debug markers that assign None to a function __code__."""
    if not file_path.endswith(".py"):
        return content
    return re.sub(r"^\s*[^\n#]+\.\__code__\s*=\s*None\s*(?:#.*)?\n?", "", content, flags=re.MULTILINE)


def _repair_python_unmounted_fastapi_router(content: str, file_path: str) -> str:
    """Mount a declared APIRouter when the generated app omitted the include call."""
    if not file_path.endswith(".py") or "APIRouter(" not in content or "app.include_router" in content:
        return content
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content
    router_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "APIRouter"
    }
    if not router_names:
        return content
    return content.rstrip() + "\n\n" + "\n".join(
        f"app.include_router({router_name})" for router_name in sorted(router_names)
    ) + "\n"


def _repair_python_sqlalchemy_datetime_defaults(content: str, file_path: str) -> str:
    """Replace calls to nonexistent SQLAlchemy DateTime clock methods."""
    if not file_path.endswith(".py") or not re.search(r"\bDateTime\.(?:now|utcnow)\(\)", content):
        return content
    content = re.sub(r"\bDateTime\.(?:now|utcnow)\(\)", "func.now()", content)
    if not re.search(r"^from\s+sqlalchemy\s+import\s+.*\bfunc\b", content, re.MULTILINE):
        content = "from sqlalchemy import func\n" + content.lstrip("\n")
    return content


def _repair_python_sqlalchemy_get_db(
    content: str,
    file_path: str,
    architecture: dict | None = None,
) -> str:
    """Complete the standard FastAPI session dependency for SQLAlchemy databases."""
    if not _file_matches_role(file_path, architecture, {"database"}) or "SessionLocal" not in content:
        return content
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content
    session_local_is_none = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "SessionLocal"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value is None
        for node in tree.body
    )
    if session_local_is_none:
        content = re.sub(
            r"^SessionLocal(?:\s*:[^=]+)?\s*=\s*None\s*$",
            "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)",
            content,
            flags=re.MULTILINE,
        )
        if not re.search(
            r"^(?:from\s+sqlalchemy\.orm\s+import\s+.*\bsessionmaker\b|import\s+sqlalchemy\.orm)",
            content,
            re.MULTILINE,
        ):
            content = "from sqlalchemy.orm import sessionmaker\n" + content.lstrip("\n")
        tree = ast.parse(content, filename=file_path)
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_db" for node in tree.body):
        return content
    return content.rstrip() + (
        "\n\n\ndef get_db():\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        yield db\n"
        "    finally:\n"
        "        db.close()\n"
    )


def _repair_python_project_call_keywords(content: str, errors: list[str]) -> str:
    """Remove keyword arguments proven absent from a generated dependency signature."""
    invalid_keywords: dict[str, set[str]] = {}
    pattern = re.compile(r"调用 (\w+) 使用了未声明参数 ([\w, ]+)，请匹配 .+ 中的真实签名")
    for error in errors:
        match = pattern.fullmatch(error)
        if match:
            invalid_keywords.setdefault(match.group(1), set()).update(
                name.strip() for name in match.group(2).split(",") if name.strip()
            )
    if not invalid_keywords:
        return content
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    changed = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        rejected = invalid_keywords.get(node.func.id)
        if not rejected:
            continue
        retained = [keyword for keyword in node.keywords if keyword.arg not in rejected]
        if len(retained) != len(node.keywords):
            node.keywords = retained
            changed = True
    if not changed:
        return content
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _repair_python_schema_field_access(content: str, errors: list[str]) -> str:
    """Remove operations that read fields absent from generated request schemas."""
    invalid_attributes = {
        (match.group(1), match.group(2))
        for error in errors
        if (
            match := re.fullmatch(
                r".+?\.py 访问 (\w+)\.(\w+)，但 .+?\.py 的 \w+ 未定义字段 \w+",
                error,
            )
        )
    }
    if not invalid_attributes:
        return content
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    def contains_invalid_attribute(node: ast.AST) -> bool:
        return any(
            isinstance(candidate, ast.Attribute)
            and isinstance(candidate.value, ast.Name)
            and (candidate.value.id, candidate.attr) in invalid_attributes
            for candidate in ast.walk(node)
        )

    class SchemaFieldRepair(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            node.keywords = [
                keyword for keyword in node.keywords
                if not contains_invalid_attribute(keyword.value)
            ]
            return node

        def visit_If(self, node):
            if contains_invalid_attribute(node.test):
                return None
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

        def visit_Assign(self, node):
            if contains_invalid_attribute(node.value):
                return None
            return self.generic_visit(node)

        def visit_AnnAssign(self, node):
            if node.value is not None and contains_invalid_attribute(node.value):
                return None
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

        visit_AsyncFunctionDef = visit_FunctionDef

    repaired_tree = SchemaFieldRepair().visit(tree)
    ast.fix_missing_locations(repaired_tree)
    repaired = ast.unparse(repaired_tree) + "\n"
    return repaired if repaired != content else content


def _repair_python_project_symbol_imports(
    content: str,
    errors: list[str],
    generated_contents: dict[str, str],
) -> str:
    """Import project symbols from their unique generated definition."""
    defined_exporters: dict[str, list[str]] = {}
    exported_symbols: dict[str, list[str]] = {}
    for dependency_path, dependency_source in generated_contents.items():
        if not dependency_path.endswith(".py"):
            continue
        try:
            for name in _python_exports(dependency_source):
                exported_symbols.setdefault(name, []).append(
                    _python_module_name(dependency_path)
                )
            for name in _python_defined_exports(dependency_source):
                defined_exporters.setdefault(name, []).append(
                    _python_module_name(dependency_path)
                )
        except SyntaxError:
            continue

    misplaced_symbols = {}
    for error in errors:
        match = re.fullmatch(r"(.+?\.py) 未导出符号 (\w+)，请使用其真实接口", error)
        if not match:
            continue
        source_module = _python_module_name(match.group(1))
        symbol = match.group(2)
        candidates = defined_exporters.get(symbol) or exported_symbols.get(symbol, [])
        if len(candidates) == 1 and candidates[0] != source_module:
            misplaced_symbols[(source_module, symbol)] = candidates[0]

    if misplaced_symbols:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            tree = None
        if tree is not None:
            changed = False
            body = []
            for node in tree.body:
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    body.append(node)
                    continue
                source_module = node.module.lstrip(".")
                retained_aliases = []
                relocated = []
                for alias in node.names:
                    target_module = misplaced_symbols.get((source_module, alias.name))
                    if target_module:
                        relocated.append((target_module, alias))
                        changed = True
                    else:
                        retained_aliases.append(alias)
                if retained_aliases:
                    node.names = retained_aliases
                    body.append(node)
                body.extend(
                    ast.ImportFrom(module=target_module, names=[alias], level=0)
                    for target_module, alias in relocated
                )
            if changed:
                tree.body = body
                ast.fix_missing_locations(tree)
                content = ast.unparse(tree) + "\n"

    missing_names = {
        match.group(1)
        for error in errors
        if (match := re.fullmatch(r"名称 (\w+) 在模块全局作用域中未定义或导入", error))
    }
    imports = []
    for name in sorted(missing_names):
        defining_exporters = defined_exporters.get(name, [])
        exporters = exported_symbols.get(name, [])
        if len(defining_exporters) == 1:
            exporters = defining_exporters
        if len(exporters) == 1:
            statement = f"from {exporters[0]} import {name}"
            if statement not in content:
                imports.append(statement)
    if not imports:
        return content
    return "\n".join(imports) + "\n" + content.lstrip("\n")


def _validate_python_implementation(content: str, file_path: str) -> list[str]:
    """Reject syntactically valid Python placeholders that contain no implementation."""
    if not file_path.endswith('.py') or file_path.endswith('__init__.py'):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    substantive_nodes = [
        node for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
        and not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    if substantive_nodes:
        return []
    return ["Python 文件仅包含导入或说明文本，缺少可执行实现"]


def _validate_python_test_structure(content: str, file_path: str) -> list[str]:
    """Reject Python test modules that pytest cannot collect or configure."""
    if not file_path.endswith(".py") or "test" not in Path(file_path).name.lower():
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    errors = []
    top_level_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_") and node.name not in top_level_functions:
                errors.append(f"{file_path} 的 {node.name} 必须定义在模块顶层")
            has_monkeypatch_call = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "setattr"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "monkeypatch"
                for child in ast.walk(node)
            )
            parameter_names = {
                argument.arg
                for argument in (
                    list(node.args.posonlyargs)
                    + list(node.args.args)
                    + list(node.args.kwonlyargs)
                )
            }
            if has_monkeypatch_call and "monkeypatch" not in parameter_names:
                errors.append(f"{file_path} 使用 monkeypatch.setattr 的函数必须声明 monkeypatch fixture")

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "tmp_path"
            and isinstance(node.value, ast.Name)
            and node.value.id == "pytestconfig"
        ):
            errors.append(
                f"{file_path} 不能从 pytestconfig 获取 tmp_path，必须声明并使用 tmp_path fixture"
            )
            break
    return errors


def _validate_python_database_abstraction(
    content: str,
    file_path: str,
    architecture: dict | None = None,
) -> list[str]:
    """Prevent a database module from mixing incompatible persistence stacks."""
    if not _file_matches_role(file_path, architecture, {"database"}):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []
    imported_modules = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".", 1)[0])
    if "sqlite3" in imported_modules and "sqlalchemy" in imported_modules:
        return [f"{file_path} 同时使用 sqlite3 和 SQLAlchemy，必须统一为一种数据库抽象"]
    return []


def _file_plan_item(file_path: str, architecture: dict | None) -> dict:
    if not isinstance(architecture, dict):
        return {}
    normalized = file_path.replace("\\", "/")
    for item in architecture.get("file_plan", []):
        if isinstance(item, dict) and item.get("path", "").replace("\\", "/") == normalized:
            return item
    return {}


def _file_contract(file_path: str, architecture: dict | None) -> dict:
    contract = _file_plan_item(file_path, architecture).get("contract", {})
    return contract if isinstance(contract, dict) else {}


def _file_role(file_path: str, architecture: dict | None) -> str:
    item = _file_plan_item(file_path, architecture)
    contract = _file_contract(file_path, architecture)
    return str(contract.get("role") or item.get("file_type") or "").lower()


_ROLE_ALIASES = {
    "database": {"database", "persistence", "storage"},
    "model": {"model", "entity", "entities"},
    "schema": {"schema", "types", "dto"},
    "repository": {"repository", "crud", "dao"},
    "entry": {"entry", "api", "application"},
    "test": {"test", "tests"},
}


def _file_matches_role(
    file_path: str,
    architecture: dict | None,
    expected_roles: set[str],
) -> bool:
    """Match architecture metadata first, then infer legacy plans from paths."""
    item = _file_plan_item(file_path, architecture)
    contract = _file_contract(file_path, architecture)
    declared_roles = {
        str(item.get("file_type") or "").lower(),
        str(contract.get("role") or "").lower(),
    } - {""}
    accepted_roles = {
        alias
        for role in expected_roles
        for alias in _ROLE_ALIASES.get(role, {role})
    }
    if declared_roles:
        return bool(declared_roles & accepted_roles)

    path_lower = file_path.replace("\\", "/").lower()
    inferred_roles = set()
    if "test" in path_lower:
        inferred_roles.add("test")
    if any(token in path_lower for token in ("database", "/db", "db.py")):
        inferred_roles.add("database")
    if any(token in path_lower for token in ("model", "entit")):
        inferred_roles.add("model")
    if any(token in path_lower for token in ("schema", "dto", "types")):
        inferred_roles.add("schema")
    if any(token in path_lower for token in ("crud", "repo", "dao")):
        inferred_roles.add("repository")
    if any(token in Path(path_lower).stem for token in ("main", "app", "server", "entry")):
        inferred_roles.add("entry")
    return bool(inferred_roles & expected_roles)


def _architecture_path_for_role(
    architecture: dict | None,
    expected_role: str,
) -> str:
    file_plan = architecture.get("file_plan", []) if isinstance(architecture, dict) else []
    for item in file_plan:
        if not isinstance(item, dict):
            continue
        candidate_path = str(item.get("path", ""))
        if candidate_path and _file_matches_role(candidate_path, architecture, {expected_role}):
            return candidate_path
    return ""


def _repair_python_sqlalchemy_table_initialization(
    content: str,
    file_path: str,
    generated_contents: dict[str, str],
    architecture: dict | None,
) -> str:
    """Create SQLAlchemy tables from an entry module after models are imported."""
    if not _file_matches_role(file_path, architecture, {"entry"}):
        return content
    database_path = _architecture_path_for_role(architecture, "database")
    database_source = generated_contents.get(database_path, "")
    single_file_database = (
        not database_source
        and "sqlalchemy" in content.lower()
        and re.search(r"\bBase\s*=\s*declarative_base\s*\(\s*\)", content)
        and re.search(r"\bengine\s*=\s*create_engine\s*\(", content)
    )
    if not single_file_database and (
        not database_source or "sqlalchemy" not in database_source.lower()
    ):
        return content
    if single_file_database:
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return content
        create_all_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_all"
        ]
        if create_all_calls:
            return content
        create_tables = ast.parse("Base.metadata.create_all(bind=engine)").body[0]
        tree.body.append(create_tables)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree) + "\n"
    try:
        database_exports = _python_exports(database_source)
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content
    if not {"Base", "engine"}.issubset(database_exports):
        return content
    database_module = _python_module_name(database_path)
    create_all_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_all"
    ]
    create_tables = ast.parse("Base.metadata.create_all(bind=engine)").body[0]
    if create_all_calls:
        changed = False
        for call in create_all_calls:
            bind_keyword = next(
                (keyword for keyword in call.keywords if keyword.arg == "bind"),
                None,
            )
            if bind_keyword is None:
                call.keywords.append(ast.keyword(arg="bind", value=ast.Name(id="engine")))
                changed = True
            elif not isinstance(bind_keyword.value, ast.Name) or bind_keyword.value.id != "engine":
                bind_keyword.value = ast.Name(id="engine")
                changed = True
        imported_names = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == database_module
            for alias in node.names
        }
        missing_imports = [name for name in ("Base", "engine") if name not in imported_names]
        if missing_imports:
            tree.body.insert(
                0,
                ast.ImportFrom(
                    module=database_module,
                    names=[ast.alias(name=name) for name in missing_imports],
                    level=0,
                ),
            )
            changed = True
        has_top_level_create_all = any(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "create_all"
            for statement in tree.body
        )
        if not has_top_level_create_all:
            last_import = max(
                (
                    index
                    for index, statement in enumerate(tree.body)
                    if isinstance(statement, (ast.Import, ast.ImportFrom))
                ),
                default=-1,
            )
            tree.body.insert(last_import + 1, create_tables)
            changed = True
        if not changed:
            return content
        ast.fix_missing_locations(tree)
        return ast.unparse(tree) + "\n"

    import_node = ast.ImportFrom(
        module=database_module,
        names=[ast.alias(name="Base"), ast.alias(name="engine")],
        level=0,
    )
    insertion_index = 0
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        insertion_index = 1
    while insertion_index < len(tree.body) and isinstance(
        tree.body[insertion_index], (ast.Import, ast.ImportFrom)
    ):
        insertion_index += 1
    tree.body.insert(insertion_index, import_node)
    tree.body.insert(insertion_index + 1, create_tables)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _repair_python_test_database_fixtures(
    content: str, file_path: str, architecture: dict | None
) -> str:
    """Ensure SQLAlchemy test table fixtures run with per-test isolation."""
    normalized_name = Path(file_path).name.lower()
    is_test = (
        _file_role(file_path, architecture) == "test"
        or normalized_name.startswith("test_")
        or normalized_name.endswith("_test.py")
    )
    if not is_test or "create_all" not in content or "TestClient" not in content:
        return content
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return content

    fixture_functions = []
    setup_fixtures = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fixture_decorators = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (isinstance(target, ast.Attribute) and target.attr == "fixture") or (
                isinstance(target, ast.Name) and target.id == "fixture"
            ):
                fixture_decorators.append(decorator)
        if not fixture_decorators:
            continue
        fixture_functions.append((node, fixture_decorators))
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "create_all"
            for child in ast.walk(node)
        ):
            setup_fixtures.append(node.name)
    if not setup_fixtures:
        return content

    changed = False
    setup_fixture_names = set(setup_fixtures)
    unstable_engine_fixture = any(
        isinstance(child, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "engine"
            for target in (child.targets if isinstance(child, ast.Assign) else [child.target])
        )
        for node, _ in fixture_functions
        if node.name in setup_fixture_names
        for child in ast.walk(node)
    )
    stale_storage_fixture = any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "setattr"
        and any(
            isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
            and argument.value in {"_get_storage_path", "get_storage_path"}
            for argument in child.args
        )
        for node, _ in fixture_functions
        if node.name in setup_fixture_names
        for child in ast.walk(node)
    )

    if unstable_engine_fixture or stale_storage_fixture:
        for node, _ in fixture_functions:
            if node.name in setup_fixture_names:
                test_client_app = "app"
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "TestClient"
                        and child.args
                    ):
                        test_client_app = ast.unparse(child.args[0])
                        break
                node.body = ast.parse(
                    "Base.metadata.drop_all(bind=engine)\n"
                    "Base.metadata.create_all(bind=engine)\n"
                    f"with TestClient({test_client_app}) as test_client:\n"
                    "    yield test_client\n"
                    "Base.metadata.drop_all(bind=engine)\n"
                ).body
                changed = True
            elif any(
                isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == "client"
                and child.attr == "engine"
                for child in ast.walk(node)
            ):
                node.body = ast.parse(
                    "db = SessionLocal()\n"
                    "try:\n"
                    "    yield db\n"
                    "finally:\n"
                    "    db.close()\n"
                ).body
                changed = True

        class TestClientCallRepair(ast.NodeTransformer):
            def visit_Call(self, node: ast.Call):
                nonlocal changed
                self.generic_visit(node)
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"get", "post", "put", "patch", "delete"}
                ):
                    retained = [keyword for keyword in node.keywords if keyword.arg != "status_code"]
                    if len(retained) != len(node.keywords):
                        node.keywords = retained
                        changed = True
                return node

        tree = TestClientCallRepair().visit(tree)

    class FixtureContextRepair(ast.NodeTransformer):
        def visit_With(self, node: ast.With):
            nonlocal changed
            replacement = []
            for item in node.items:
                context = item.context_expr
                if (
                    isinstance(context, ast.Call)
                    and isinstance(context.func, ast.Name)
                    and context.func.id in setup_fixture_names
                ):
                    changed = True
                    replacement.extend(node.body)
                    break
            else:
                return self.generic_visit(node)
            return [self.visit(child) for child in replacement]

    tree = FixtureContextRepair().visit(tree)
    for node, decorators in fixture_functions:
        for decorator in decorators:
            if not isinstance(decorator, ast.Call):
                continue
            for keyword in decorator.keywords:
                if (
                    keyword.arg == "scope"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value != "function"
                ):
                    keyword.value = ast.Constant(value="function")
                    changed = True
        if node.name in setup_fixtures:
            continue
        existing_args = {argument.arg for argument in node.args.args}
        for setup_fixture in setup_fixtures:
            if setup_fixture not in existing_args:
                node.args.args.append(ast.arg(arg=setup_fixture))
                changed = True
    if not changed:
        return content
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _declared_python_framework_roots(architecture: dict | None) -> set[str]:
    """Return Python framework imports explicitly selected by the architecture."""
    if not isinstance(architecture, dict):
        return set()
    framework_values = [architecture.get("framework"), architecture.get("tech_stack")]
    project_spec = architecture.get("project_spec", {})
    if isinstance(project_spec, dict):
        framework_values.append(project_spec.get("framework"))
        for section in project_spec.values():
            if isinstance(section, dict):
                framework_values.append(section.get("framework"))
    serialized = " ".join(
        str(value).lower() for value in framework_values if value
    )
    known_frameworks = {
        "django", "falcon", "fastapi", "flask", "litestar", "sanic", "starlette",
    }
    return {framework for framework in known_frameworks if framework in serialized}


def _validate_python_contract(content: str, file_path: str, architecture: dict | None) -> list[str]:
    """Validate language-neutral architecture contracts for Python files."""
    file_plan_item = _file_plan_item(file_path, architecture)
    contract = _file_contract(file_path, architecture)
    if not contract or not file_path.endswith(".py"):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.lstrip(".").split(".", 1)[0])
    forbidden = contract.get("forbidden_imports", [])
    if isinstance(forbidden, str):
        forbidden = [forbidden]
    file_type = str(file_plan_item.get("file_type", "")).lower()
    if file_type in {"entry", "api"}:
        # Entry and API modules must be able to import the framework selected
        # by the project architecture, even if an inconsistent model-produced
        # contract also lists that framework as forbidden.
        allowed_frameworks = _declared_python_framework_roots(architecture)
        forbidden = [
            module for module in forbidden
            if str(module).split(".", 1)[0].lower() not in allowed_frameworks
        ]
    if file_type == "test" or str(contract.get("role", "")).lower() == "test":
        # Test modules need their runner and client fixtures to execute.
        allowed_test_support = {
            "json", "os", "pathlib", "sys", "tempfile", "typing",
        }
        forbidden = [
            module for module in forbidden
            if str(module).split(".", 1)[0] not in {
                "pytest", "fastapi", *allowed_test_support,
            }
        ]
    if str(contract.get("role", "")).lower() == "database":
        # The database abstraction is an implementation dependency of the
        # database module itself, even when a broad contract lists it as
        # forbidden for downstream layers.
        abstraction = str(contract.get("database_abstraction", "")).lower()
        allowed_database_modules = {
            "sqlalchemy": {"sqlalchemy"},
            "sqlite3": {"sqlite3"},
            "raw_sql": {"sqlite3"},
        }.get(abstraction, set())
        forbidden = [
            module for module in forbidden
            if str(module).split(".", 1)[0] not in allowed_database_modules
        ]
    errors = [
        f"{file_path} 违反架构契约，禁止导入模块 {module}"
        for module in forbidden
        if str(module).split(".", 1)[0] in imported_roots
    ]
    declared_exports = contract.get("exports", [])
    if isinstance(declared_exports, str):
        declared_exports = [declared_exports]
    actual_exports = _python_exports(content)
    # Tests are terminal consumers discovered by the runner, not public API
    # modules consumed by downstream generated files.
    exports_to_validate = [] if file_type == "test" else declared_exports
    for declared_export in exports_to_validate:
        if not isinstance(declared_export, str):
            continue
        match = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*", declared_export)
        if match and match.group(1) not in actual_exports:
            errors.append(
                f"{file_path} 未导出架构契约要求的公共符号 {match.group(1)}"
            )
    abstraction = str(contract.get("database_abstraction", "")).lower()
    if abstraction and abstraction not in {"unknown", "none"}:
        abstraction_markers = {
            "sqlalchemy": "sqlalchemy",
            "sqlite3": "sqlite3",
            "raw_sql": "sqlite3",
        }
        marker = abstraction_markers.get(abstraction)
        if marker and marker not in imported_roots:
            errors.append(f"{file_path} 未遵守架构契约声明的数据库抽象 {abstraction}")
    role = str(contract.get("role", "")).lower()
    if (
        "fastapi" in _declared_python_framework_roots(architecture)
        and (file_type in {"schema", "types", "dto"} or role in {"schema", "types", "dto"})
    ):
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            inherits_base_model = any(
                (isinstance(base, ast.Name) and base.id == "BaseModel")
                or (isinstance(base, ast.Attribute) and base.attr == "BaseModel")
                for base in node.bases
            )
            if not inherits_base_model:
                errors.append(
                    f"{file_path} 的 FastAPI Schema 类 {node.name} 必须继承 Pydantic BaseModel"
                )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        if function_name != "sessionmaker":
            continue
        if any(
            keyword.arg == "class_"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is None
            for keyword in node.keywords
        ):
            errors.append(f"{file_path} 的 sessionmaker 不能使用 class_=None")
    if file_type == "test" or str(contract.get("role", "")).lower() == "test":
        test_functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        if not test_functions:
            errors.append(f"{file_path} 必须声明至少一个可收集的 test_ 测试函数")
    return errors


def _repair_python_sessionmaker_class_none(content: str, file_path: str) -> str:
    """Remove SQLAlchemy's invalid explicit null session class override."""
    if not file_path.endswith(".py") or "class_" not in content:
        return content
    repaired = re.sub(r"\bclass_\s*=\s*None\s*,\s*", "", content)
    return re.sub(r",\s*class_\s*=\s*None\b", "", repaired)


def _repair_python_pydantic_base_alias(content: str, file_path: str) -> str:
    """Keep generated Pydantic schema aliases independent from ORM metadata."""
    if not file_path.endswith(".py") or "BasePydantic" not in content:
        return content
    return re.sub(
        r"^\s*BasePydantic\s*=\s*type\(\s*['\"]BasePydantic['\"]\s*,\s*\(\s*Base\s*,\s*\)\s*,\s*\)\s*$",
        "BasePydantic = BaseModel",
        content,
        flags=re.MULTILINE,
    )


def _repair_python_shared_base(
    content: str,
    file_path: str,
    generated_contents: dict[str, str],
    architecture: dict | None = None,
) -> str:
    """Normalize a model's duplicate SQLAlchemy Base to the shared database Base."""
    if not _file_matches_role(file_path, architecture, {"model"}):
        return content
    database_path = _architecture_path_for_role(architecture, "database") or "database.py"
    database_source = generated_contents.get(database_path, "")
    if "Base = declarative_base()" not in database_source:
        return content
    if "declarative_base" not in content:
        return content

    repaired = re.sub(
        r"^\s*from\s+sqlalchemy(?:\.(?:orm|ext(?:\.declarative)?))?\s+import\s+declarative_base\s*$\n?",
        "",
        content,
        flags=re.MULTILINE,
    )
    repaired = re.sub(
        r"^\s*Base\s*=\s*(?:declarative_base\(\)|[\w.]+\.declarative_base\(\))\s*$\n?",
        "",
        repaired,
        flags=re.MULTILINE,
    )
    if repaired == content:
        return content
    return f"from {_python_module_name(database_path)} import Base\n" + repaired.lstrip("\n")


def _invalid_sqlalchemy_metadata_owners(content: str, file_path: str) -> list[ast.Attribute]:
    """Find model-class metadata initialization through a nonexistent Class.Base."""
    if not file_path.endswith(".py"):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    invalid_owners = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        metadata = node.func.value
        if node.func.attr != "create_all" or not isinstance(metadata, ast.Attribute):
            continue
        owner = metadata.value
        if (
            metadata.attr == "metadata"
            and isinstance(owner, ast.Attribute)
            and owner.attr == "Base"
            and isinstance(owner.value, ast.Name)
            and owner.value.id[:1].isupper()
        ):
            invalid_owners.append(owner)
    return invalid_owners


def _validate_python_sqlalchemy_metadata_owner(content: str, file_path: str) -> list[str]:
    if not _invalid_sqlalchemy_metadata_owners(content, file_path):
        return []
    return [
        f"{file_path} 必须通过共享 Base.metadata.create_all 初始化 SQLAlchemy 元数据"
    ]


def _python_class_fields(content: str) -> dict[str, set[str]]:
    """Extract declared class fields without importing generated project code."""
    tree = ast.parse(content)
    fields = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields[node.name] = {
            target.id
            for statement in node.body
            for target in (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
                if isinstance(statement, ast.AnnAssign)
                else []
            )
            if isinstance(target, ast.Name)
        }
    return fields


def _validate_python_schema_field_access(
    content: str,
    file_path: str,
    generated_contents: dict[str, str],
) -> list[str]:
    """Reject attribute reads absent from an annotated generated Schema class."""
    if not file_path.endswith(".py"):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    schema_fields: dict[str, tuple[str, set[str]]] = {}
    for dependency_path, dependency_source in generated_contents.items():
        if not dependency_path.endswith(".py"):
            continue
        try:
            for class_name, fields in _python_class_fields(dependency_source).items():
                schema_fields.setdefault(class_name, (dependency_path, fields))
        except SyntaxError:
            continue

    allowed_methods = {
        "copy", "dict", "json", "model_copy", "model_dump", "model_dump_json",
    }
    errors = []
    seen = set()
    for function in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        parameters = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
        annotated_parameters = {}
        for parameter in parameters:
            annotation = parameter.annotation
            if isinstance(annotation, ast.Name) and annotation.id in schema_fields:
                annotated_parameters[parameter.arg] = annotation.id
        if not annotated_parameters:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            class_name = annotated_parameters.get(node.value.id)
            if not class_name or node.attr in allowed_methods:
                continue
            dependency_path, fields = schema_fields[class_name]
            if node.attr in fields:
                continue
            fingerprint = (node.value.id, class_name, node.attr)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            errors.append(
                f"{file_path} 访问 {node.value.id}.{node.attr}，但 "
                f"{dependency_path} 的 {class_name} 未定义字段 {node.attr}"
            )
    return errors


def _repair_python_sqlalchemy_metadata_owner(
    content: str,
    file_path: str,
    generated_contents: dict[str, str],
    architecture: dict | None = None,
) -> str:
    """Replace Model.Base.metadata with the database module's shared Base."""
    database_path = _architecture_path_for_role(architecture, "database") or "database.py"
    database_source = generated_contents.get(database_path, "")
    try:
        database_exports = _python_exports(database_source)
    except SyntaxError:
        return content
    invalid_owners = _invalid_sqlalchemy_metadata_owners(content, file_path)
    if "Base" not in database_exports or not invalid_owners:
        return content

    line_offsets = []
    offset = 0
    for line in content.splitlines(keepends=True):
        line_offsets.append(offset)
        offset += len(line)
    replacements = []
    for owner in invalid_owners:
        start = line_offsets[owner.lineno - 1] + owner.col_offset
        end = line_offsets[owner.end_lineno - 1] + owner.end_col_offset
        replacements.append((start, end))
    repaired = content
    for start, end in sorted(replacements, reverse=True):
        repaired = repaired[:start] + "Base" + repaired[end:]
    if "Base" not in _python_exports(repaired):
        repaired = f"from {_python_module_name(database_path)} import Base\n" + repaired.lstrip("\n")
    return repaired


def _validate_python_project_imports(
    content: str,
    file_path: str,
    generated_contents: dict[str, str],
    all_project_files: list[str],
    architecture: dict | None = None,
) -> list[str]:
    """校验 Python 项目内导入只引用已生成依赖及其真实导出。"""
    if not file_path.endswith('.py'):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return [f"Python 语法错误: {exc.msg} (line {exc.lineno})"]

    project_modules = {
        _python_module_name(path): path
        for path in all_project_files
        if path.endswith('.py') and path != file_path
    }
    project_aliases = _python_project_module_aliases(all_project_files, file_path)
    project_modules.update({alias: project_modules[module] for alias, module in project_aliases.items()})
    generated_modules = {
        _python_module_name(path): source
        for path, source in generated_contents.items()
        if path.endswith('.py')
    }
    generated_modules.update({alias: generated_modules[module] for alias, module in project_aliases.items() if module in generated_modules})
    errors = []
    imported_project_functions: dict[str, tuple[str, str]] = {}

    def allows_deferred_model_import(module: str) -> bool:
        target_path = project_modules.get(module)
        return bool(
            target_path
            and architecture
            and _file_matches_role(file_path, architecture, {"database"})
            and _file_matches_role(target_path, architecture, {"model"})
        )
    symbol_table = symtable.symtable(content, file_path, "exec")
    defined_globals = {
        symbol.get_name()
        for symbol in symbol_table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }
    referenced_globals = {
        symbol.get_name()
        for symbol in symbol_table.get_symbols()
        if symbol.is_referenced()
    }
    pending_tables = list(symbol_table.get_children())
    while pending_tables:
        child_table = pending_tables.pop()
        pending_tables.extend(child_table.get_children())
        for symbol in child_table.get_symbols():
            if symbol.is_global() and symbol.is_assigned():
                defined_globals.add(symbol.get_name())
            if symbol.is_global() and symbol.is_referenced():
                referenced_globals.add(symbol.get_name())

    runtime_globals = set(dir(builtins)) | {
        "__file__",
        "__name__",
        "__package__",
        "__spec__",
    }
    for name in sorted(referenced_globals - defined_globals - runtime_globals):
        errors.append(f"名称 {name} 在模块全局作用域中未定义或导入")

    creates_sqlalchemy_base = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "Base"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and isinstance(node.value, ast.Call)
        and (
            isinstance(node.value.func, ast.Name)
            and node.value.func.id == "declarative_base"
            or isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "declarative_base"
        )
        for node in tree.body
    )
    if creates_sqlalchemy_base:
        for module, source in generated_modules.items():
            try:
                dependency_exports = _python_exports(source)
            except SyntaxError:
                continue
            if "Base" in dependency_exports and module in project_modules:
                errors.append(
                    f"{project_modules[module]} 已导出 SQLAlchemy Base，{file_path} 必须导入复用，"
                    "禁止再次调用 declarative_base()"
                )
                break

    if _file_matches_role(file_path, architecture, {"model"}):
        database_path = _architecture_path_for_role(architecture, "database") or "database.py"
        database_source = generated_modules.get(_python_module_name(database_path))
        if database_source:
            database_uses_sqlite = bool(re.search(r"\b(?:import\s+sqlite3|from\s+sqlite3\s+import)\b", database_source))
            database_uses_sqlalchemy = "sqlalchemy" in database_source
            model_uses_sqlite = bool(re.search(r"\b(?:import\s+sqlite3|from\s+sqlite3\s+import)\b", content))
            model_uses_sqlalchemy = "sqlalchemy" in content
            if database_uses_sqlite and model_uses_sqlalchemy:
                errors.append(
                    f"{database_path} 使用原生 sqlite3 时，{file_path} 禁止混用 SQLAlchemy ORM"
                )
            elif database_uses_sqlalchemy and model_uses_sqlite:
                errors.append(
                    f"{database_path} 使用 SQLAlchemy 时，{file_path} 禁止混用原生 sqlite3"
                )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module in project_modules and module not in generated_modules:
                    if not allows_deferred_model_import(module):
                        errors.append(f"项目模块 {project_modules[module]} 尚未生成，当前拓扑层禁止导入")
                elif module not in project_modules:
                    root_module = module.split('.', 1)[0]
                    try:
                        root_available = importlib.util.find_spec(root_module) is not None
                        module_available = importlib.util.find_spec(module) is not None
                    except (ImportError, ValueError, AttributeError):
                        root_available = False
                        module_available = False
                    if not root_available:
                        errors.append(f"模块 {root_module} 不在项目文件集合中且当前运行时不可用")
                    elif not module_available:
                        errors.append(f"模块 {module} 当前运行时不可导入")
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module.lstrip('.')
            if module not in project_modules:
                root_module = module.split('.', 1)[0]
                try:
                    available = importlib.util.find_spec(root_module) is not None
                except (ImportError, ValueError, AttributeError):
                    available = False
                if not available:
                    errors.append(f"模块 {root_module} 不在项目文件集合中且当前运行时不可用")
                else:
                    try:
                        imported_module = importlib.import_module(module)
                    except Exception:
                        imported_module = None
                    if imported_module is None:
                        errors.append(f"模块 {module} 当前运行时不可导入")
                    else:
                        for alias in node.names:
                            if alias.name != "*" and not hasattr(imported_module, alias.name):
                                errors.append(
                                    f"模块 {module} 未导出符号 {alias.name}，请使用其真实接口"
                                )
                continue
            if module not in generated_modules:
                if not allows_deferred_model_import(module):
                    errors.append(f"项目模块 {project_modules[module]} 尚未生成，当前拓扑层禁止导入")
                continue
            try:
                exports = _python_exports(generated_modules[module])
            except SyntaxError:
                continue
            for alias in node.names:
                if alias.name != '*' and alias.name not in exports:
                    errors.append(
                        f"{project_modules[module]} 未导出符号 {alias.name}，请使用其真实接口"
                    )
                elif alias.name != '*':
                    imported_project_functions[alias.asname or alias.name] = (module, alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        imported_function = imported_project_functions.get(node.func.id)
        if not imported_function:
            continue
        module, exported_name = imported_function
        try:
            dependency_tree = ast.parse(generated_modules[module])
        except (SyntaxError, KeyError):
            continue
        definition = next(
            (
                candidate
                for candidate in dependency_tree.body
                if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
                and candidate.name == exported_name
            ),
            None,
        )
        if definition is None:
            continue

        positional_params = [*definition.args.posonlyargs, *definition.args.args]
        required_count = len(positional_params) - len(definition.args.defaults)
        positional_count = len(node.args)
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        supplied_names = {
            parameter.arg for parameter in positional_params[:positional_count]
        } | keyword_names
        required_names = {parameter.arg for parameter in positional_params[:required_count]}
        missing_names = sorted(required_names - supplied_names)

        if definition.args.vararg is None and positional_count > len(positional_params):
            errors.append(
                f"调用 {node.func.id} 传入 {positional_count} 个位置参数，"
                f"但 {project_modules[module]} 中定义最多接受 {len(positional_params)} 个"
            )
        if missing_names:
            errors.append(
                f"调用 {node.func.id} 缺少必需参数 {', '.join(missing_names)}，"
                f"请匹配 {project_modules[module]} 中的真实签名"
            )
        accepted_keywords = {
            parameter.arg for parameter in [*positional_params, *definition.args.kwonlyargs]
        }
        unexpected_keywords = sorted(keyword_names - accepted_keywords)
        if definition.args.kwarg is None and unexpected_keywords:
            errors.append(
                f"调用 {node.func.id} 使用了未声明参数 {', '.join(unexpected_keywords)}，"
                f"请匹配 {project_modules[module]} 中的真实签名"
            )
    return list(dict.fromkeys(errors))


def _repair_python_sync_async_calls(
    content: str,
    generated_contents: dict[str, str],
) -> str:
    """Align await usage with the actual async/sync project function definition."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    async_functions: dict[tuple[str, str], bool] = {}
    for path, source in generated_contents.items():
        if not path.endswith(".py"):
            continue
        try:
            dependency_tree = ast.parse(source, filename=path)
        except SyntaxError:
            continue
        module = _python_module_name(path)
        for node in dependency_tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                async_functions[(module, node.name)] = isinstance(node, ast.AsyncFunctionDef)

    imported_functions: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module.lstrip(".")
            for alias in node.names:
                imported_functions[alias.asname or alias.name] = (module, alias.name)

    changed = False

    class AwaitRepair(ast.NodeTransformer):
        def visit_Await(self, node: ast.Await):
            nonlocal changed
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                imported = imported_functions.get(value.func.id)
                if imported and async_functions.get(imported) is False:
                    changed = True
                    return self.visit(value)
            return self.generic_visit(node)

    repaired_tree = AwaitRepair().visit(tree)
    if not changed:
        return content
    ast.fix_missing_locations(repaired_tree)
    return ast.unparse(repaired_tree) + "\n"


def _is_edit_marker(content: str) -> bool:
    """检查工程师返回的内容是否是编辑标记（而非完整文件内容）"""
    if not content:
        return False
    try:
        data = json.loads(content.strip())
        return isinstance(data, dict) and data.get("action") == "edited"
    except (json.JSONDecodeError, ValueError):
        return False


def _git_stash_push(work_dir: str, files: list[str], message: str = "agent-backup") -> bool:
    """用 git stash 备份已 track 的文件"""
    if not files:
        return True
    try:
        result = subprocess.run(
            ['git', 'stash', 'push', '-m', message, '--', *files],
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info(f"git stash push: {len(files)} 个文件")
            return True
        logger.warning(f"git stash push 失败: {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"git stash push 异常: {e}")
        return False


def _git_stash_pop(work_dir: str) -> bool:
    """恢复最近的 git stash"""
    try:
        result = subprocess.run(
            ['git', 'stash', 'pop'],
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info("git stash pop: 恢复成功")
            return True
        logger.warning(f"git stash pop 失败: {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"git stash pop 异常: {e}")
        return False


def _git_stash_drop(work_dir: str) -> bool:
    """丢弃最近的 git stash"""
    try:
        result = subprocess.run(
            ['git', 'stash', 'drop'],
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug(f"文件操作失败：{e}")
        return False


def _fix_absolute_imports(
    content: str, file_path: str, all_project_files: list[str]
) -> str:
    """修复 Python 文件中的绝对导入，转为相对导入。

    当 LLM 生成 from src.utils import greet 时，自动转为 from .utils import greet。
    仅处理 Python 文件，且仅当目标模块在同包内存在时才转换。
    """
    if not file_path.endswith('.py'):
        return content

    # 当前文件的包路径
    parts = file_path.replace('\\', '/').split('/')
    if len(parts) < 2:
        root_modules = {
            Path(project_file).stem
            for project_file in all_project_files
            if '/' not in project_file.replace('\\', '/') and project_file.endswith('.py')
        }
        def normalize_root_from_dot_import(match: re.Match) -> str:
            imported_names = match.group(2)
            module_names = [
                name.strip().split(" as ", 1)[0]
                for name in imported_names.split(",")
            ]
            if module_names and all(name in root_modules for name in module_names):
                return f"{match.group(1)}import {imported_names}"
            return match.group(0)

        content = re.sub(
            r'^(\s*)from\s+\.\s+import\s+([A-Za-z_]\w*(?:\s+as\s+[A-Za-z_]\w*)?(?:\s*,\s*[A-Za-z_]\w*(?:\s+as\s+[A-Za-z_]\w*)?)*)$',
            normalize_root_from_dot_import,
            content,
            flags=re.MULTILINE,
        )
        content = re.sub(
            r'^(\s*from\s+)\.([A-Za-z_]\w*)(\s+import\s+)',
            lambda match: (
                f"{match.group(1)}{match.group(2)}{match.group(3)}"
                if match.group(2) in root_modules
                else match.group(0)
            ),
            content,
            flags=re.MULTILINE,
        )
        return re.sub(
            r'^(\s*from\s+)([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)(\s+import\s+)',
            lambda match: (
                f"{match.group(1)}{match.group(2).rsplit('.', 1)[-1]}{match.group(3)}"
                if match.group(2).rsplit('.', 1)[-1] in root_modules
                else match.group(0)
            ),
            content,
            flags=re.MULTILINE,
        )
    current_pkg = '/'.join(parts[:-1])  # e.g. "src/utils"

    # 构建同包文件集合（用于判断目标模块是否在同一包内）
    same_pkg_modules = set()
    for f in all_project_files:
        if not f.endswith('.py'):
            continue
        f_norm = f.replace('\\', '/')
        f_pkg = '/'.join(f_norm.split('/')[:-1])
        if f_pkg == current_pkg:
            stem = f_norm.split('/')[-1].replace('.py', '')
            same_pkg_modules.add(stem)

    # 匹配 from src.xxx import yyy 或 from src.xxx.yyy import zzz
    # 需要找到 common prefix（如 src/ 或 app/）来识别绝对导入
    lines = content.split('\n')
    fixed_lines = []
    changed = False

    for line in lines:
        stripped = line.strip()
        # 匹配 from <prefix>.<module> import <names>
        m = re.match(r'^(from\s+)([\w.]+)(\s+import\s+.+)$', stripped)
        if m:
            prefix = m.group(1)
            module_path = m.group(2)  # e.g. "src.utils" or "app.models.user"
            suffix = m.group(3)

            # 将模块路径转为文件路径
            module_parts = module_path.split('.')

            # 尝试找到与 current_pkg 匹配的前缀，然后检查剩余部分是否在同包内
            # 例如: current_pkg = "src/utils", module_path = "src.utils.helpers"
            #   → prefix_match at "src.utils", remainder = "helpers"
            for i in range(1, len(module_parts)):
                candidate_pkg = '/'.join(module_parts[:i])
                if candidate_pkg == current_pkg:
                    target_module = module_parts[i]
                    if target_module in same_pkg_modules:
                        # 转为相对导入
                        new_import = f"{prefix}.{target_module}{suffix}"
                        fixed_lines.append(line.replace(stripped, new_import))
                        changed = True
                        break
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    if changed:
        logger.info(f"自动修复绝对导入: {file_path}")
    return '\n'.join(fixed_lines)


def _format_review_issues(issues: object) -> str:
    """把审查建议渲染成单行文本。

    `reviewer.review_code` 返回的 `issues` 可能是字符串列表，也可能是模型
    给出的结构化字典列表；直接 `'; '.join(...)` 会在字典上抛 TypeError，
    让一次审查建议变成整层生成失败。
    """
    if isinstance(issues, str):
        return issues
    if not isinstance(issues, (list, tuple)):
        return str(issues) if issues else ""
    rendered = []
    for issue in issues:
        if isinstance(issue, str):
            rendered.append(issue)
            continue
        if isinstance(issue, dict):
            summary = next(
                (
                    str(issue[key])
                    for key in ("issue", "message", "description", "detail", "text", "reason")
                    if issue.get(key)
                ),
                "",
            )
            severity = str(issue.get("severity") or issue.get("risk_level") or "").strip()
            if severity and summary:
                rendered.append(f"[{severity}] {summary}")
            elif summary:
                rendered.append(summary)
            else:
                rendered.append(json.dumps(issue, ensure_ascii=False))
            continue
        rendered.append(str(issue))
    return "; ".join(part for part in rendered if part)


