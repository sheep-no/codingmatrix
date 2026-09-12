"""Frozen cross-file symbol table for spec-first generation."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

logger = logging.getLogger(__name__)

ROUTE_DECORATOR_RE = re.compile(
    r"@(?:app|router|api_router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
TEST_CLIENT_PATH_RE = re.compile(
    r"""(?:client|TestClient)[^.\n]{0,40}\.(?:get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]""",
    re.IGNORECASE,
)
JSON_FILE_STORE_RE = re.compile(
    r"""open\(\s*[^)]+\.json|Path\(\s*['\"][^'\"]+\.json['\"]|json\.(?:load|dump)\(""",
    re.IGNORECASE,
)
SQLITE3_IMPORT_RE = re.compile(r"(?:^|\n)\s*(?:import\s+sqlite3|from\s+sqlite3\s+import)")

IMPORT_TO_PIP = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "jose": "python-jose[cryptography]",
    "jwt": "PyJWT",
    "passlib": "passlib[bcrypt]",
    "bcrypt": "bcrypt",
    "pydantic": "pydantic",
    "httpx": "httpx",
    "pytest": "pytest",
    "starlette": "starlette",
    "psycopg2": "psycopg2-binary",
    "psycopg": "psycopg[binary]",
    "dotenv": "python-dotenv",
    "multipart": "python-multipart",
    "email_validator": "email-validator",
}

PIP_ORDER = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "python-jose[cryptography]",
    "PyJWT",
    "passlib[bcrypt]",
    "bcrypt",
    "pydantic",
    "python-multipart",
    "psycopg2-binary",
    "httpx",
    "pytest",
]

_COMPACT_TICKET_PATHS = {
    "main.py",
    "app/database.py",
    "app/models.py",
    "app/services.py",
    "app/routers.py",
    "tests/test_app.py",
}


def is_ticket_requirement(requirement: str) -> bool:
    return bool(re.search(r"ticket|工单", requirement or "", re.IGNORECASE))


def build_ticket_eight_file_symbol_table() -> Dict[str, Any]:
    """Signature-level contract for the compact 8-file ticket service."""
    service_signatures = {
        "hash_password": "def hash_password(password: str) -> str",
        "verify_password": "def verify_password(password: str, hashed: str) -> bool",
        "create_access_token": "def create_access_token(data: dict) -> str",
        "decode_access_token": "def decode_access_token(token: str) -> dict",
        "register_user": "def register_user(db, email: str, password: str, is_admin: bool = False)",
        "authenticate_user": "def authenticate_user(db, email: str, password: str)",
        "create_ticket": "def create_ticket(db, title: str, description: str, reporter_id: int)",
        "list_tickets": "def list_tickets(db, status: str | None = None)",
        "get_ticket": "def get_ticket(db, ticket_id: int)",
        "assign_ticket": "def assign_ticket(db, ticket_id: int, assignee_id: int, actor)",
        "transition_ticket": "def transition_ticket(db, ticket_id: int, new_status: str, actor)",
        "close_ticket": "def close_ticket(db, ticket_id: int, actor)",
        "log_audit": "def log_audit(db, actor_id: int, action: str, target: str)",
    }
    routes = [
        "POST /register",
        "POST /login",
        "POST /tickets",
        "GET /tickets",
        "GET /tickets/{ticket_id}",
        "POST /tickets/{ticket_id}/assign",
        "POST /tickets/{ticket_id}/transition",
        "POST /tickets/{ticket_id}/close",
    ]
    return {
        "storage": {"backend": "sqlalchemy", "dialect": "sqlite"},
        "auth": {"scheme": "jwt_hs256"},
        "route_prefix": "",
        "files": {
            "app/database.py": {
                "provides": ["Base", "engine", "SessionLocal", "get_db"],
                "requires": [],
                "signatures": {
                    "Base": "Base = declarative_base()",
                    "engine": "engine = create_engine(...)",
                    "SessionLocal": "SessionLocal = sessionmaker(...)",
                    "get_db": "def get_db()",
                },
                "routes": [],
            },
            "app/models.py": {
                "provides": ["User", "Ticket", "AuditLog", "TicketStatus"],
                "requires": ["Base"],
                "signatures": {
                    "User": "class User(Base)",
                    "Ticket": "class Ticket(Base)",
                    "AuditLog": "class AuditLog(Base)",
                    "TicketStatus": "class TicketStatus",
                },
                "routes": [],
            },
            "app/services.py": {
                "provides": list(service_signatures),
                "requires": ["User", "Ticket", "AuditLog", "TicketStatus", "get_db"],
                "signatures": service_signatures,
                "routes": [],
            },
            "app/routers.py": {
                "provides": ["router"],
                "requires": [
                    "hash_password",
                    "verify_password",
                    "create_access_token",
                    "decode_access_token",
                    "register_user",
                    "authenticate_user",
                    "create_ticket",
                    "list_tickets",
                    "get_ticket",
                    "assign_ticket",
                    "transition_ticket",
                    "close_ticket",
                ],
                "signatures": {"router": "router = APIRouter()"},
                "routes": list(routes),
            },
            "main.py": {
                "provides": ["app"],
                "requires": ["router"],
                "signatures": {"app": "app = FastAPI()"},
                "routes": [],
            },
            "tests/test_app.py": {
                "provides": [],
                "requires": ["app"],
                "signatures": {},
                "routes": list(routes),
            },
            "requirements.txt": {"provides": [], "requires": [], "signatures": {}, "routes": []},
            "README.md": {"provides": [], "requires": [], "signatures": {}, "routes": []},
        },
    }


