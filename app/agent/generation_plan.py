"""Project-level immutable generation plan and its consistency gate."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dependency_manifest import DependencyManifest
from .interface_registry import InterfaceRegistry


# 计划内文件可解析出的模块名（a/b.py -> a.b；a/__init__.py -> a）
_PACKAGE_ENTRY_FILES = {
    "__init__.py", "index.js", "index.jsx", "index.ts", "index.tsx", "mod.rs", "lib.rs",
}
_SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue",
    ".go", ".rs", ".java", ".kt", ".rb", ".php",
}


class PlanFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    role: str = ""
    language: str = ""
    file_type: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    dependencies: Tuple[str, ...] = ()
    imports: Tuple[str, ...] = ()
    contract_refs: Tuple[str, ...] = ()
    contract: Mapping[str, Any] = Field(default_factory=dict)


class GenerationPlan(BaseModel):
    """The single project-level source of truth consumed by later stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    policy: str = "extensible"
    language: str = ""
    framework: str = ""
    runtime: str = ""
    requested_paths: Tuple[str, ...] = ()
    files: Tuple[PlanFile, ...] = ()
    interfaces: InterfaceRegistry = Field(default_factory=InterfaceRegistry.build)
    dependencies: DependencyManifest = Field(default_factory=DependencyManifest.build)
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_digest(self) -> "GenerationPlan":
        payload = {"version": self.version, "policy": self.policy, "language": self.language, "framework": self.framework, "runtime": self.runtime, "requested_paths": self.requested_paths, "files": [item.model_dump(mode="json") for item in self.files], "interfaces": self.interfaces.model_dump(mode="json"), "dependencies": self.dependencies.model_dump(mode="json")}
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if self.digest != expected:
            raise ValueError("generation plan digest does not match its contents")
        return self

    @classmethod
    def build(cls, files: Iterable[Mapping[str, object] | PlanFile], *, language: str = "", framework: str = "", runtime: str = "", requested_paths: Optional[Iterable[str]] = None, policy: str = "extensible", version: int = 1, interfaces: Optional[InterfaceRegistry] = None, dependencies: Optional[DependencyManifest] = None) -> "GenerationPlan":
        normalized = tuple(sorted((_coerce_file(item) for item in files), key=lambda item: item.path))
        paths = {item.path for item in normalized}
        if len(paths) != len(normalized):
            raise ValueError("generation plan file paths must be unique")
        normalized = _resolve_plan_dependencies(normalized, paths)
        missing = {dependency for item in normalized for dependency in item.dependencies if dependency not in paths}
        if missing:
            raise ValueError(f"generation plan has missing file dependencies: {sorted(missing)}")
        _assert_acyclic(normalized)
        requested = tuple(sorted({_normalize_path(path) for path in (requested_paths or ())}))
        if policy == "strict" and set(requested) != paths:
            raise ValueError("strict generation plan files must equal requested_paths")
        registry = interfaces or InterfaceRegistry.build(())
        manifest = dependencies or DependencyManifest.build(())
        payload = {"version": version, "policy": policy, "language": language, "framework": framework, "runtime": runtime, "requested_paths": requested, "files": [item.model_dump(mode="json") for item in normalized], "interfaces": registry.model_dump(mode="json"), "dependencies": manifest.model_dump(mode="json")}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return cls(version=version, policy=policy, language=language, framework=framework, runtime=runtime, requested_paths=requested, files=normalized, interfaces=registry, dependencies=manifest, digest=digest)

    @classmethod
    def from_architecture(cls, architecture: Mapping[str, object], **kwargs: object) -> "GenerationPlan":
        files = architecture.get("file_plan", ())
        if isinstance(files, str):
            files = [files]
        elif not isinstance(files, (list, tuple)):
            files = ()
        project = architecture.get("project_spec", {})
        project = project if isinstance(project, Mapping) else {}
        interface_data = architecture.get("interfaces", architecture.get("interface_registry", ()))
        dependency_data = architecture.get("dependencies", architecture.get("dependency_manifest", ()))
        if isinstance(interface_data, InterfaceRegistry):
            interfaces = interface_data
        elif isinstance(interface_data, str) or interface_data is None:
            interfaces = InterfaceRegistry.build(())
        else:
            interfaces = InterfaceRegistry.build(interface_data or ())
        if isinstance(dependency_data, DependencyManifest):
            dependencies = dependency_data
        elif isinstance(dependency_data, str) or dependency_data is None:
            dependencies = DependencyManifest.build(())
        else:
            dependencies = DependencyManifest.build(dependency_data or ())
        strict_paths = architecture.get("strict_file_paths")
        build_options = dict(kwargs)
        if strict_paths and "policy" not in build_options:
            build_options["policy"] = "strict"
            build_options["requested_paths"] = strict_paths
        return cls.build(files, language=str(project.get("language", architecture.get("language", ""))), framework=str(project.get("framework", architecture.get("framework", ""))), runtime=str(project.get("runtime", architecture.get("runtime", ""))), interfaces=interfaces, dependencies=dependencies, **build_options)

    def file_entries(self) -> Tuple[Mapping[str, object], ...]:
        """Return a compatibility projection with mutable collection fields."""
        return tuple({
            "path": item.path,
            "description": item.role,
            "language": item.language,
            "file_type": item.file_type,
            "priority": item.priority,
            "dependencies": list(item.dependencies),
            "imports": list(item.imports),
            "contract_refs": list(item.contract_refs),
            "contract": dict(item.contract),
        } for item in self.files)


