"""Built-in FastAPI, Express, Go, and Spring stack adapters."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.agent.code_synthesis_contracts import ProjectModel
from app.agent.framework_profiles import DEFAULT_PROFILES, FrameworkProfile
from app.agent.orchestration.profile_bridge import project_model_from_profile
from app.agent.profile_discovery import discover_profile

from .base import BaseStackAdapter, UnsupportedStackError


_IGNORED_DIRECTORIES = frozenset({
    ".git", ".idea", ".monkeycode", ".venv", "build", "dist",
    "node_modules", "target", "venv",
})


class FastAPIStackAdapter(BaseStackAdapter):
    stack_id = "fastapi"
    language = "python"
    framework = "fastapi"
    aliases = (("python", "fastapi"),)

    def framework_profile(self, project: ProjectModel | None = None) -> FrameworkProfile:
        _require_project_stack(project, self.aliases)
        return DEFAULT_PROFILES.require("python", "fastapi")

    def detect(self, workspace: Path) -> ProjectModel:
        _require_workspace(workspace, self.aliases)
        sources = _source_files(workspace, (".py",))
        entrypoints = tuple(
            path for path, content in sources if re.search(r"\bFastAPI\s*\(", content)
        )
        return _project_from_sources(
            self.framework_profile(), sources,
            runtime=_python_runtime(workspace),
            targets=_existing(workspace, "pyproject.toml", "requirements.txt"),
            entrypoints=entrypoints,
        )


class ExpressStackAdapter(BaseStackAdapter):
    stack_id = "express"
    language = "typescript"
    framework = "express"
    aliases = (
        ("typescript", "express"),
        ("javascript", "express"),
        ("js", "express"),
        ("ts", "express"),
    )

    def framework_profile(self, project: ProjectModel | None = None) -> FrameworkProfile:
        _require_project_stack(project, self.aliases)
        return DEFAULT_PROFILES.require("typescript", "express")

    def detect(self, workspace: Path) -> ProjectModel:
        _require_workspace(workspace, self.aliases)
        sources = _source_files(workspace, (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"))
        entrypoints: list[str] = []
        package_path = workspace / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        main = package.get("main") if isinstance(package, dict) else None
        if isinstance(main, str) and (workspace / main).is_file():
            entrypoints.append(Path(main).as_posix())
        entrypoints.extend(
            path for path, content in sources
            if re.search(r"\bexpress\s*\(", content) and path not in entrypoints
        )
        return _project_from_sources(
            self.framework_profile(), sources,
            runtime=_node_runtime(package), targets=("package.json",),
            entrypoints=tuple(entrypoints),
        )


class GoStackAdapter(BaseStackAdapter):
    stack_id = "go-stdlib"
    language = "go"
    framework = "stdlib"
    aliases = (
        ("go", "stdlib"),
        ("go", "net/http"),
        ("go", "net-http"),
    )

    def framework_profile(self, project: ProjectModel | None = None) -> FrameworkProfile:
        _require_project_stack(project, self.aliases)
        return DEFAULT_PROFILES.require("go", "stdlib")

    def detect(self, workspace: Path) -> ProjectModel:
        _require_workspace(workspace, (("go", "stdlib"),))
        sources = _source_files(workspace, (".go",))
        entrypoints = tuple(
            path for path, content in sources
            if re.search(r"(?m)^\s*package\s+main\s*$", content)
            and re.search(r"(?m)^\s*func\s+main\s*\(", content)
        )
        go_mod = (workspace / "go.mod").read_text(encoding="utf-8")
        module_match = re.search(r"(?m)^\s*module\s+(\S+)", go_mod)
        modules = (module_match.group(1),) if module_match else ()
        return _project_from_sources(
            self.framework_profile(), sources,
            runtime=_match_value(go_mod, r"(?m)^\s*go\s+(\S+)"),
            modules=modules, targets=("go.mod",), entrypoints=entrypoints,
        )


class SpringStackAdapter(BaseStackAdapter):
    stack_id = "spring"
    language = "java"
    framework = "spring-boot"
    aliases = (
        ("java", "spring-boot"),
        ("java", "spring-boot-gradle"),
    )

    def framework_profile(self, project: ProjectModel | None = None) -> FrameworkProfile:
        _require_project_stack(project, self.aliases)
        framework = project.framework if project is not None else self.framework
        return DEFAULT_PROFILES.require("java", framework)

    def detect(self, workspace: Path) -> ProjectModel:
        discovered = _require_workspace(workspace, self.aliases)
        profile = DEFAULT_PROFILES.require("java", discovered.framework)
        sources = _source_files(workspace, (".java",))
        entrypoints = tuple(
            path for path, content in sources if "@SpringBootApplication" in content
        )
        targets = _existing(workspace, "pom.xml", "build.gradle", "build.gradle.kts")
        manifest = "\n".join(
            (workspace / path).read_text(encoding="utf-8") for path in targets
        )
        modules = tuple(sorted(set(re.findall(r"<artifactId>([^<]+)</artifactId>", manifest))))
        return _project_from_sources(
            profile, sources,
            runtime=_java_runtime(manifest), modules=modules,
            targets=targets, entrypoints=entrypoints,
        )


def _require_workspace(workspace: Path, aliases: tuple[tuple[str, str], ...]):
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("stack workspace must be an existing directory")
    discovered = discover_profile(workspace)
    key = (discovered.language.lower(), discovered.framework.lower())
    normalized_aliases = {(language.lower(), framework.lower()) for language, framework in aliases}
    if key not in normalized_aliases:
        raise UnsupportedStackError(
            f"workspace stack {discovered.language}/{discovered.framework} is not supported by this adapter"
        )
    return discovered


def _require_project_stack(
    project: ProjectModel | None, aliases: tuple[tuple[str, str], ...]
) -> None:
    if project is None:
        return
    key = (project.language.lower(), project.framework.lower())
    normalized_aliases = {(language.lower(), framework.lower()) for language, framework in aliases}
    if key not in normalized_aliases:
        raise UnsupportedStackError(
            f"project stack {project.language}/{project.framework} does not match adapter"
        )


def _project_from_sources(
    profile: FrameworkProfile,
    sources: tuple[tuple[str, str], ...],
    *,
    runtime: str = "",
    modules: tuple[str, ...] = (),
    targets: tuple[str, ...] = (),
    entrypoints: tuple[str, ...] = (),
) -> ProjectModel:
    source_parents = tuple(sorted({
        str(Path(path).parent.as_posix())
        for path, _ in sources
        if Path(path).parent.as_posix() != "."
    }))
    detected_modules = modules or source_parents
    return project_model_from_profile(
        profile,
        modules=detected_modules,
        targets=targets,
        entrypoints=tuple(sorted(set(entrypoints))),
        generated_zones=source_parents,
    ).model_copy(update={"runtime": runtime})


def _source_files(
    workspace: Path, extensions: tuple[str, ...], *, limit: int = 2_000
) -> tuple[tuple[str, str], ...]:
    files = []
    for root, directories, names in os.walk(workspace, followlinks=False):
        directories[:] = sorted(
            name for name in directories if name not in _IGNORED_DIRECTORIES
        )
        root_path = Path(root)
        for name in sorted(names):
            path = root_path / name
            if (
                path.is_symlink()
                or path.suffix.lower() not in extensions
                or path.stat().st_size > 1_000_000
            ):
                continue
            relative = path.relative_to(workspace)
            files.append((relative.as_posix(), path.read_text(encoding="utf-8")))
            if len(files) >= limit:
                return tuple(files)
    return tuple(files)


def _existing(workspace: Path, *names: str) -> tuple[str, ...]:
    return tuple(name for name in names if (workspace / name).is_file())


def _python_runtime(workspace: Path) -> str:
    version_file = workspace / ".python-version"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    pyproject = workspace / "pyproject.toml"
    if pyproject.is_file():
        return _match_value(
            pyproject.read_text(encoding="utf-8"),
            r"requires-python\s*=\s*[\"']([^\"']+)",
        )
    return ""


def _node_runtime(package: object) -> str:
    if not isinstance(package, dict):
        return ""
    engines = package.get("engines")
    return str(engines.get("node", "")) if isinstance(engines, dict) else ""


def _java_runtime(manifest: str) -> str:
    patterns = (
        r"<maven\.compiler\.release>([^<]+)</maven\.compiler\.release>",
        r"<java\.version>([^<]+)</java\.version>",
        r"sourceCompatibility\s*=\s*[\"']?([^\s\"']+)",
    )
    for pattern in patterns:
        value = _match_value(manifest, pattern)
        if value:
            return value
    return ""


def _match_value(content: str, pattern: str) -> str:
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


__all__ = [
    "ExpressStackAdapter",
    "FastAPIStackAdapter",
    "GoStackAdapter",
    "SpringStackAdapter",
]
