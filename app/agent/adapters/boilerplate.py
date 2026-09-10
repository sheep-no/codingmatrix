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


def scaffold_entry(language: str, file_path: str, architecture: Dict[str, Any]) -> str:
    lang = (language or "python").lower()
    if lang == "python":
        return _python_entry(file_path, architecture)
    if lang in {"javascript", "typescript"}:
        return _javascript_entry(architecture)
    if lang == "go":
        return _go_entry()
    if lang == "java":
        return _java_entry(file_path)
    if lang == "rust":
        return "fn main() {}\n"
    return ""


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
    if _storage_type(architecture) == "sqlite":
        packages.append("sqlalchemy")
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
    return (
        "{\n"
        f'  "name": "{_slug(architecture)}",\n'
        '  "version": "1.0.0",\n'
        f'  "main": "{entry or "src/index.js"}",\n'
        '  "scripts": {\n'
        '    "start": "node src/index.js"\n'
        "  },\n"
        '  "dependencies": {\n'
        '    "express": "^4.19.2"\n'
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
