"""
SharedContext - 共享上下文

在多阶段生成过程中维护全局状态，包括：
- 需求分析结果
- 架构设计（项目类型、技术栈、目录结构）
- 已生成的规范（OpenAPI、类型定义、数据库 Schema）
- 已生成的文件及其内容
- 依赖关系图
- 错误和警告日志
"""

import json
import logging
import hashlib
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FileArtifact:
    """单个文件的生成产物"""
    path: str
    content: str
    file_type: str  # 'spec', 'model', 'api', 'service', 'view', 'config', 'util', 'test'
    generated_by: str  # model name
    generation_order: int
    depends_on: List[str] = field(default_factory=list)  # 依赖的其他文件路径
    validation_passed: bool = True
    validation_errors: List[str] = field(default_factory=list)
    review_issues: List[str] = field(default_factory=list)
    fix_attempts: int = 0
    content_hash: str = ""
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    language: str = ""
    status: str = "generated"
    diagnostics: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SpecArtifact:
    """规范类产物（OpenAPI、类型定义、数据库 Schema）"""
    spec_type: str  # 'openapi', 'types', 'db_schema', 'config'
    content: Dict[str, Any]
    generated_by: str
    version: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class GenerationPhase:
    """生成阶段状态"""
    name: str
    status: str  # 'pending', 'in_progress', 'completed', 'failed'
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    files_generated: int = 0
    files_total: int = 0
    errors: List[str] = field(default_factory=list)


