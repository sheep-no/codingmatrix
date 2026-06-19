"""
DependencyGraphValidator - 依赖图验证器

通过 LLM 验证依赖图的正确性，检测：
1. 功能重复：不同路径但描述相同的文件
2. 错误路径：路径格式不合法
3. 缺失依赖：依赖指向不存在的节点
4. 文件类型错误：file_type 与扩展名不匹配
"""

import json
import logging
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 最大重试次数
MAX_VALIDATION_RETRIES = 2


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
        self.error_count = sum(1 for i in self.issues if i.issue_type in ('duplicate_function', 'missing_dependency', 'framework_inconsistency', 'interface_mismatch'))
        self.warning_count = sum(1 for i in self.issues if i.issue_type in ('invalid_path', 'wrong_file_type', 'same_name_file'))


class DependencyGraphValidator:
    """依赖图验证器

    通过 LLM 验证依赖图的正确性。

    Args:
        llm_caller: async 函数，接受 (prompt, system_prompt) 返回 LLM 响应
        language_adapter: 语言适配器（可选）
    """

    def __init__(
        self,
        llm_caller: Callable[[str, str], Awaitable[str]],
        language_adapter=None,
    ):
        self._llm_caller = llm_caller
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
        # 构建验证上下文
        context = self._build_context(dep_graph, scope, new_files, architecture)

        # 调用 LLM 验证
        prompt = self._build_prompt(context, scope)
        system_prompt = self._build_system_prompt(scope)

        try:
            response = await self._llm_caller(prompt, system_prompt)
            result = self._parse_response(response)
            return result
        except Exception as e:
            logger.error(f"依赖图验证失败: {e}")
            # 验证失败不阻塞生成，返回通过但记录 warning
            return ValidationResult(passed=True, issues=[
                ValidationIssue(
                    issue_type="validation_error",
                    file_path="",
                    message=f"验证过程出错: {str(e)}",
                    suggestion="跳过验证，继续生成"
                )
            ])

    def _build_context(
        self,
        dep_graph,
        scope: str,
        new_files: Optional[List[str]],
        architecture: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建验证上下文"""
        # 获取所有节点信息
        nodes = {}
        for path, node in dep_graph.nodes.items():
            nodes[path] = {
                "type": node.file_type,
                "priority": node.priority,
                "description": node.description,
            }

        # 获取所有边
        edges = []
        for source, targets in dep_graph.adjacency.items():
            for target in targets:
                if source in dep_graph.nodes and target in dep_graph.nodes:
                    edges.append({"from": source, "to": target})

        # 获取 file_plan 描述和 imports（如果有）
        file_plan_descriptions = {}
        file_plan_imports = {}
        if architecture:
            for fi in architecture.get("file_plan", []):
                fp = fi.get("path", "")
                if fp:
                    file_plan_descriptions[fp] = fi.get("description", "")
                    if fi.get("imports"):
                        file_plan_imports[fp] = fi["imports"]

        # 获取 project_spec 中的框架信息
        project_spec = architecture.get("project_spec", {}) if architecture else {}
        framework_info = {}
        if project_spec:
            default_fw = project_spec.get("default", {}).get("framework")
            for spec_key, spec_val in project_spec.items():
                fw = spec_val.get("framework", default_fw)
                if fw:
                    framework_info[spec_key] = fw

        context = {
            "nodes": nodes,
            "edges": edges,
            "file_plan_descriptions": file_plan_descriptions,
            "file_plan_imports": file_plan_imports,
            "framework_info": framework_info,
            "total_files": len(nodes),
            "total_edges": len(edges),
        }

        if scope == "incremental" and new_files:
            context["new_files"] = new_files
            # 获取新文件的直接依赖
            new_file_deps = {}
            for nf in new_files:
                deps = list(dep_graph.adjacency.get(nf, set()))
                dependents = list(dep_graph.reverse_adjacency.get(nf, set()))
                new_file_deps[nf] = {"depends_on": deps, "depended_by": dependents}
            context["new_file_dependencies"] = new_file_deps

        if scope == "refactor" and new_files:
            context["refactored_files"] = new_files

        return context

    def _build_system_prompt(self, scope: str) -> str:
        """构建系统提示词"""
        base = """你是一个依赖图验证专家。你的任务是检查文件依赖图的正确性。

你需要检测以下问题：
1. **功能重复**：不同路径的文件描述了相同的功能，应该合并
2. **错误路径**：文件路径格式不合法（如使用点号分隔目录 app.database.py）
3. **缺失依赖**：文件依赖了图中不存在的节点
4. **文件类型错误**：file_type 与文件扩展名明显不匹配
5. **同名文件**：不同目录下的文件使用了相同的文件名，容易造成混淆
6. **框架不一致**：同一运行时的文件使用了不同的框架（如 main.py 用 FastAPI 但 routers.py 用 Flask）
7. **接口不匹配**：下游文件导入的类/函数名在上游文件中不存在（如下游导入 ExpenseModel 但上游定义的是 Transaction）

你必须返回严格的 JSON 格式，不要添加任何其他文本：
```json
{
  "passed": true/false,
  "issues": [
    {
      "issue_type": "duplicate_function|invalid_path|missing_dependency|wrong_file_type|same_name_file|framework_inconsistency|interface_mismatch",
      "file_path": "问题文件路径",
      "message": "问题描述",
      "suggestion": "修复建议",
      "related_files": ["相关文件路径"]
    }
  ]
}
```

判断规则：
- 功能重复：两个文件的描述高度相似（>80% 语义重合），且功能确实相同
- 错误路径：路径格式不合法。特别注意：如果路径中没有斜杠 `/` 但有多个点号段（如 `src.app.utils.py`、`app.database.py`），这是错误格式，应该用斜杠分隔目录（如 `src/app/utils.py`）。但单个文件名中的点号是合法的（如 `app.py`、`docker.toml.backup`）
- 缺失依赖：边的目标节点不在节点列表中
- 文件类型错误：扩展名与 file_type 明显矛盾（如 .html 文件的 file_type 是 model）
- 同名文件警告：不同目录下的文件使用相同文件名（如 models/user.py 和 routers/user.py），虽然不一定是错误，但容易造成混淆，建议使用更具描述性的名称（如 user_model.py、user_router.py）
- 框架不一致：检查 project_spec 中的 framework 字段，如果后端文件 A 使用 FastAPI 但后端文件 B 使用 Flask，这是严重错误。requirements.txt 中的依赖也必须与框架一致
- 接口不匹配：检查 file_plan 中的 imports 字段，如果文件 A 的 imports 列出了从文件 B 导入 ExpenseModel，但文件 B 的 description 中定义的是 Transaction 类，这是接口不匹配错误

如果没有问题，返回 passed=true 和空 issues 列表。"""

        if scope == "incremental":
            base += "\n\n当前是增量验证模式，只关注新增文件与已有文件的关系。"
        elif scope == "refactor":
            base += "\n\n当前是重构验证模式，关注文件拆分后依赖关系的正确性。"

        return base

    def _build_prompt(self, context: Dict[str, Any], scope: str) -> str:
        """构建验证 prompt"""
        lines = []

        if scope == "incremental":
            lines.append("## 新增文件验证")
            lines.append(f"新增文件数量: {len(context.get('new_files', []))}")
            lines.append(f"已有文件总数: {context['total_files']}")
            lines.append("")
            lines.append("### 新增文件:")
            for nf in context.get("new_files", []):
                node_info = context["nodes"].get(nf, {})
                desc = context.get("file_plan_descriptions", {}).get(nf, node_info.get("description", ""))
                lines.append(f"- {nf} (type={node_info.get('type', 'unknown')}): {desc}")
                deps_info = context.get("new_file_dependencies", {}).get(nf, {})
                if deps_info.get("depends_on"):
                    lines.append(f"  依赖: {deps_info['depends_on']}")
                if deps_info.get("depended_by"):
                    lines.append(f"  被依赖: {deps_info['depended_by']}")
            lines.append("")
            lines.append("### 已有文件（用于检查功能重复）:")
            existing_files = {k: v for k, v in context["nodes"].items() if k not in context.get("new_files", [])}
            for path, info in existing_files.items():
                desc = context.get("file_plan_descriptions", {}).get(path, info.get("description", ""))
                lines.append(f"- {path} (type={info.get('type', 'unknown')}): {desc}")

        elif scope == "refactor":
            lines.append("## 重构验证")
            lines.append(f"重构文件数量: {len(context.get('refactored_files', []))}")
            lines.append(f"总文件数: {context['total_files']}")
            lines.append("")
            lines.append("### 重构涉及的文件:")
            for rf in context.get("refactored_files", []):
                node_info = context["nodes"].get(rf, {})
                desc = context.get("file_plan_descriptions", {}).get(rf, node_info.get("description", ""))
                lines.append(f"- {rf} (type={node_info.get('type', 'unknown')}): {desc}")
            lines.append("")
            lines.append("### 依赖关系:")
            for edge in context["edges"]:
                if edge["from"] in context.get("refactored_files", []) or edge["to"] in context.get("refactored_files", []):
                    lines.append(f"- {edge['from']} -> {edge['to']}")

        else:  # full
            lines.append("## 完整依赖图验证")
            lines.append(f"文件总数: {context['total_files']}")
            lines.append(f"依赖关系数: {context['total_edges']}")
            lines.append("")
            lines.append("### 文件列表:")
            for path, info in context["nodes"].items():
                desc = context.get("file_plan_descriptions", {}).get(path, info.get("description", ""))
                lines.append(f"- {path} (type={info.get('type', 'unknown')}, priority={info.get('priority', 3)}): {desc}")
            lines.append("")
            lines.append("### 依赖关系:")
            for edge in context["edges"]:
                lines.append(f"- {edge['from']} -> {edge['to']}")

        return "\n".join(lines)

    def _parse_response(self, response: str) -> ValidationResult:
        """解析 LLM 响应"""
        # 提取 JSON
        response = response.strip()

        # 尝试从 markdown 代码块中提取
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                response = response[start:end].strip()

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 和最后一个 }
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    logger.warning(f"无法解析验证响应: {response[:200]}")
                    return ValidationResult(passed=True)
            else:
                logger.warning(f"验证响应中未找到 JSON: {response[:200]}")
                return ValidationResult(passed=True)

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(ValidationIssue(
                issue_type=issue_data.get("issue_type", "unknown"),
                file_path=issue_data.get("file_path", ""),
                message=issue_data.get("message", ""),
                suggestion=issue_data.get("suggestion", ""),
                related_files=issue_data.get("related_files", []),
            ))

        return ValidationResult(
            passed=data.get("passed", True),
            issues=issues,
        )


def format_validation_feedback(result: ValidationResult) -> str:
    """将验证结果格式化为反馈文本，用于传递给架构师重新生成"""
    if result.passed:
        return ""

    lines = ["依赖图验证未通过，请根据以下问题修正："]
    for i, issue in enumerate(result.issues, 1):
        lines.append(f"{i}. [{issue.issue_type}] {issue.message}")
        if issue.file_path:
            lines.append(f"   文件: {issue.file_path}")
        if issue.related_files:
            lines.append(f"   相关文件: {', '.join(issue.related_files)}")
        if issue.suggestion:
            lines.append(f"   建议: {issue.suggestion}")
    lines.append("")
    lines.append("请修正后重新生成 file_plan。")
    return "\n".join(lines)