def add_profile_components(
    files: Iterable[Mapping[str, object] | PlanFile],
    profile_context: Mapping[str, object],
    *,
    policy: str = "extensible",
    requested_paths: Optional[Iterable[str]] = None,
    language: str = "",
    framework: str = "",
    runtime: str = "",
) -> GenerationPlan:
    """Project domain component hints into a plan without expanding strict scopes."""
    entries = list(files)
    existing = {str(item.path if isinstance(item, PlanFile) else item.get("path", "")) for item in entries}
    if policy != "strict":
        raw_policy = profile_context.get("capability_policy", {})
        component_plan = raw_policy.get("component_file_plan", ()) if isinstance(raw_policy, Mapping) else ()
        previous = None
        for item in component_plan:
            path = str(item.get("path", ""))
            if not path or path in existing:
                continue
            component = str(item.get("component", "component"))
            entry = {"path": path, "role": component, "file_type": component, "priority": 3}
            if previous:
                entry["dependencies"] = (previous,)
            entries.append(entry)
            existing.add(path)
            previous = path
    return GenerationPlan.build(
        entries, language=language, framework=framework, runtime=runtime,
        policy=policy, requested_paths=requested_paths,
    )


def _coerce_file(item: Mapping[str, object] | PlanFile) -> PlanFile:
    if isinstance(item, PlanFile):
        return item
    if isinstance(item, str):
        item = {"path": item}
    if not isinstance(item, Mapping):
        raise ValueError("generation plan file must be an object")
    raw = item.get("dependencies", item.get("depends_on", ()))
    if isinstance(raw, str):
        raw = (raw,)
    imports = item.get("imports", ())
    if isinstance(imports, str):
        imports = (imports,)
    contract_refs = item.get("contract_refs", ())
    if isinstance(contract_refs, str):
        contract_refs = (contract_refs,)
    contract = item.get("contract", {})
    if not isinstance(contract, Mapping):
        raise ValueError("file contract must be an object")
    return PlanFile(path=_normalize_path(str(item.get("path", ""))), role=str(item.get("role", item.get("description", ""))), language=str(item.get("language", "")), file_type=str(item.get("file_type", "")), priority=_normalize_priority(item.get("priority", 3)), dependencies=tuple(_normalize_path(str(value)) for value in raw or ()), imports=tuple(str(value) for value in imports or ()), contract_refs=tuple(str(value) for value in contract_refs or ()), contract=dict(contract))