def freeze_symbol_table(architecture: MutableMapping[str, Any]) -> Dict[str, Any]:
    """Attach a frozen symbol table to architecture and sync file_plan contracts."""
    existing = architecture.get("symbol_table")
    if _table_has_provides(existing):
        table = existing
    elif _should_use_ticket_table(architecture):
        table = build_ticket_eight_file_symbol_table()
    else:
        table = derive_symbol_table(architecture)
    architecture["symbol_table"] = table
    _sync_project_spec(architecture, table)
    _sync_file_plan_contracts(architecture, table)
    return table


def attach_to_project_context(
    project_context: MutableMapping[str, Any],
    architecture: MutableMapping[str, Any],
) -> Dict[str, Any]:
    table = freeze_symbol_table(architecture)
    project_context["architecture"] = architecture
    project_context["symbol_table"] = table
    project_context.setdefault("generated_signatures", {})
    return table


def record_generated_signature(
    project_context: MutableMapping[str, Any],
    file_path: str,
    content: str,
) -> None:
    from app.agent.signature_extractor import extract_signatures

    normalized = (file_path or "").replace("\\", "/")
    generated = project_context.setdefault("generated_signatures", {})
    excerpt = extract_signatures(normalized, content or "") or ""
    generated[normalized] = excerpt[:4000]