class SharedContext:
    """
    共享上下文 - 在整个生成生命周期中维护全局状态

    设计原则：
    1. 所有阶段共享同一个上下文实例
    2. 规范（Spec）优先生成并写入上下文
    3. 代码生成阶段读取上下文中的规范
    4. 每个文件的元数据都记录在上下文中
    """

    def __init__(self, requirement: str, output_dir: Path):
        # 基础信息
        self.requirement = requirement
        self.output_dir = output_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 复杂度分析
        self.complexity: Optional[Dict[str, Any]] = None
        self.model_assignment: Optional[Dict[str, str]] = None

        # 架构设计
        self.project_type: str = "unknown"
        self.tech_stack: List[str] = []
        self.directory_structure: Dict[str, Any] = {}

        # 规范产物（Spec-First 核心）
        self.specs: Dict[str, SpecArtifact] = {}

        # 文件产物
        self.files: Dict[str, FileArtifact] = {}
        self.file_generation_order: int = 0

        # 依赖关系
        self.dependencies: Dict[str, List[str]] = {}  # file -> [dependencies]

        # 生成阶段
        self.phases: Dict[str, GenerationPhase] = {}

        # 全局状态
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {}

    # ==================== 指标管理 ====================

    def set_metric(self, key: str, value: Any):
        """设置指标"""
        self.metrics[key] = value

    def get_metric(self, key: str, default: Any = None) -> Any:
        """获取指标"""
        return self.metrics.get(key, default)

    # ==================== 阶段管理 ====================

    def start_phase(self, phase_name: str, total_files: int = 0):
        """开始一个生成阶段"""
        self.phases[phase_name] = GenerationPhase(
            name=phase_name,
            status="in_progress",
            started_at=datetime.now().isoformat(),
            files_total=total_files
        )
        self._log_event("phase_start", {"phase": phase_name, "total_files": total_files})

    def complete_phase(self, phase_name: str, errors: Optional[List[str]] = None):
        """完成一个生成阶段"""
        if phase_name in self.phases:
            phase = self.phases[phase_name]
            phase.status = "failed" if errors is not None else "completed"
            phase.completed_at = datetime.now().isoformat()
            if errors:
                phase.errors.extend(errors)
                self.errors.extend(errors)
        self._log_event("phase_complete", {"phase": phase_name, "errors": errors})

    def get_phase_status(self) -> Dict[str, str]:
        """获取所有阶段的状态"""
        return {name: phase.status for name, phase in self.phases.items()}

    # ==================== 规范管理 ====================

    def save_spec(self, spec_type: str, content: Dict[str, Any], model_name: str):
        """保存规范产物"""
        self.specs[spec_type] = SpecArtifact(
            spec_type=spec_type,
            content=content,
            generated_by=model_name
        )
        self._log_event("spec_saved", {"type": spec_type, "model": model_name})

    def get_spec(self, spec_type: str) -> Optional[Dict[str, Any]]:
        """获取规范内容"""
        artifact = self.specs.get(spec_type)
        return artifact.content if artifact else None

    def get_all_specs_summary(self) -> str:
        """获取所有规范的摘要（用于注入到代码生成的 prompt 中）"""
        parts = []
        for spec_type, artifact in self.specs.items():
            content_preview = json.dumps(artifact.content, ensure_ascii=False)[:500]
            parts.append(f"## {spec_type}\n{content_preview}")
        return "\n\n".join(parts) if parts else "（暂无规范）"

    # ==================== 文件管理 ====================

    def register_file(self, file_path: str, file_type: str, depends_on: Optional[List[str]] = None) -> int:
        """注册一个待生成的文件，返回生成序号"""
        self.file_generation_order += 1
        order = self.file_generation_order

        self.files[file_path] = FileArtifact(
            path=file_path,
            content="",
            file_type=file_type,
            generated_by="",
            generation_order=order,
            depends_on=depends_on or []
        )

        if depends_on:
            self.dependencies[file_path] = depends_on

        return order

    def save_file_content(self, file_path: str, content: str, model_name: str):
        """保存文件内容"""
        content = content or ""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        imports, exports = self._extract_file_symbols(file_path, content)
        if file_path in self.files:
            self.files[file_path].content = content
            self.files[file_path].generated_by = model_name
            self.files[file_path].content_hash = content_hash
            self.files[file_path].imports = imports
            self.files[file_path].exports = exports
            self.files[file_path].language = Path(file_path).suffix.lstrip(".")
            self.files[file_path].status = "generated"
            self.files[file_path].diagnostics = []
        else:
            self.file_generation_order += 1
            self.files[file_path] = FileArtifact(
                path=file_path,
                content=content,
                file_type="unknown",
                generated_by=model_name,
                generation_order=self.file_generation_order,
                content_hash=content_hash,
                imports=imports,
                exports=exports,
                language=Path(file_path).suffix.lstrip("."),
            )

    def update_file_validation(self, file_path: str, passed: bool, errors: Optional[List[str]] = None):
        """更新文件验证状态"""
        if file_path in self.files:
            self.files[file_path].validation_passed = passed
            self.files[file_path].status = "valid" if passed else "invalid"
            if errors:
                self.files[file_path].validation_errors.extend(errors)
                self.files[file_path].diagnostics.extend(errors)

    def is_file_ready(self, file_path: str) -> bool:
        """判断文件及其上游依赖是否可以供下游生成使用。"""
        artifact = self.files.get(file_path)
        if artifact is None or not artifact.content.strip() or not artifact.validation_passed:
            return False
        return self.are_dependencies_ready(file_path)

    def are_dependencies_ready(self, file_path: str) -> bool:
        """判断目标文件的所有上游产物是否有效。"""
        return all(
            dependency in self.files
            and self.files[dependency].content.strip()
            and self.files[dependency].validation_passed
            for dependency in self.dependencies.get(file_path, [])
        )

    def get_artifact_manifest(self) -> Dict[str, Dict[str, Any]]:
        """返回不包含源码的文件产物清单。"""
        return {
            path: {
                "path": artifact.path,
                "content_hash": artifact.content_hash,
                "imports": list(artifact.imports),
                "exports": list(artifact.exports),
                "language": artifact.language,
                "depends_on": list(artifact.depends_on),
                "status": artifact.status,
                "validation_passed": artifact.validation_passed,
                "diagnostics": list(artifact.diagnostics),
            }
            for path, artifact in self.files.items()
        }

    @staticmethod
    def _extract_file_symbols(file_path: str, content: str) -> tuple[List[str], List[str]]:
        """提取跨语言常见导入和导出符号，无法识别时返回空列表。"""
        imports = re.findall(
            r"^\s*(?:from\s+([\w./-]+)\s+import|import\s+([\w./-]+)|#include\s*[<\"]([^>\"]+)|(?:const|let|var)\s+\w+\s*=\s*require\(['\"]([^'\"]+))",
            content,
            re.MULTILINE,
        )
        import_values = [value for match in imports for value in match if value]
        exports = re.findall(
            r"^\s*(?:export\s+)?(?:async\s+)?(?:class|def|function|func|fn|struct|interface|type|enum)\s+([A-Za-z_]\w*)",
            content,
            re.MULTILINE,
        )
        return sorted(set(import_values)), sorted(set(exports))

    def update_file_review(self, file_path: str, issues: Optional[List[str]] = None):
        """更新文件审查结果"""
        if file_path in self.files and issues:
            self.files[file_path].review_issues.extend(issues)

    def increment_fix_attempts(self, file_path: str):
        """增加修复尝试次数"""
        if file_path in self.files:
            self.files[file_path].fix_attempts += 1

    def get_file_content(self, file_path: str) -> Optional[str]:
        """获取已生成的文件内容"""
        artifact = self.files.get(file_path)
        return artifact.content if artifact else None

    def get_generated_files_summary(self) -> str:
        """获取已生成文件的摘要（用于注入到后续文件的 prompt 中）"""
        parts = []
        for path, artifact in sorted(self.files.items(), key=lambda x: x[1].generation_order):
            if artifact.content and artifact.content.strip():
                ext = Path(path).suffix.lstrip('.')
                lang = ext if ext in ('py', 'js', 'ts', 'vue', 'html', 'css', 'json', 'yaml', 'sql', 'md', 'sh') else ''
                preview = artifact.content[:300]
                parts.append(f"## {path}\n```{lang}\n{preview}\n...```\n")
        return "\n".join(parts) if parts else "（暂无已生成文件）"

    # ==================== 依赖查询 ====================

    def get_dependencies_for(self, file_path: str) -> List[str]:
        """获取某个文件的依赖列表"""
        return self.dependencies.get(file_path, [])

    def get_dependents_of(self, file_path: str) -> List[str]:
        """获取依赖某个文件的其他文件列表"""
        return [f for f, deps in self.dependencies.items() if file_path in deps]

    def get_generation_order(self) -> List[str]:
        """按依赖顺序获取文件生成顺序"""
        # 简单的拓扑排序
        visited = set()
        order = []

        def visit(f: str):
            if f in visited:
                return
            visited.add(f)
            for dep in self.dependencies.get(f, []):
                visit(dep)
            order.append(f)

        for f in self.dependencies:
            visit(f)

        # 添加没有依赖关系的文件
        for f in self.files:
            if f not in visited:
                order.append(f)

        return order

    # ==================== 工具方法 ====================

    def add_error(self, error: str):
        """添加错误"""
        self.errors.append(error)
        self._log_event("error", {"message": error})

    def add_warning(self, warning: str):
        """添加警告"""
        self.warnings.append(warning)
        self._log_event("warning", {"message": warning})

    def get_summary(self) -> Dict[str, Any]:
        """获取上下文摘要（用于序列化/日志）"""
        return {
            "session_id": self.session_id,
            "requirement": self.requirement[:100],
            "project_type": self.project_type,
            "tech_stack": self.tech_stack,
            "complexity": self.complexity,
            "phases": {name: phase.status for name, phase in self.phases.items()},
            "specs_generated": list(self.specs.keys()),
            "files_count": len(self.files),
            "files_generated": sum(1 for f in self.files.values() if f.content),
            "errors_count": len(self.errors),
            "warnings_count": len(self.warnings),
            "metrics": self.metrics
        }

    def to_export_dict(self) -> Dict[str, Any]:
        """导出完整的上下文字典（用于保存或调试）"""
        return {
            "session_id": self.session_id,
            "requirement": self.requirement,
            "output_dir": str(self.output_dir),
            "project_type": self.project_type,
            "tech_stack": self.tech_stack,
            "complexity": self.complexity,
            "model_assignment": self.model_assignment,
            "specs": {k: {"type": v.spec_type, "content": v.content, "model": v.generated_by} for k, v in self.specs.items()},
            "files": {k: {
                "path": v.path,
                "file_type": v.file_type,
                "model": v.generated_by,
                "order": v.generation_order,
                "depends_on": v.depends_on,
                "content_hash": v.content_hash,
                "imports": v.imports,
                "exports": v.exports,
                "language": v.language,
                "status": v.status,
                "validation_passed": v.validation_passed,
                "validation_errors": v.validation_errors,
                "diagnostics": v.diagnostics,
                "review_issues": v.review_issues,
                "fix_attempts": v.fix_attempts,
                "timestamp": v.timestamp
            } for k, v in self.files.items()},
            "dependencies": self.dependencies,
            "phases": {name: {
                "status": phase.status,
                "started_at": phase.started_at,
                "completed_at": phase.completed_at,
                "files_generated": phase.files_generated,
                "files_total": phase.files_total,
                "errors": phase.errors
            } for name, phase in self.phases.items()},
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics
        }

    def _log_event(self, event_type: str, details: Dict[str, Any]):
        """记录事件（用于调试和追踪）"""
        logger.debug(f"[Context:{self.session_id}] {event_type}: {json.dumps(details, ensure_ascii=False)}")