def _normalize_priority(value: object) -> int:
    """Keep model-supplied scheduling hints inside the supported range."""
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 3
    return min(max(priority, 1), 5)


def _module_key(path: str) -> str:
    """计划文件路径对应的模块名（app/models.py -> app.models）。"""
    pure = PurePosixPath(path)
    if pure.name in _PACKAGE_ENTRY_FILES:
        parts = pure.parent.parts
    elif pure.suffix.lower() in _SOURCE_SUFFIXES:
        parts = pure.with_suffix("").parts
    else:
        return ""
    return ".".join(part for part in parts if part not in ("", "."))


def _resolve_plan_dependencies(files: Tuple[PlanFile, ...], paths: set) -> Tuple[PlanFile, ...]:
    """把 file_plan 的 dependencies 规范化为计划内文件路径。

    架构师提示词允许用 imports 或 dependencies 声明依赖方向，模型常在该字段
    写入模块名（app.database）或第三方包名。契约模型只接受计划内文件路径，
    直接冻结会因「missing file dependencies」误判为计划损坏而硬失败。

    这里保留能解析到计划文件的依赖（含模块名 -> 文件路径），对确实写成文件
    路径却缺失的依赖仍保留原值，交由 missing 检查报错。
    """
    index: dict = {}
    for path in paths:
        key = _module_key(path)
        if key:
            index.setdefault(key, path)

    resolved_files = []
    changed = False
    for item in files:
        resolved = []
        for dependency in item.dependencies:
            target = _match_plan_dependency(dependency, paths, index)
            if target is not None:
                if target != item.path and target not in resolved:
                    resolved.append(target)
            elif _looks_like_source_file(dependency) and dependency not in resolved:
                # 明确写成文件路径却没有对应计划文件，保留以便报错
                resolved.append(dependency)
        if tuple(resolved) != item.dependencies:
            changed = True
        resolved_files.append(item.model_copy(update={"dependencies": tuple(resolved)}))
    return tuple(resolved_files) if changed else files


def _match_plan_dependency(dependency: str, paths: set, index: dict) -> Optional[str]:
    """返回依赖对应的计划内文件路径；无法解析时返回 None。"""
    if dependency in paths:
        return dependency
    dependency = str(dependency or "").strip()
    if not dependency:
        return None
    if "/" not in dependency and "." in dependency:
        candidate = dependency.replace(".", "/")
    else:
        candidate = dependency
    for key in (dependency, candidate):
        target = index.get(key)
        if target:
            return target
    if candidate and not PurePosixPath(candidate).suffix:
        prefix = candidate.rstrip("/") + "/"
        matches = sorted(path for path in paths if path.startswith(prefix))
        # 包目录依赖优先指向包入口文件
        for path in matches:
            if PurePosixPath(path).name in _PACKAGE_ENTRY_FILES:
                return path
        for path in matches:
            if path.startswith(prefix):
                return path
    return None


def _looks_like_source_file(dependency: str) -> bool:
    return PurePosixPath(str(dependency or "")).suffix.lower() in _SOURCE_SUFFIXES


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def _normalize_path(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    if not candidate or candidate.startswith("/") or _WINDOWS_DRIVE.match(candidate):
        raise ValueError("plan paths must be relative and non-empty")
    parts = []
    for part in candidate.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or any(char.isspace() for char in part):
            raise ValueError("plan paths cannot contain traversal or whitespace")
        parts.append(part)
    if not parts:
        raise ValueError("plan paths must identify a file")
    return PurePosixPath(*parts).as_posix()


def _assert_acyclic(files: Tuple[PlanFile, ...]) -> None:
    dependencies = {item.path: set(item.dependencies) for item in files}
    visiting = set()
    visited = set()

    def visit(path: str) -> None:
        if path in visiting:
            raise ValueError(f"generation plan contains a dependency cycle at: {path}")
        if path in visited:
            return
        visiting.add(path)
        for dependency in dependencies[path]:
            visit(dependency)
        visiting.remove(path)
        visited.add(path)

    for path in dependencies:
        visit(path)
