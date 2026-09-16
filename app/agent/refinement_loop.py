"""
RefinementLoop - 迭代修复循环

核心理念：生成 -> 验证 -> 发现错误 -> 注入错误信息重新生成 -> 再次验证
通过反馈循环提高小模型生成代码的质量。

循环流程：
1. Generate: 使用 LLM 生成代码
2. Validate: 语法检查、规范一致性检查
3. Analyze: 分析错误类型和原因
4. Fix: 将错误信息注入 prompt，重新生成
5. Repeat: 最多 N 次，直到验证通过或达到最大次数

说明：只有 error 级别的问题会驱动修复循环；warning 只作为诊断信息返回。
"""

import json
import re
import ast
import asyncio
import logging
from typing import Optional, Dict, List, Callable
from pathlib import Path
from dataclasses import dataclass

from app.utils import call_llm
from app.agent.shared_context import SharedContext
from app.agent.js_syntax import check_js_source, check_ts_source, vue_script_source
from app.agent.markup_syntax import css_structure_errors, html_structure_errors

logger = logging.getLogger(__name__)


# 按复杂度分级的修复轮次限制
_REFINEMENT_ATTEMPTS_BY_COMPLEXITY = {
    "simple": 2,
    "small": 2,
    "medium": 3,
    "large": 4,
    "enterprise": 5,
}


@dataclass
class ValidationIssue:
    """单个验证问题"""
    type: str  # 'syntax', 'import', 'spec_mismatch', 'missing_ref', 'logic'
    severity: str  # 'error', 'warning'
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class RefinementResult:
    """迭代修复结果"""
    success: bool
    final_content: str
    attempts: int
    issues_found: List[ValidationIssue]
    issues_fixed: int
    remaining_issues: List[ValidationIssue]


