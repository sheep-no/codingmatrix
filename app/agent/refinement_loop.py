"""
RefinementLoop - 迭代修复循环

核心理念：生成 -> 验证 -> 发现错误 -> 注入错误信息重新生成 -> 再次验证
通过反馈循环提高小模型生成代码的质量。

循环流程：
1. Generate: 使用 LLM 生成代码
2. Validate: 语法检查、导入检查、规范一致性检查
3. Analyze: 分析错误类型和原因
4. Fix: 将错误信息注入 prompt，重新生成
5. Repeat: 最多 N 次，直到验证通过或达到最大次数
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
        from app.agent.models import DEFAULT_CODE_MODEL
        self.default_model = context.model_assignment.get("backend_model", DEFAULT_CODE_MODEL) if context.model_assignment else DEFAULT_CODE_MODEL
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

            if not issues:
                # 验证通过
                return RefinementResult(
                    success=True,
                    final_content=content,
                    attempts=attempt,
                    issues_found=all_issues,
                    issues_fixed=issues_fixed,
                    remaining_issues=[]
                )

            all_issues.extend(issues)

            # Step 2: 分析错误（含错误行 ±10 行代码上下文）
            error_summary = self._build_error_summary(issues, content)

            # Step 3: 如果是最后一次尝试，记录结果并返回
            if attempt == self.MAX_ATTEMPTS:
                logger.warning(f"文件 {file_path} 经过 {attempt} 次修复仍有 {len(issues)} 个问题")
                return RefinementResult(
                    success=False,
                    final_content=content,
                    attempts=attempt,
                    issues_found=all_issues,
                    issues_fixed=issues_fixed,
                    remaining_issues=issues
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
                    break

                new_content = self._clean_code_block(new_content)

                # Step 6: 验证修复是否有效（内容确实改变了）
                if new_content.strip() == content.strip():
                    logger.warning(f"修复尝试 {attempt} 未改变代码内容，消耗一次尝试")
                    break

                content = new_content
                issues_fixed += len(issues)

            except Exception as e:
                logger.error(f"修复尝试 {attempt} 失败: {e}")
                break

        # 理论上不会到这里（最后一次尝试会提前返回）
        return RefinementResult(
            success=False,
            final_content=content,
            attempts=self.MAX_ATTEMPTS,
            issues_found=all_issues,
            issues_fixed=issues_fixed,
            remaining_issues=[]
        )

    # ==================== 验证方法 ====================

    async def _validate_code(self, file_path: str, content: str, file_type: str) -> List[ValidationIssue]:
        """验证代码，返回问题列表"""
        issues: List[ValidationIssue] = []

        ext = Path(file_path).suffix.lower()

        # Python 文件验证
        if ext == '.py':
            issues.extend(self._validate_python_syntax(content, file_path))
            issues.extend(self._validate_python_imports(content))
            issues.extend(self._validate_spec_consistency(content, file_type))

        # JavaScript/TypeScript 文件验证
        elif ext in ('.js', '.ts', '.vue'):
            issues.extend(self._validate_js_basic(content))

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

    def _validate_python_imports(self, content: str) -> List[ValidationIssue]:
        """验证 Python 导入语句"""
        issues = []
        standard_libs = {
            'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing', 'asyncio',
            'logging', 'collections', 'functools', 'itertools', 'math', 'string',
            'io', 'copy', 'time', 'enum', 'dataclasses', 'abc', 'contextlib',
            'urllib', 'http', 'email', 'hashlib', 'hmac', 'secrets', 'base64',
            'struct', 'textwrap', 'unittest', 'pdb', 'traceback', 'warnings',
            'weakref', 'types', 'importlib', 'sqlite3', 'decimal', 'uuid',
            'argparse', 'configparser', 'csv', 'html', 'xml', 'zipfile', 'tarfile',
            'glob', 'shutil', 'tempfile', 'subprocess', 'signal', 'threading',
            'multiprocessing', 'socket', 'ssl', 'select', 'selectors'
        }

        imports = set()
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('import '):
                parts = line[7:].split()
                if parts:
                    module = parts[0].split('.')[0].split(',')[0].strip()
                    if module:
                        imports.add(module)
            elif line.startswith('from '):
                parts = line[5:].split()
                if parts:
                    module = parts[0].split('.')[0].strip()
                    if module and module != '.':
                        imports.add(module)

        # 检查非标准库导入
        missing_imports = []
        for imp in imports:
            if imp in standard_libs:
                continue
            if imp.startswith('_') or imp.startswith('app.') or imp.startswith('src.'):
                continue  # 项目内部导入
            try:
                import importlib
                importlib.import_module(imp)
            except ImportError:
                missing_imports.append(imp)

        if missing_imports:
            issues.append(ValidationIssue(
                type="import",
                severity="warning",
                message=f"可能存在缺失的依赖: {', '.join(missing_imports[:5])}",
                suggestion=f"确保这些包在 requirements.txt 中: {', '.join(missing_imports[:3])}"
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

    def _validate_js_basic(self, content: str) -> List[ValidationIssue]:
        """基础 JavaScript 验证"""
        issues = []
        
        # 尝试使用 node -c 进行语法检查
        try:
            import subprocess
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(content)
                tmp_path = f.name
            
            result = subprocess.run(
                ['node', '-c', tmp_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                # 解析错误信息
                error_msg = result.stderr.strip()
                if error_msg:
                    # 尝试提取行号
                    line_match = re.search(r':(\d+)', error_msg)
                    line_num = int(line_match.group(1)) if line_match else None
                    issues.append(ValidationIssue(
                        type="syntax",
                        severity="error",
                        message=f"JavaScript 语法错误: {error_msg}",
                        line=line_num,
                        suggestion="检查语法错误"
                    ))
            
            # 清理临时文件
            Path(tmp_path).unlink(missing_ok=True)
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # node 不可用，回退到基本检查
            if content.count('{') != content.count('}'):
                issues.append(ValidationIssue(
                    type="syntax",
                    severity="error",
                    message="花括号不匹配",
                    suggestion="检查所有 { 和 } 的配对"
                ))
            if content.count('(') != content.count(')'):
                issues.append(ValidationIssue(
                    type="syntax",
                    severity="error",
                    message="圆括号不匹配",
                    suggestion="检查所有 ( 和 ) 的配对"
                ))
        
        return issues

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
        """HTML 基础验证"""
        issues = []
        # 检查基本标签闭合
        for tag in ['html', 'head', 'body']:
            open_count = len(re.findall(rf'<{tag}[\s>]', content, re.IGNORECASE))
            close_count = len(re.findall(rf'</{tag}>', content, re.IGNORECASE))
            if open_count > close_count:
                issues.append(ValidationIssue(
                    type="syntax",
                    severity="error",
                    message=f"<{tag}> 标签未闭合: 开始 {open_count} 个，结束 {close_count} 个",
                    suggestion=f"添加 </{tag}> 闭合标签"
                ))
        # 检查 script 标签
        script_opens = len(re.findall(r'<script[\s>]', content, re.IGNORECASE))
        script_closes = len(re.findall(r'</script>', content, re.IGNORECASE))
        if script_opens > script_closes:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"<script> 标签未闭合: 开始 {script_opens} 个，结束 {script_closes} 个",
                suggestion="添加 </script> 闭合标签"
            ))
        # 检查 style 标签
        style_opens = len(re.findall(r'<style[\s>]', content, re.IGNORECASE))
        style_closes = len(re.findall(r'</style>', content, re.IGNORECASE))
        if style_opens > style_closes:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"<style> 标签未闭合: 开始 {style_opens} 个，结束 {style_closes} 个",
                suggestion="添加 </style> 闭合标签"
            ))
        return issues

    def _validate_css_basic(self, content: str) -> List[ValidationIssue]:
        """CSS 基础验证"""
        issues = []
        # 检查大括号匹配
        brace_open = content.count('{')
        brace_close = content.count('}')
        if brace_open != brace_close:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"CSS 大括号不匹配: {{ 有 {brace_open} 个，}} 有 {brace_close} 个",
                suggestion="检查所有 { 和 } 的配对"
            ))
        # 检查小括号匹配
        paren_open = content.count('(')
        paren_close = content.count(')')
        if paren_open != paren_close:
            issues.append(ValidationIssue(
                type="syntax",
                severity="error",
                message=f"CSS 小括号不匹配: ( 有 {paren_open} 个，) 有 {paren_close} 个",
                suggestion="检查所有 ( 和 ) 的配对"
            ))
        return issues

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
