"""Deterministic entry, manifest, and README skeletons owned by language adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

README_NAMES = {"readme.md", "readme"}
MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "cargo.toml",
    "pom.xml",
}


def scaffold_for_language(
    language: str,
    file_path: str,
    file_type: str,
    architecture: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    architecture = architecture or {}
    name = Path(file_path).name.lower()
    kind = (file_type or "").lower()
    if name in README_NAMES or kind in {"docs", "readme"}:
        return scaffold_readme(architecture, language)
    if name in MANIFEST_NAMES:
        return scaffold_manifest(language, name, architecture)
    if kind == "entry":
        return scaffold_entry(language, file_path, architecture)
    if kind == "database":
        return scaffold_database(language, file_path, architecture)
    if kind == "test" or _looks_like_test_path(file_path):
        return scaffold_test(language, file_path, architecture)
    return None


def scaffold_readme(architecture: Dict[str, Any], language: str = "python") -> str:
    title = _project_title(architecture)
    lines = [f"# {title}", "", "## Files", ""]
    for item in _file_plan(architecture):
        path = item.get("path")
        if not path:
            continue
        description = item.get("description") or item.get("file_type") or ""
        lines.append(f"- `{path}`: {description}".rstrip())
    lines.extend(["", "## Run", "", _run_command(language, architecture), ""])
    if any(
        item.get("file_type") == "test" or "test" in str(item.get("path") or "").lower()
        for item in _file_plan(architecture)
    ):
        test_cmd = "pytest" if (language or "python").lower() == "python" else "see README"
        lines.extend(["", "## Test", "", test_cmd, ""])
    return "\n".join(lines)


def scaffold_manifest(language: str, name: str, architecture: Dict[str, Any]) -> str:
    if name == "requirements.txt":
        return _python_requirements(architecture)
    if name == "pyproject.toml":
        return _python_pyproject(architecture)
    if name == "package.json":
        return _javascript_package_json(architecture)
    if name == "go.mod":
        return "module example.com/app\n\ngo 1.22\n"
    if name == "cargo.toml":
        return (
            "[package]\n"
            f'name = "{_slug(architecture)}"\n'
            'version = "0.1.0"\n'
            'edition = "2021"\n'
        )
    if name == "pom.xml":
        return _java_pom(architecture)
    return ""


def scaffold_entry(language: str, file_path: str, architecture: Dict[str, Any]) -> Optional[str]:
    lang = (language or "python").lower()
    framework = _framework(architecture).lower()
    if lang == "python":
        if "flask" in framework or "fastapi" in framework:
            return _python_entry(file_path, architecture)
        return None
    if lang in {"javascript", "typescript"}:
        if "express" in framework:
            return _javascript_entry(architecture)
        return None
    return None


def scaffold_database(language: str, file_path: str, architecture: Dict[str, Any]) -> Optional[str]:
    if (language or "python").lower() != "python":
        return None
    backend = _storage_backend(architecture)
    storage_type = _storage_type(architecture).lower()
    if backend in {"sqlite", "postgresql", "postgres"}:
        backend = "sqlalchemy"
    if not backend and storage_type in {"sqlite", "postgresql", "postgres"}:
        backend = "sqlalchemy"
    if backend != "sqlalchemy":
        return None
    dialect = storage_type or "sqlite"
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    storage = default.get("storage") if isinstance(default, dict) else {}
    filename = "app.db"
    if isinstance(storage, dict) and storage.get("filename"):
        filename = str(storage["filename"])
    if dialect in {"postgresql", "postgres"}:
        url = "postgresql://localhost/app"
        connect = ""
    else:
        url = f"sqlite:///./{filename}"
        connect = ', connect_args={"check_same_thread": False}'
    return (
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import sessionmaker, declarative_base\n"
        "\n"
        f'SQLALCHEMY_DATABASE_URL = "{url}"\n'
        f"engine = create_engine(SQLALCHEMY_DATABASE_URL{connect})\n"
        "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n"
        "Base = declarative_base()\n"
        "\n"
        "def get_db():\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        yield db\n"
        "    finally:\n"
        "        db.close()\n"
    )


def _file_plan(architecture: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = architecture.get("file_plan") or []
    return [item for item in plan if isinstance(item, dict)]


def _project_title(architecture: Dict[str, Any]) -> str:
    requirement = str(architecture.get("requirement") or architecture.get("project_name") or "").strip()
    if requirement:
        return requirement.splitlines()[0][:80]
    return "Generated Project"


def _slug(architecture: Dict[str, Any]) -> str:
    title = _project_title(architecture).lower()
    chars = [ch if ch.isalnum() else "-" for ch in title]
    slug = "".join(chars).strip("-") or "app"
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:40]


def _framework(architecture: Dict[str, Any]) -> str:
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    if isinstance(default, dict) and default.get("framework"):
        return str(default["framework"])
    return str(architecture.get("framework") or "")


def _storage_type(architecture: Dict[str, Any]) -> str:
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    storage = default.get("storage") if isinstance(default, dict) else {}
    if isinstance(storage, dict):
        return str(storage.get("type") or "")
    return ""


def _storage_backend(architecture: Dict[str, Any]) -> str:
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    storage = default.get("storage") if isinstance(default, dict) else {}
    table = architecture.get("symbol_table") if isinstance(architecture.get("symbol_table"), dict) else {}
    table_storage = table.get("storage") if isinstance(table.get("storage"), dict) else {}
    if isinstance(storage, dict) and storage.get("backend"):
        return str(storage.get("backend") or "").lower()
    return str(table_storage.get("backend") or "").lower()


def _auth_scheme(architecture: Dict[str, Any]) -> str:
    spec = architecture.get("project_spec") or {}
    default = spec.get("default") if isinstance(spec, dict) else {}
    auth = default.get("auth") if isinstance(default, dict) else {}
    table = architecture.get("symbol_table") if isinstance(architecture.get("symbol_table"), dict) else {}
    table_auth = table.get("auth") if isinstance(table.get("auth"), dict) else {}
    if isinstance(auth, dict) and auth.get("scheme"):
        return str(auth.get("scheme") or "").lower()
    return str(table_auth.get("scheme") or "").lower()


def _run_command(language: str, architecture: Dict[str, Any]) -> str:
    lang = (language or "python").lower()
    if lang == "python":
        entry = next((item.get("path") for item in _file_plan(architecture) if item.get("file_type") == "entry"), "main.py")
        return f"python {entry or 'main.py'}"
    if lang in {"javascript", "typescript"}:
        return "npm start"
    if lang == "go":
        return "go run ."
    if lang == "java":
        return "mvn spring-boot:run"
    if lang == "rust":
        return "cargo run"
    return "see README"


def _python_requirements(architecture: Dict[str, Any]) -> str:
    framework = _framework(architecture).lower()
    packages: List[str] = []
    if "flask" in framework:
        packages.append("flask")
    elif "fastapi" in framework or "uvicorn" in framework:
        packages.extend(["fastapi", "uvicorn"])
    storage_type = _storage_type(architecture)
    storage_backend = _storage_backend(architecture)
    if storage_backend == "sqlalchemy" or storage_type in {"sqlite", "postgresql", "postgres"}:
        packages.append("sqlalchemy")
    if "jwt" in _auth_scheme(architecture):
        packages.extend(["python-jose[cryptography]", "passlib[bcrypt]", "bcrypt"])
    if any(
        item.get("file_type") == "test" or "test" in str(item.get("path") or "").lower()
        for item in _file_plan(architecture)
    ):
        packages.append("pytest")
        if "fastapi" in framework:
            packages.append("httpx")
    unique: List[str] = []
    for package in packages:
        if package not in unique:
            unique.append(package)
    return "\n".join(unique) + ("\n" if unique else "")


def _python_pyproject(architecture: Dict[str, Any]) -> str:
    deps = ", ".join(
        f'"{line}"' for line in _python_requirements(architecture).splitlines() if line.strip()
    )
    return (
        "[project]\n"
        f'name = "{_slug(architecture)}"\n'
        'version = "0.1.0"\n'
        f"dependencies = [{deps}]\n"
    )


def _javascript_package_json(architecture: Dict[str, Any]) -> str:
    entry = next(
        (item.get("path") for item in _file_plan(architecture) if item.get("file_type") == "entry"),
        "src/index.js",
    )
    framework = _framework(architecture).lower()
    dependency_lines = []
    if "express" in framework:
        dependency_lines.append('    "express": "^4.19.2"')
    dependencies = ",\n".join(dependency_lines)
    return (
        "{\n"
        f'  "name": "{_slug(architecture)}",\n'
        '  "version": "1.0.0",\n'
        f'  "main": "{entry or "src/index.js"}",\n'
        '  "scripts": {\n'
        '    "start": "node src/index.js"\n'
        "  },\n"
        '  "dependencies": {\n'
        f"{dependencies}\n"
        "  }\n"
        "}\n"
    )


def _java_pom(architecture: Dict[str, Any]) -> str:
    artifact = _slug(architecture)
    return f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>{artifact}</artifactId>
  <version>0.1.0</version>
  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
  </properties>
</project>
"""