def remember_generated_file(
    project_context: MutableMapping[str, Any],
    file_path: str,
    content: str,
    architecture: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    record_generated_signature(project_context, file_path, content)
    arch = architecture or project_context.get("architecture") or {}
    return validate_file_against_symbol_table(file_path, content or "", arch)


def derive_symbol_table(architecture: Mapping[str, Any]) -> Dict[str, Any]:
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    storage = default.get("storage") if isinstance(default, dict) else {}
    if not isinstance(storage, dict):
        storage = {}
    auth = default.get("auth") if isinstance(default, dict) else {}
    if not isinstance(auth, dict):
        auth = {}
    backend = str(storage.get("backend") or "").lower()
    dialect = str(storage.get("type") or storage.get("dialect") or "").lower()
    if not backend and dialect in {"sqlite", "postgresql", "postgres"}:
        backend = "sqlalchemy"
    elif not backend and dialect in {"json_file", "json"}:
        backend = "json"
    files: Dict[str, Any] = {}
    for item in architecture.get("file_plan") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = str(item["path"]).replace("\\", "/")
        contract = item.get("contract") if isinstance(item.get("contract"), dict) else {}
        files[path] = {
            "provides": _as_str_list(contract.get("exports")),
            "requires": _as_str_list(contract.get("required_imports") or contract.get("shared_symbols")),
            "signatures": {},
            "routes": _as_str_list(contract.get("routes")),
        }
    return {
        "storage": {"backend": backend, "dialect": dialect},
        "auth": {"scheme": str(auth.get("scheme") or "")},
        "route_prefix": str(architecture.get("route_prefix") or ""),
        "files": files,
    }


def validate_file_against_symbol_table(
    file_path: str,
    content: str,
    architecture: Mapping[str, Any],
) -> List[str]:
    table = architecture.get("symbol_table") if isinstance(architecture.get("symbol_table"), dict) else {}
    if not table:
        return []
    normalized = (file_path or "").replace("\\", "/")
    entry = (table.get("files") or {}).get(normalized) or {}
    issues: List[str] = []
    if not content or not content.strip():
        if entry.get("provides") or entry.get("routes"):
            issues.append(f"{normalized}: empty file missing frozen contract")
        return issues

    defined = _defined_names(normalized, content, architecture)
    for name in entry.get("provides") or []:
        if name not in defined:
            issues.append(f"{normalized}: missing frozen symbol {name}")

    expected_routes = [_normalize_route(item) for item in (entry.get("routes") or [])]
    if expected_routes and not _looks_like_test(normalized):
        actual = [_normalize_route(item) for item in _extract_routes(content)]
        missing = [route for route in expected_routes if route not in actual]
        if missing:
            issues.append(f"{normalized}: missing frozen routes {', '.join(missing)}")

    if str(table.get("route_prefix") or "") == "":
        for route in list(_extract_routes(content)) + list(_extract_test_paths(content)):
            path_only = route.split(" ", 1)[-1]
            if path_only.startswith("/api/v1"):
                issues.append(f"{normalized}: uses /api/v1 but frozen route_prefix is empty")
                break

    storage = table.get("storage") if isinstance(table.get("storage"), dict) else {}
    backend = str(storage.get("backend") or "").lower()
    file_type = _file_type(normalized, architecture)
    if backend == "sqlalchemy" and file_type in {"database", "model", "service"}:
        if SQLITE3_IMPORT_RE.search(content):
            issues.append(f"{normalized}: sqlite3 import conflicts with frozen storage.backend=sqlalchemy")
        if JSON_FILE_STORE_RE.search(content):
            issues.append(f"{normalized}: JSON file storage conflicts with frozen storage.backend=sqlalchemy")

    return issues


def validate_project_against_symbol_table(
    files: Mapping[str, str],
    architecture: Mapping[str, Any],
) -> List[str]:
    issues: List[str] = []
    for path, content in files.items():
        issues.extend(validate_file_against_symbol_table(path, content or "", architecture))
    return issues


def scan_python_packages(files: Mapping[str, str]) -> List[str]:
    from app.agent.adapters.python import PythonLanguageAdapter

    adapter = PythonLanguageAdapter()
    packages: List[str] = []
    seen: set[str] = set()
    for path, content in files.items():
        if not str(path).endswith(".py") or not content:
            continue
        for info in adapter.parse_imports(content, path):
            module = (info.module or "").lstrip(".")
            if not module or info.is_relative:
                continue
            top = module.split(".")[0]
            if adapter.is_project_module(module) or top in adapter.PYTHON_BUILTINS:
                continue
            if _is_local_python_module(top, files):
                continue
            pip_name = IMPORT_TO_PIP.get(top, top)
            if pip_name not in seen:
                seen.add(pip_name)
                packages.append(pip_name)
    if any(_looks_like_test(path) for path in files):
        for name in ("pytest", "httpx"):
            if name not in seen:
                seen.add(name)
                packages.append(name)
    return _order_packages(packages)


def rewrite_manifests(
    output_dir: Path,
    architecture: Mapping[str, Any],
    files: Mapping[str, str],
    ctx: Any = None,
) -> Dict[str, str]:
    from app.agent.adapters.boilerplate import scaffold_for_language, scaffold_readme
    from app.agent.utils import write_file_atomic

    rewritten: Dict[str, str] = {}
    planned = {
        str(item.get("path") or "").replace("\\", "/")
        for item in architecture.get("file_plan") or []
        if isinstance(item, dict)
    }
    language = str(architecture.get("language") or "python").lower()
    if language == "python" or "requirements.txt" in planned:
        packages = scan_python_packages(files)
        table = architecture.get("symbol_table") if isinstance(architecture.get("symbol_table"), dict) else {}
        storage = table.get("storage") if isinstance(table.get("storage"), dict) else {}
        if str(storage.get("backend") or "") == "sqlalchemy" and "sqlalchemy" not in packages:
            packages.append("sqlalchemy")
        auth = table.get("auth") if isinstance(table.get("auth"), dict) else {}
        if "jwt" in str(auth.get("scheme") or "").lower():
            for name in ("python-jose[cryptography]", "passlib[bcrypt]", "bcrypt"):
                if name not in packages:
                    packages.append(name)
        packages = _order_packages(packages)
        content = ("\n".join(packages) + "\n") if packages else ""
        if "requirements.txt" in planned or packages:
            write_file_atomic(Path(output_dir), "requirements.txt", content, skip_placeholder_check=True)
            rewritten["requirements.txt"] = content
            if ctx is not None:
                ctx.save_file_content("requirements.txt", content, "symbol_table")
    if "README.md" in planned or "readme.md" in {p.lower() for p in planned}:
        readme = scaffold_readme(dict(architecture), language)
        write_file_atomic(Path(output_dir), "README.md", readme, skip_placeholder_check=True)
        rewritten["README.md"] = readme
        if ctx is not None:
            ctx.save_file_content("README.md", readme, "symbol_table")
    for item in architecture.get("file_plan") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        if not path:
            continue
        kind = str(item.get("file_type") or "")
        if kind != "test" and not _looks_like_test(path):
            continue
        test_content = scaffold_for_language(language, path, kind or "test", dict(architecture))
        if not test_content:
            continue
        write_file_atomic(Path(output_dir), path, test_content, skip_placeholder_check=True)
        rewritten[path] = test_content
        if ctx is not None:
            ctx.save_file_content(path, test_content, "symbol_table")
    return rewritten


def finalize_generated_project(
    output_dir: Path,
    architecture: Mapping[str, Any],
    files: Mapping[str, str],
    ctx: Any = None,
) -> List[str]:
    issues = validate_project_against_symbol_table(files, architecture)
    if issues:
        logger.warning("symbol_table gate found %s issue(s)", len(issues))
        for issue in issues[:20]:
            logger.warning("  %s", issue)
    rewrite_manifests(output_dir, architecture, files, ctx)
    return issues


def _table_has_provides(table: Any) -> bool:
    if not isinstance(table, dict):
        return False
    files = table.get("files")
    if not isinstance(files, dict) or not files:
        return False
    return any(isinstance(entry, dict) and entry.get("provides") for entry in files.values())


def _should_use_ticket_table(architecture: Mapping[str, Any]) -> bool:
    requirement = str(architecture.get("requirement") or "")
    if not is_ticket_requirement(requirement):
        return False
    if architecture.get("used_compact_eight_file_plan"):
        return True
    paths = {
        str(item.get("path") or "").replace("\\", "/")
        for item in architecture.get("file_plan") or []
        if isinstance(item, dict)
    }
    return _COMPACT_TICKET_PATHS <= paths


def _sync_project_spec(architecture: MutableMapping[str, Any], table: Mapping[str, Any]) -> None:
    spec = architecture.setdefault("project_spec", {})
    if not isinstance(spec, dict):
        return
    default = spec.setdefault("default", {})
    if not isinstance(default, dict):
        return
    storage = table.get("storage") if isinstance(table.get("storage"), dict) else {}
    if storage:
        current = default.get("storage") if isinstance(default.get("storage"), dict) else {}
        merged = dict(current)
        if storage.get("backend"):
            merged["backend"] = storage["backend"]
        dialect = storage.get("dialect")
        if dialect and not merged.get("type"):
            merged["type"] = dialect
        default["storage"] = merged
    auth = table.get("auth") if isinstance(table.get("auth"), dict) else {}
    if auth.get("scheme"):
        default["auth"] = {"scheme": auth["scheme"]}


def _sync_file_plan_contracts(architecture: MutableMapping[str, Any], table: Mapping[str, Any]) -> None:
    files = table.get("files") if isinstance(table.get("files"), dict) else {}
    for item in architecture.get("file_plan") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = str(item["path"]).replace("\\", "/")
        entry = files.get(path)
        if not isinstance(entry, dict):
            continue
        contract = dict(item.get("contract") or {}) if isinstance(item.get("contract"), dict) else {}
        provides = _as_str_list(entry.get("provides"))
        if provides:
            contract["exports"] = provides
        requires = _as_str_list(entry.get("requires"))
        if requires:
            contract["required_imports"] = requires
        routes = _as_str_list(entry.get("routes"))
        if routes:
            contract["routes"] = routes
        notes = []
        if entry.get("signatures"):
            notes.append("implement frozen signatures exactly")
        if isinstance(table.get("storage"), dict) and table["storage"].get("backend"):
            notes.append(f"storage.backend={table['storage']['backend']}")
        if isinstance(table.get("auth"), dict) and table["auth"].get("scheme"):
            notes.append(f"auth.scheme={table['auth']['scheme']}")
        if notes:
            extra = "; ".join(notes)
            existing = str(contract.get("notes") or "").strip()
            contract["notes"] = f"{existing}; {extra}" if existing else extra
        item["contract"] = contract


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if item]
    return []


