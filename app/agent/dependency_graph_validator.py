"""
DependencyGraphValidator - 依赖图验证器

对依赖图做确定性校验，检测：
1. 功能重复：不同路径但描述相同的文件
2. 错误路径：路径格式不合法
3. 缺失依赖：依赖指向不存在的节点
4. 文件类型错误：file_type 与扩展名不匹配
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_FILE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".rb", ".php"}

# 使 passed=False 的问题类型；这些类型必须计入 error，避免「验证失败但 0 错误」。
_BLOCKING_ISSUE_TYPES = frozenset({"invalid_path", "missing_dependency"})
# 明确属于警告的类型；其余（含 LLM 自由发挥的未知类型）一律计为 error，避免静默丢失。
_WARNING_ISSUE_TYPES = frozenset({"wrong_file_type", "same_name_file"})


@dataclass
class ValidationIssue:
    """验证问题"""
    issue_type: str  # duplicate_function, invalid_path, missing_dependency, wrong_file_type
    file_path: str
    message: str
    suggestion: str
    related_files: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0

    def __post_init__(self):
        self.warning_count = sum(
            1 for i in self.issues if i.issue_type in _WARNING_ISSUE_TYPES
        )
        self.error_count = len(self.issues) - self.warning_count


class DependencyGraphValidator:
    """依赖图验证器

    对依赖图做确定性校验（空图、非法路径、指向不存在节点的依赖）。

    Args:
        language_adapter: 语言适配器（可选）
    """

    def __init__(
        self,
        language_adapter=None,
    ):
        self._language_adapter = language_adapter

    async def validate(
        self,
        dep_graph,
        scope: str = "full",
        new_files: Optional[List[str]] = None,
        architecture: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """验证依赖图

        Args:
            dep_graph: DependencyGraph 实例
            scope: 验证范围 - "full"（全图）/ "incremental"（新增部分）/ "refactor"（重构部分）
            new_files: 新增文件列表（incremental/refactor 模式时使用）
            architecture: 架构设计（可选，用于获取 file_plan 描述）

        Returns:
            ValidationResult 验证结果
        """
        # scope/new_files 保留仅为调用方兼容：当前校验是覆盖整图的确定性检查，
        # 不再按范围调用 LLM（历史 LLM 路径已移除）。
        del scope, new_files
        return self.validate_static(dep_graph, architecture)

    def validate_static(
        self,
        dep_graph,
        architecture: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """确定性校验：空图、非法路径、指向不存在节点的依赖。"""
        issues: List[ValidationIssue] = []
        nodes = set(getattr(dep_graph, "nodes", {}) or {})
        if not nodes:
            issues.append(ValidationIssue(
                issue_type="invalid_path",
                file_path="",
                message="依赖图为空",
                suggestion="使用默认 file_plan 重建依赖图",
            ))
            return ValidationResult(passed=False, issues=issues)

        for path in nodes:
            if _is_invalid_file_path(path):
                issues.append(ValidationIssue(
                    issue_type="invalid_path",
                    file_path=str(path),
                    message=f"文件路径不合法: {path}",
                    suggestion="使用斜杠分隔目录，例如 app/database.py",
                ))

        adjacency = getattr(dep_graph, "adjacency", {}) or {}
        for source, targets in adjacency.items():
            for target in targets or []:
                if target and not self._dependency_satisfied(target, nodes, current_file=str(source)):
                    issues.append(ValidationIssue(
                        issue_type="missing_dependency",
                        file_path=str(source),
                        message=f"{source} 依赖了不存在的节点 {target}",
                        suggestion="从 file_plan 中补齐该文件或删除该依赖",
                        related_files=[str(target)],
                    ))

        if architecture:
            for item in architecture.get("file_plan") or []:
                if not isinstance(item, dict):
                    continue
                path = item.get("path") or ""
                for dep in item.get("imports") or item.get("dependencies") or []:
                    if not dep:
                        continue
                    if self._dependency_satisfied(dep, nodes, current_file=str(path)):
                        continue
                    if not _looks_like_project_dependency(dep, nodes):
                        continue
                    issues.append(ValidationIssue(
                        issue_type="missing_dependency",
                        file_path=str(path),
                        message=f"{path} 声明了不存在的依赖 {dep}",
                        suggestion="从 file_plan 中补齐该文件或删除该依赖",
                        related_files=[str(dep)],
                    ))

        blocking = [
            issue for issue in issues
            if issue.issue_type in _BLOCKING_ISSUE_TYPES
        ]
        return ValidationResult(passed=not blocking, issues=issues)

    def _dependency_satisfied(self, dep: Any, nodes: set, current_file: str = "") -> bool:
        """Match module-style imports such as src.config to src/config.py nodes."""
        raw = str(dep or "").replace("\\", "/").strip()
        if not raw:
            return True
        if raw in nodes:
            return True
        candidates = list(_heuristic_file_candidates(raw))
        adapter = self._language_adapter
        if adapter is not None:
            try:
                from app.agent.adapters.language_adapter import ImportInfo
                info = ImportInfo(module=raw, symbols=[], is_relative=raw.startswith("."))
                candidates.extend(adapter.resolve_import_to_file(info, current_file or "") or [])
            except Exception:
                logger.debug("语言适配器未能解析依赖: %s", raw, exc_info=True)
        seen = set()
        for candidate in candidates:
            path = str(candidate or "").replace("\\", "/").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            if path in nodes:
                return True
            package = _package_prefix(path)
            if package and any(node == package or node.startswith(package + "/") for node in nodes):
                return True
        return False


def _is_invalid_file_path(path: Any) -> bool:
    if not path:
        return True
    normalized = str(path).replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or normalized.startswith("~"):
        return True
    if any(part == ".." for part in normalized.split("/")):
        return True
    if "/" not in normalized and normalized.count(".") >= 2:
        suffix = normalized.rsplit(".", 1)[-1].lower()
        if suffix in {"py", "js", "ts", "go"} and "." in normalized.rsplit(".", 1)[0]:
            return True
    return False


def _heuristic_file_candidates(dep: str) -> List[str]:
    raw = str(dep or "").replace("\\", "/").strip().strip(".")
    if not raw:
        return []
    candidates = [raw]
    suffix = Path(raw).suffix.lower()
    module_path = raw.replace(".", "/") if "/" not in raw else raw
    if module_path != raw:
        candidates.append(module_path)
    if suffix not in _FILE_SUFFIXES:
        candidates.append(f"{module_path}.py")
        candidates.append(f"{module_path}/__init__.py")
        if "/" in raw and raw != module_path:
            candidates.append(f"{raw}.py")
            candidates.append(f"{raw}/__init__.py")
    seen = set()
    unique: List[str] = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _package_prefix(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    if normalized.endswith("/__init__.py"):
        return normalized[: -len("/__init__.py")]
    suffix = Path(normalized).suffix.lower()
    if suffix in _FILE_SUFFIXES:
        return normalized[: -len(suffix)]
    return normalized.rstrip("/")


def _project_roots(nodes: set) -> set:
    roots = set()
    for path in nodes:
        parts = str(path).replace("\\", "/").split("/")
        if len(parts) > 1:
            roots.add(parts[0])
    return roots


def _looks_like_project_dependency(dep: Any, nodes: set) -> bool:
    raw = str(dep or "").replace("\\", "/").strip()
    if not raw:
        return False
    roots = _project_roots(nodes)
    if not roots:
        suffix = Path(raw).suffix.lower()
        return "/" in raw or suffix in _FILE_SUFFIXES
    for candidate in _heuristic_file_candidates(raw):
        first = candidate.split("/")[0]
        if first in roots:
            return True
    return False