def _python_module(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _api_modules(architecture: Dict[str, Any]) -> Iterable[str]:
    for item in _file_plan(architecture):
        path = str(item.get("path") or "")
        if item.get("file_type") in {"api", "router", "routes", "controller"} or "/controllers/" in f"/{path}":
            if path.endswith(".py"):
                yield path


def _python_entry(file_path: str, architecture: Dict[str, Any]) -> str:
    framework = _framework(architecture).lower()
    api_modules = list(_api_modules(architecture))
    if "flask" in framework:
        lines = ["from flask import Flask, jsonify", "", "app = Flask(__name__)", ""]
        for path in api_modules:
            module = _python_module(path)
            alias = Path(path).stem + "_router"
            lines.append(f"from {module} import router as {alias}")
            lines.append(f"app.register_blueprint({alias})")
        lines.extend(
            [
                "",
                "@app.get(\"/health\")",
                "def health():",
                "    return jsonify({\"status\": \"ok\"})",
                "",
                'if __name__ == "__main__":',
                "    app.run(host=\"0.0.0.0\", port=8000)",
                "",
            ]
        )
        return "\n".join(lines)
    if "fastapi" in framework:
        lines = ["from fastapi import FastAPI", "", "app = FastAPI()", ""]
        for path in api_modules:
            module = _python_module(path)
            alias = Path(path).stem + "_router"
            lines.append(f"from {module} import router as {alias}")
            lines.append(f"app.include_router({alias})")
        lines.extend(
            [
                "",
                "@app.get(\"/health\")",
                "def health():",
                "    return {\"status\": \"ok\"}",
                "",
                'if __name__ == "__main__":',
                "    import uvicorn",
                "    uvicorn.run(app, host=\"0.0.0.0\", port=8000)",
                "",
            ]
        )
        return "\n".join(lines)
    return (
        '"""Application entry."""\n'
        "\n"
        "def main() -> None:\n"
        "    pass\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


def _javascript_entry(architecture: Dict[str, Any]) -> str:
    return (
        "const express = require('express');\n"
        "const app = express();\n"
        "app.use(express.json());\n"
        "app.get('/health', (_req, res) => res.json({ status: 'ok' }));\n"
        "app.listen(3000);\n"
    )


def _go_entry() -> str:
    return (
        "package main\n"
        "\n"
        "import (\n"
        "\t\"fmt\"\n"
        "\t\"net/http\"\n"
        ")\n"
        "\n"
        "func main() {\n"
        "\thttp.HandleFunc(\"/health\", func(w http.ResponseWriter, r *http.Request) {\n"
        "\t\tfmt.Fprint(w, `{\"status\":\"ok\"}`)\n"
        "\t})\n"
        "\thttp.ListenAndServe(\":8080\", nil)\n"
        "}\n"
    )


def _java_entry(file_path: str) -> str:
    package_parts = list(Path(file_path).parent.parts)
    class_name = Path(file_path).stem
    package_line = ""
    if "java" in package_parts:
        idx = package_parts.index("java")
        package = ".".join(package_parts[idx + 1 :])
        if package:
            package_line = f"package {package};\n\n"
    return (
        package_line
        + f"public class {class_name} {{\n"
        + "    public static void main(String[] args) {\n"
        + "    }\n"
        + "}\n"
    )


TICKET_TEST_ROUTES = (
    "POST /register",
    "POST /login",
    "POST /tickets",
    "GET /tickets",
    "GET /tickets/{ticket_id}",
    "POST /tickets/{ticket_id}/assign",
    "POST /tickets/{ticket_id}/transition",
    "POST /tickets/{ticket_id}/close",
)


def scaffold_test(language: str, file_path: str, architecture: Dict[str, Any]) -> Optional[str]:
    if (language or "python").lower() != "python":
        return None
    routes = _frozen_routes(architecture, file_path)
    if not routes and architecture.get("used_compact_eight_file_plan"):
        if Path(file_path).name.lower() == "test_app.py":
            routes = list(TICKET_TEST_ROUTES)
    if not routes or not _looks_like_ticket_routes(routes):
        return None
    return _python_ticket_tests()


def _looks_like_test_path(file_path: str) -> bool:
    lower = (file_path or "").replace("\\", "/").lower()
    name = Path(lower).name
    return "/tests/" in f"/{lower}" or name.startswith("test_") or name.endswith("_test.py")


def _frozen_routes(architecture: Dict[str, Any], file_path: str) -> List[str]:
    normalized = (file_path or "").replace("\\", "/")
    table = architecture.get("symbol_table") if isinstance(architecture.get("symbol_table"), dict) else {}
    files = table.get("files") if isinstance(table.get("files"), dict) else {}
    entry = files.get(normalized) if isinstance(files.get(normalized), dict) else {}
    routes = entry.get("routes") if isinstance(entry, dict) else None
    if routes:
        return [str(item) for item in routes if item]
    for item in _file_plan(architecture):
        if str(item.get("path") or "").replace("\\", "/") != normalized:
            continue
        contract = item.get("contract") if isinstance(item.get("contract"), dict) else {}
        planned = contract.get("routes") if isinstance(contract, dict) else None
        if planned:
            return [str(route) for route in planned if route]
    return []


def _looks_like_ticket_routes(routes: Iterable[str]) -> bool:
    text = " ".join(str(item) for item in routes).lower()
    return "/tickets" in text and "/register" in text


def _python_ticket_tests() -> str:
    return '''"""Frozen route tests for the ticket service."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(email: str, password: str, is_admin: bool = False) -> str:
    client.post("/register", json={"email": email, "password": password, "is_admin": is_admin})
    response = client.post("/login", json={"email": email, "password": password})
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return str(payload.get("access_token") or payload.get("token") or "")


def _ticket_id(payload: dict):
    return payload.get("id") or payload.get("ticket_id")


def test_auth_failure():
    denied = client.post("/login", json={"email": "missing@example.com", "password": "wrong"})
    assert denied.status_code in {400, 401, 403, 404}
    anonymous = client.get("/tickets")
    assert anonymous.status_code in {401, 403}


def test_unauthorized_access():
    admin_token = _register_and_login("admin@example.com", "secret", is_admin=True)
    user_token = _register_and_login("user@example.com", "secret", is_admin=False)
    created = client.post(
        "/tickets",
        json={"title": "need help", "description": "broken login"},
        headers=_auth_header(admin_token),
    )
    assert created.status_code in {200, 201}
    ticket_id = _ticket_id(created.json())
    assigned = client.post(
        f"/tickets/{ticket_id}/assign",
        json={"assignee_id": 2},
        headers=_auth_header(user_token),
    )
    assert assigned.status_code in {401, 403}


def test_illegal_state_transition():
    admin_token = _register_and_login("admin-flow@example.com", "secret", is_admin=True)
    created = client.post(
        "/tickets",
        json={"title": "illegal jump", "description": "skip states"},
        headers=_auth_header(admin_token),
    )
    ticket_id = _ticket_id(created.json())
    jumped = client.post(
        f"/tickets/{ticket_id}/transition",
        json={"new_status": "closed"},
        headers=_auth_header(admin_token),
    )
    assert jumped.status_code in {400, 409, 422}


def test_close_ticket():
    admin_token = _register_and_login("admin-close@example.com", "secret", is_admin=True)
    headers = _auth_header(admin_token)
    created = client.post(
        "/tickets",
        json={"title": "legal close", "description": "follow the machine"},
        headers=headers,
    )
    ticket_id = _ticket_id(created.json())
    progressing = client.post(
        f"/tickets/{ticket_id}/transition",
        json={"new_status": "in_progress"},
        headers=headers,
    )
    assert progressing.status_code in {200, 204}
    resolved = client.post(
        f"/tickets/{ticket_id}/transition",
        json={"new_status": "resolved"},
        headers=headers,
    )
    assert resolved.status_code in {200, 204}
    closed = client.post(f"/tickets/{ticket_id}/close", json={}, headers=headers)
    assert closed.status_code in {200, 204}
'''