def _defined_names(file_path: str, content: str, architecture: Mapping[str, Any]) -> set[str]:
    adapter = _adapter(architecture)
    names: set[str] = set()
    if adapter is not None:
        try:
            names.update(adapter.extract_definitions(content))
        except Exception:
            pass
    for match in re.finditer(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)|^(\w+)\s*=", content, re.MULTILINE):
        names.update(group for group in match.groups() if group)
    return names


def _extract_routes(content: str) -> List[str]:
    return [f"{method.upper()} {path}" for method, path in ROUTE_DECORATOR_RE.findall(content or "")]


def _extract_test_paths(content: str) -> List[str]:
    return TEST_CLIENT_PATH_RE.findall(content or "")


def _normalize_route(value: str) -> str:
    text = str(value or "").strip()
    if " " in text:
        method, path = text.split(" ", 1)
        return f"{method.upper()} {_canonical_path(path)}"
    return _canonical_path(text)


def _canonical_path(path: str) -> str:
    text = path.strip() or "/"
    if not text.startswith("/"):
        text = "/" + text
    text = re.sub(r"\{[^}]+\}", "{}", text)
    text = re.sub(r"/+$", "", text) or "/"
    return text


def _looks_like_test(path: str) -> bool:
    lower = (path or "").replace("\\", "/").lower()
    name = Path(lower).name
    return "/tests/" in f"/{lower}" or name.startswith("test_") or name.endswith("_test.py")


