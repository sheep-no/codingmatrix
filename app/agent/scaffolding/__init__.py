"""Official scaffold execution and immutable plan import."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.adapters import LanguageAdapterRegistry
from app.agent.dependency_manifest import DependencyKind, DependencyManifest
from app.agent.generation_plan import GenerationPlan
from app.agent.interface_registry import InterfaceRegistry
from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner


_IGNORED_PARTS = frozenset({
    ".git", ".idea", ".monkeycode", ".next", ".venv", "__pycache__",
    "build", "coverage", "dist", "node_modules", "target", "venv",
})
_MANIFEST_NAMES = frozenset({
    "Cargo.lock", "Cargo.toml", "go.mod", "go.sum", "package-lock.json",
    "package.json", "pom.xml", "pyproject.toml", "requirements.txt",
    "tsconfig.json",
})
_TEXT_ASSET_EXTENSIONS = frozenset({
    ".css", ".graphql", ".gql", ".html", ".md", ".scss", ".svg",
    ".txt", ".yaml", ".yml",
})
_TEXT_FILE_NAMES = frozenset({".dockerignore", ".gitignore", "Dockerfile"})


class ScaffoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    framework: str = Field(min_length=1)
    language: str = Field(min_length=1)
    target_dir: str = Field(min_length=1)
    command: Tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "ScaffoldRequest":
        normalized = _normalize_relative_path(self.target_dir)
        if normalized != self.target_dir:
            raise ValueError("scaffold target_dir must be a normalized relative path")
        return self

    def as_command_spec(self) -> CommandSpec:
        return CommandSpec(action=ToolchainAction.INSTALL, command=self.command)


def official_scaffold_request(language: str, framework: str, target_dir: str) -> ScaffoldRequest:
    """Return a known CLI invocation for supported framework baselines."""
    target_dir = _normalize_relative_path(target_dir)
    key = (language.lower(), framework.lower())
    commands = {
        ("typescript", "express"): ("npx", "--yes", "express-generator@4.16.1", target_dir, "--no-view"),
        ("javascript", "express"): ("npx", "--yes", "express-generator@4.16.1", target_dir, "--no-view"),
        ("typescript", "nestjs"): (
            "npx", "--yes", "@nestjs/cli@11.0.10", "new", target_dir,
            "--package-manager", "npm", "--skip-git", "--skip-install",
        ),
        ("typescript", "react-vite"): (
            "npm", "create", "vite@6.1.0", target_dir, "--", "--template", "react-ts",
        ),
    }
    command = commands.get(key)
    if command is None:
        raise LookupError(f"official scaffold not found: {language}/{framework}")
    return ScaffoldRequest(
        framework=framework,
        language=language,
        target_dir=target_dir,
        command=command,
    )


def supports_official_scaffold(language: str, framework: str) -> bool:
    """Return whether a fixed, reviewed scaffold command is registered."""
    try:
        official_scaffold_request(language, framework, "project")
    except LookupError:
        return False
    return True


async def execute_official_scaffold(
    workspace: Path,
    request: ScaffoldRequest,
    *,
    runner: ToolchainRunner | None = None,
) -> GenerationPlan:
    """Execute a known scaffold and import its files into a frozen plan."""
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("scaffold workspace must be an existing directory")
    target = _resolve_inside(workspace, request.target_dir)
    if target.exists() and any(target.iterdir()):
        raise ValueError("scaffold target directory must be absent or empty")
    returncode, stdout, stderr = await (runner or ToolchainRunner()).run(
        request.as_command_spec(), workspace
    )
    if returncode != 0:
        diagnostic = (stderr or stdout)[-4000:]
        raise RuntimeError(f"official scaffold failed with exit code {returncode}: {diagnostic}")
    if not target.is_dir():
        raise RuntimeError("official scaffold completed without creating target directory")
    return import_scaffold_plan(
        target, language=request.language, framework=request.framework
    )


def import_scaffold_plan(
    project_dir: Path,
    *,
    language: str,
    framework: str,
    max_files: int = 500,
    max_file_bytes: int = 1_000_000,
) -> GenerationPlan:
    """Parse scaffold files, imports, symbols, and manifests into a plan."""
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        raise ValueError("scaffold project directory must exist")
    if max_files < 1 or max_file_bytes < 1:
        raise ValueError("scaffold import limits must be positive")

    source_language = "javascript" if language.lower() in {"js", "javascript", "typescript"} else language.lower()
    adapter = LanguageAdapterRegistry.get_adapter(source_language)
    if adapter is None:
        raise LookupError(f"language adapter not found: {language}")

    contents: dict[str, str] = {}
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(project_dir)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.stat().st_size > max_file_bytes:
            raise ValueError(f"scaffold file exceeds size limit: {relative.as_posix()}")
        is_extensionless_text = not path.suffix and not path.name.startswith(".")
        if (
            path.suffix not in adapter.extensions
            and path.suffix not in _TEXT_ASSET_EXTENSIONS
            and path.name not in _MANIFEST_NAMES
            and path.name not in _TEXT_FILE_NAMES
            and not is_extensionless_text
        ):
            continue
        try:
            contents[relative.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"scaffold file is not UTF-8: {relative.as_posix()}") from exc
        if len(contents) > max_files:
            raise ValueError("scaffold contains too many importable files")
    if not contents:
        raise ValueError("scaffold contains no importable files")

    definitions: dict[str, Mapping[str, object]] = {}
    symbol_counts: Counter[str] = Counter()
    parsed_imports = {}
    for path, content in contents.items():
        if Path(path).suffix not in adapter.extensions:
            continue
        imports = tuple(adapter.parse_imports(content, path))
        parsed_imports[path] = imports
        symbols = adapter.extract_definitions(content)
        definitions[path] = symbols
        symbol_counts.update(
            symbol.name for symbol in symbols.values() if symbol.is_exported
        )

    paths = set(contents)
    files = []
    for path in sorted(paths):
        imports = parsed_imports.get(path, ())
        dependencies = set()
        for import_info in imports:
            for candidate in adapter.resolve_import_to_file(import_info, path):
                normalized = candidate.replace("\\", "/").removeprefix("./")
                if normalized in paths and normalized != path:
                    dependencies.add(normalized)
                    break
        file_type = adapter.infer_file_type(path)
        if Path(path).suffix not in adapter.extensions:
            file_type = "config"
        files.append({
            "path": path,
            "role": file_type,
            "language": language,
            "file_type": file_type,
            "dependencies": tuple(sorted(dependencies)),
            "imports": tuple(item.module for item in imports),
        })

    interface_entries = []
    for path, symbols in definitions.items():
        unique_symbols = []
        for symbol in symbols.values():
            if symbol.is_exported and symbol_counts[symbol.name] == 1:
                unique_symbols.append({"name": symbol.name})
        if unique_symbols:
            interface_entries.append({
                "module": _module_name(path), "owner": path,
                "symbols": unique_symbols,
            })

    return GenerationPlan.build(
        files,
        language=language,
        framework=framework,
        requested_paths=paths,
        policy="strict",
        interfaces=InterfaceRegistry.build(interface_entries),
        dependencies=_read_dependency_manifest(project_dir),
    )


def _read_dependency_manifest(project_dir: Path) -> DependencyManifest:
    entries: dict[str, dict[str, str]] = {}

    package_json = project_dir / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid scaffold package.json") from exc
        if not isinstance(package, Mapping):
            raise ValueError("scaffold package.json must contain an object")
        for section, kind in (("dependencies", DependencyKind.RUNTIME), ("devDependencies", DependencyKind.TEST)):
            values = package.get(section, {})
            if isinstance(values, Mapping):
                for name, version in values.items():
                    entries[str(name)] = {
                        "name": str(name), "version": str(version),
                        "kind": kind.value, "source": "scaffold",
                    }

    requirements = project_dir / "requirements.txt"
    if requirements.is_file():
        for raw_line in requirements.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(("-", "http://", "https://")):
                continue
            match = re.match(r"([A-Za-z0-9_.-]+)\s*([<>=!~].*)?$", line)
            if match:
                name, version = match.group(1), match.group(2) or ""
                entries[name] = {
                    "name": name, "version": version,
                    "kind": DependencyKind.RUNTIME.value, "source": "scaffold",
                }

    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as stream:
                payload = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError("invalid scaffold pyproject.toml") from exc
        project = payload.get("project", {})
        raw_dependencies = project.get("dependencies", ()) if isinstance(project, Mapping) else ()
        for raw_dependency in raw_dependencies if isinstance(raw_dependencies, list) else ():
            match = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)$", str(raw_dependency))
            if match:
                name, version = match.groups()
                entries[name] = {
                    "name": name, "version": version,
                    "kind": DependencyKind.RUNTIME.value, "source": "scaffold",
                }

    cargo = project_dir / "Cargo.toml"
    if cargo.is_file():
        try:
            with cargo.open("rb") as stream:
                payload = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError("invalid scaffold Cargo.toml") from exc
        for section, kind in (("dependencies", DependencyKind.RUNTIME), ("dev-dependencies", DependencyKind.TEST)):
            values = payload.get(section, {})
            if isinstance(values, Mapping):
                for name, value in values.items():
                    version = value if isinstance(value, str) else value.get("version", "") if isinstance(value, Mapping) else ""
                    entries[str(name)] = {
                        "name": str(name), "version": str(version),
                        "kind": kind.value, "source": "scaffold",
                    }

    go_mod = project_dir / "go.mod"
    if go_mod.is_file():
        for raw_line in go_mod.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip().removeprefix("require ").strip()
            parts = line.split()
            if len(parts) >= 2 and "." in parts[0] and parts[1].startswith("v"):
                name, version = parts[:2]
                entries[name] = {
                    "name": name, "version": version,
                    "kind": DependencyKind.RUNTIME.value, "source": "scaffold",
                }

    pom = project_dir / "pom.xml"
    if pom.is_file():
        try:
            root = ET.fromstring(pom.read_text(encoding="utf-8"))
        except (UnicodeError, ET.ParseError) as exc:
            raise ValueError("invalid scaffold pom.xml") from exc
        for dependency in root.findall(".//{*}dependency"):
            group = dependency.findtext("{*}groupId", default="").strip()
            artifact = dependency.findtext("{*}artifactId", default="").strip()
            version = dependency.findtext("{*}version", default="").strip()
            scope = dependency.findtext("{*}scope", default="").strip()
            if group and artifact:
                name = f"{group}:{artifact}"
                entries[name] = {
                    "name": name, "version": version,
                    "kind": DependencyKind.TEST.value if scope == "test" else DependencyKind.RUNTIME.value,
                    "source": "scaffold",
                }
    return DependencyManifest.build(entries.values())


def _normalize_relative_path(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    pure = PurePosixPath(candidate)
    if not candidate or pure.is_absolute() or candidate != pure.as_posix():
        raise ValueError("scaffold target_dir must be a normalized relative path")
    if any(part in {"", ".", ".."} or any(char.isspace() for char in part) for part in pure.parts):
        raise ValueError("scaffold target_dir contains unsafe path components")
    return pure.as_posix()


def _resolve_inside(workspace: Path, relative_path: str) -> Path:
    target = (workspace / relative_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("scaffold target must stay inside workspace") from exc
    return target


def _module_name(path: str) -> str:
    pure = PurePosixPath(path)
    parts = pure.with_suffix("").parts
    if parts and parts[-1] in {"__init__", "index", "mod"}:
        parts = parts[:-1]
    return ".".join(parts) or pure.stem


__all__ = [
    "ScaffoldRequest", "execute_official_scaffold", "import_scaffold_plan",
    "official_scaffold_request", "supports_official_scaffold",
]