class RefinementLoop:
    """
    迭代修复循环

    通过"生成-验证-修复"循环，逐步提高代码质量。
    每次修复都会将上一次的错误信息注入到 prompt 中，
    让模型知道哪里需要修复。
    """

    MAX_ATTEMPTS = 3
    SYSTEM_PROMPT = """你是一位资深代码修复专家，擅长根据错误信息修复代码。

你的任务：
1. 理解当前代码中的错误
2. 根据错误信息进行针对性修复
3. 返回修复后的完整代码

规则：
- 返回完整代码，不要省略任何部分
- 保持原有代码结构，只修复错误部分
- 不要添加新的功能或改变原有逻辑"""

    def __init__(self, context: SharedContext, complexity: str = "medium", api_key_token: Optional[str] = None):
        self.context = context
        self.api_key_token = api_key_token
        self._pending_tasks: set = set()
        assignment = context.model_assignment or {}
        self.default_model = assignment.get("backend_model") if isinstance(assignment, dict) else getattr(assignment, "backend_model", None)
        if not self.default_model:
            raise RuntimeError("model assignment is required for refinement")
        from app.agent.orchestrator import LayeredModelRouter
        self.model_config = LayeredModelRouter.get_model_config(self.default_model)
        self._complexity = complexity
        self.MAX_ATTEMPTS = _REFINEMENT_ATTEMPTS_BY_COMPLEXITY.get(complexity, 3)

    async def refine(
        self,
        file_path: str,
        file_type: str,
        description: str,
        initial_content: str,
        model_name: Optional[str] = None,
        project_context: Optional[Dict] = None,
        callback: Optional[Callable] = None
    ) -> RefinementResult:
        """
        执行迭代修复循环

        Args:
            file_path: 文件路径
            file_type: 文件类型
            description: 文件描述
            initial_content: 初始生成的代码内容
            model_name: 使用的模型（默认使用后端模型）
            project_context: 项目上下文
            callback: 进度回调

        Returns:
            RefinementResult
        """
        target_model = model_name or self.default_model
        from app.agent.orchestrator import LayeredModelRouter
        model_config = LayeredModelRouter.get_model_config(target_model)
        content = initial_content
        all_issues: List[ValidationIssue] = []
        issues_fixed = 0

        self.context.increment_fix_attempts(file_path)

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            self._report_progress(file_path, attempt, callback)

            # Step 1: 验证当前代码
            issues = await self._validate_code(file_path, content, file_type)

            all_issues.extend(issues)

            # 只有 error 级别的缺陷才需要修复。warning 是提示性信息（规范建议等），
            # 既不阻塞文件通过，也不该触发整文件重写：修复循环重写的是当前文件，
            # 无法解决文件之外的提示，反复重写只会消耗轮次并可能改坏代码。
            blocking = [issue for issue in issues if issue.severity == "error"]

            if not blocking:
                # 无阻塞缺陷即视为通过，warning 作为诊断信息保留
                return RefinementResult(
                    success=True,
                    final_content=content,
                    attempts=attempt,
                    issues_found=all_issues,
                    issues_fixed=issues_fixed,
                    remaining_issues=[issue for issue in issues if issue.severity != "error"]
                )

            # Step 2: 分析错误（含错误行 ±10 行代码上下文）
            error_summary = self._build_error_summary(blocking, content)

            # Step 3: 如果是最后一次尝试，记录结果并返回
            if attempt == self.MAX_ATTEMPTS:
                logger.warning(f"文件 {file_path} 经过 {attempt} 次修复仍有 {len(blocking)} 个问题")
                return RefinementResult(
                    success=False,
                    final_content=content,
                    attempts=attempt,
                    issues_found=all_issues,
                    issues_fixed=issues_fixed,
                    remaining_issues=blocking
                )

            # Step 4: 构建修复 prompt
            fix_prompt = self._build_fix_prompt(
                file_path=file_path,
                file_type=file_type,
                description=description,
                current_code=content,
                error_summary=error_summary,
                project_context=project_context,
                attempt=attempt
            )

            # Step 5: 调用 LLM 修复
            try:
                response = await call_llm(
                    prompt=fix_prompt,
                    model=target_model,
                    stream=False,
                    max_tokens=model_config["max_tokens"],
                    thinking_budget=model_config["thinking_budget"],
                    temperature=0.5,  # 修复时使用更低的温度
                    api_key_token=self.api_key_token
                )

                new_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not new_content or not new_content.strip():
                    logger.warning(f"修复尝试 {attempt} 返回空内容，消耗一次尝试")
                    continue

                new_content = self._clean_code_block(new_content)

                # Step 6: 验证修复是否有效（内容确实改变了）
                if new_content.strip() == content.strip():
                    logger.warning(f"修复尝试 {attempt} 未改变代码内容，消耗一次尝试")
                    continue

                content = new_content
                issues_fixed += len(blocking)

            except Exception as e:
                logger.error(f"修复尝试 {attempt} 失败: {e}")
                continue

        # 理论上不会到这里（最后一次尝试会提前返回）
        return RefinementResult(
            success=False,
            final_content=content,
            attempts=self.MAX_ATTEMPTS,
            issues_found=all_issues,
            issues_fixed=issues_fixed,
            remaining_issues=blocking or all_issues
        )

    # ==================== 验证方法 ====================

    async def _validate_code(self, file_path: str, content: str, file_type: str) -> List[ValidationIssue]:
        """验证代码，返回问题列表"""
        issues: List[ValidationIssue] = []

        ext = Path(file_path).suffix.lower()

        # Python 文件验证
        if ext == '.py':
            issues.extend(self._validate_python_syntax(content, file_path))
            issues.extend(self._validate_spec_consistency(content, file_type))

        # JavaScript/TypeScript 文件验证
        elif ext in ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue'):
            issues.extend(self._validate_js_source(content, ext))

        # JSON 文件验证
        elif ext == '.json':
            issues.extend(self._validate_json_syntax(content))

        # HTML 文件验证
        elif ext == '.html':
            issues.extend(self._validate_html_basic(content))

        # CSS 文件验证
        elif ext == '.css':
            issues.extend(self._validate_css_basic(content))

        return issues

    def _validate_python_syntax(self, content: str, file_path: str) -> List[ValidationIssue]:
        """验证 Python 语法"""
        issues = []
        try:
            ast.parse(content)
        except SyntaxError as e:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"语法错误: {e.msg}",
                line=e.lineno,
                suggestion="检查括号匹配、缩进和语法正确性"
            ))
        return issues

    def _validate_spec_consistency(self, content: str, file_type: str) -> List[ValidationIssue]:
        """验证代码与规范的一致性"""
        issues = []

        # 如果是 API 相关文件，检查是否引用了正确的路由
        if file_type in ("api", "view", "controller", "router"):
            openapi = self.context.get_spec("openapi")
            if openapi:
                paths = openapi.get("paths", {})
                for path in paths:
                    # 检查路径是否在代码中出现
                    # 简化检查：只检查路径的关键部分
                    path_parts = path.strip('/').split('/')
                    for part in path_parts:
                        if part and not part.startswith('{') and part not in content:
                            # 不一定要报错，只是记录为 warning
                            pass

        # 如果是模型相关文件，检查是否引用了正确的字段
        if file_type in ("model", "entity", "dto"):
            types_spec = self.context.get_spec("types")
            if types_spec and types_spec.get("code"):
                # 简化检查：确保代码中使用了 Pydantic 的 BaseModel
                if "BaseModel" not in content and "pydantic" not in content.lower():
                    issues.append(ValidationIssue(
                        type="spec_mismatch",
                        severity="warning",
                        message="类型定义文件应使用 Pydantic BaseModel",
                        suggestion="from pydantic import BaseModel"
                    ))

        return issues

    def _validate_js_source(self, content: str, ext: str) -> List[ValidationIssue]:
        """校验 JS/TS 家族源码，包括 .vue 的 <script> 块与 JSX/TSX。

        `node -c` 无法解析 JSX、类型注解和 Vue 单文件组件，整体送检会误报；
        按扩展名选择共享校验器（见 app/agent/js_syntax.py）。
        """
        use_ts = ext in ('.ts', '.tsx')
        use_jsx = ext in ('.jsx', '.tsx')
        source = content
        if ext == '.vue':
            source, use_ts, use_jsx = vue_script_source(content)
        if not source.strip():
            return []

        if use_ts:
            ok, error = check_ts_source(source, jsx=use_jsx)
            label = "TypeScript"
        else:
            ok, error = check_js_source(source)
            label = "JavaScript"
        if ok:
            return []

        error = error or "语法检查未通过"
        line_match = re.search(r':(\d+)', error)
        return [ValidationIssue(
            type="syntax",
            severity="error",
            message=f"{label} 语法错误: {error}",
            line=int(line_match.group(1)) if line_match else None,
            suggestion="检查语法错误",
        )]

    def _validate_json_syntax(self, content: str) -> List[ValidationIssue]:
        """验证 JSON 语法"""
        issues = []
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"JSON 语法错误: {e.msg}",
                line=e.lineno,
                suggestion="检查 JSON 格式，确保键用双引号包裹"
            ))
        return issues

    def _validate_html_basic(self, content: str) -> List[ValidationIssue]:
        """HTML 基础验证（复用共享结构校验：注释和原始文本元素里的标签不算）"""
        return [
            ValidationIssue(
                type="syntax",
                severity="error",
                message=error,
                suggestion="检查标签配对，补全缺失的闭合标签",
            )
            for error in html_structure_errors(content)
        ]

    def _validate_css_basic(self, content: str) -> List[ValidationIssue]:
        """CSS 基础验证（复用共享结构校验：注释和字符串里的定界符不算）"""
        return [
            ValidationIssue(
                type="syntax",
                severity="error",
                message=error,
                suggestion="检查括号配对与声明闭合",
            )
            for error in css_structure_errors(content, check_parentheses=True)
        ]

    # ==================== Prompt 构建 ====================

    def _build_error_summary(self, issues: List[ValidationIssue], current_code: str = "") -> str:
        """构建错误摘要（含错误行 ±10 行代码上下文）"""
        if not issues:
            return "没有发现错误"

        lines = current_code.split('\n') if current_code else []
        parts = []
        for i, issue in enumerate(issues, 1):
            line_info = f" (第 {issue.line} 行)" if issue.line else ""
            parts.append(f"{i}. [{issue.severity.upper()}]{line_info} {issue.type}: {issue.message}")
            if issue.suggestion:
                parts.append(f"   建议: {issue.suggestion}")

            # 注入错误行 ±10 行代码上下文
            if issue.line and lines and 1 <= issue.line <= len(lines):
                start = max(0, issue.line - 11)
                end = min(len(lines), issue.line + 10)
                context_lines = []
                for idx in range(start, end):
                    marker = " >>> " if idx == issue.line - 1 else "     "
                    context_lines.append(f"{marker}{idx + 1:4d} | {lines[idx]}")
                parts.append("   代码上下文:\n" + "\n".join(context_lines))

        return "\n".join(parts)

    def _build_fix_prompt(
        self,
        file_path: str,
        file_type: str,
        description: str,
        current_code: str,
        error_summary: str,
        project_context: Optional[Dict],
        attempt: int
    ) -> str:
        """构建修复 prompt"""
        # 获取相关规范上下文
        spec_context = ""
        try:
            from app.agent.spec_first_generator import SpecFirstGenerator
            gen = SpecFirstGenerator(self.context)
            spec_context = gen.get_spec_context_for_file(file_path, file_type)
        except Exception as e:
            logger.debug(f"精炼循环操作失败：{e}")

        # 获取已生成的相关文件
        related_files = self.context.get_generated_files_summary()

        prompt_parts = [
            "【SYSTEM】",
            self.SYSTEM_PROMPT,
            "",
            "【USER】",
            f"## 第 {attempt} 次修复",
            "",
            f"文件路径: {file_path}",
            f"文件类型: {file_type}",
            f"文件描述: {description}",
            "",
            "## 发现的错误",
            error_summary,
            "",
            "## 当前代码",
            "```",
            current_code,
            "```",
            "",
            "## 相关规范",
            spec_context if spec_context else "（无相关规范）",
            "",
            "## 已生成的相关文件",
            related_files if related_files else "（无相关文件）",
            "",
            "请修复上述错误，返回修复后的完整代码。"
        ]

        return "\n".join(prompt_parts)

    # ==================== 辅助方法 ====================

    def _clean_code_block(self, content: str) -> str:
        """清理代码块标记"""
        from app.agent.utils import clean_code_block
        return clean_code_block(content)

    def _report_progress(self, file_path: str, attempt: int, callback: Optional[Callable]):
        """报告进度"""
        if not callback:
            return
        progress = {
            "type": "refinement_progress",
            "file_path": file_path,
            "attempt": attempt,
            "max_attempts": self.MAX_ATTEMPTS
        }
        try:
            result = callback(json.dumps(progress, ensure_ascii=False))
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)
        except Exception as e:
            logger.error(f"修复进度回调失败: {e}")