def _file_type(path: str, architecture: Mapping[str, Any]) -> str:
    normalized = (path or "").replace("\\", "/")
    for item in architecture.get("file_plan") or []:
        if isinstance(item, dict) and str(item.get("path") or "").replace("\\", "/") == normalized:
            return str(item.get("file_type") or "").lower()
    lower = normalized.lower()
    if "database" in lower:
        return "database"
    if "model" in lower:
        return "model"
    if "service" in lower:
        return "service"
    if "router" in lower or "controller" in lower:
        return "api"
    if _looks_like_test(normalized):
        return "test"
    if Path(normalized).name in {"main.py", "app.py"}:
        return "entry"
    return ""


def _adapter(architecture: Mapping[str, Any]):
    from app.agent.adapters import LanguageAdapterRegistry

    language = str(architecture.get("language") or "python")
    return LanguageAdapterRegistry.get_adapter(language) or LanguageAdapterRegistry.get_adapter("python")


def _order_packages(packages: Iterable[str]) -> List[str]:
    unique: List[str] = []
    for name in packages:
        if name not in unique:
            unique.append(name)
    ordered = [name for name in PIP_ORDER if name in unique]
    ordered.extend(name for name in unique if name not in ordered)
    return ordered


def _is_local_python_module(top: str, files: Mapping[str, str]) -> bool:
    if not top:
        return False
    marker = f"/{top}/"
    for path in files:
        normalized = str(path).replace("\\", "/")
        if not normalized.endswith(".py"):
            continue
        stem = Path(normalized).stem
        if stem == top:
            return True
        if normalized.startswith(f"{top}/") or marker in f"/{normalized}":
            return True
    return False
