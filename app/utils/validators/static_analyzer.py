"""
静态代码分析器 - 集成 flake8/pylint 等工具
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import sys
import json
import ast

logger = logging.getLogger(__name__)


@dataclass
class LintIssue:
    """代码规范问题"""
    file: str
    line: int
    column: int
    code: str
    message: str
    severity: str  # error/warning/info


@dataclass
class LintResult:
    """Lint 结果"""
    success: bool
    issues: List[LintIssue] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    duration_seconds: float = 0.0


@dataclass
class ComplexityReport:
    """复杂度报告"""
    file: str
    function: str
    line: int
    cyclomatic_complexity: int
    cognitive_complexity: Optional[int] = None
    issue_count: int = 0


@dataclass
class StyleResult:
    """代码风格结果"""
    success: bool
    is_formatted: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class StaticAnalyzer:
    """静态代码分析器"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.python_executable: str = sys.executable
    
    async def run_linter(
        self,
        file_path: Optional[Path] = None,
        use_flake8: bool = True,
        use_pylint: bool = False
    ) -> LintResult:
        """
        运行代码检查
        
        Args:
            file_path: 要检查的文件，None 则检查整个项目
            use_flake8: 是否使用 flake8
            use_pylint: 是否使用 pylint
        
        Returns:
            LintResult: 检查结果
        """
        import time
        start_time = time.time()
        
        result = LintResult(success=True)
        
        # flake8 检查
        if use_flake8:
            flake8_result = await self._run_flake8(file_path)
            result.issues.extend(flake8_result.issues)
            result.errors += flake8_result.errors
            result.warnings += flake8_result.warnings
            result.infos += flake8_result.infos
        
        # pylint 检查
        if use_pylint:
            pylint_result = await self._run_pylint(file_path)
            result.issues.extend(pylint_result.issues)
            result.errors += pylint_result.errors
            result.warnings += pylint_result.warnings
            result.infos += pylint_result.infos
        
        result.duration_seconds = time.time() - start_time
        result.success = result.errors == 0
        
        return result
    
    async def _run_flake8(self, file_path: Optional[Path]) -> LintResult:
        """运行 flake8"""
        result = LintResult(success=True)
        
        try:
            # 检查是否安装了 flake8
            if not await self._check_tool_installed('flake8'):
                logger.warning("flake8 未安装，跳过检查")
                return result
            
            cmd = [
                self.python_executable,
                "-m", "flake8",
                "--max-line-length=120",
                "--ignore=E501,W503",
                "--format=json"
            ]
            
            if file_path:
                cmd.append(str(file_path))
            else:
                # 检查所有 Python 文件
                cmd.append(str(self.project_path))
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                try:
                    # 解析 JSON 输出
                    issues_data = json.loads(stdout.decode('utf-8'))
                    for issue in issues_data:
                        severity = "error"
                        if issue.get('code', '').startswith('W'):
                            severity = "warning"
                        elif issue.get('code', '').startswith('I'):
                            severity = "info"
                        
                        result.issues.append(LintIssue(
                            file=issue.get('filename', ''),
                            line=issue.get('line_number', 0),
                            column=issue.get('column_number', 0),
                            code=issue.get('code', ''),
                            message=issue.get('text', ''),
                            severity=severity
                        ))
                        
                        if severity == "error":
                            result.errors += 1
                        elif severity == "warning":
                            result.warnings += 1
                        else:
                            result.infos += 1
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    logger.error(f"解析 flake8 输出失败：{e}")
                    
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"运行 flake8 失败：{e}")
        
        return result
    
    async def _run_pylint(self, file_path: Optional[Path]) -> LintResult:
        """运行 pylint"""
        result = LintResult(success=True)
        
        try:
            # 检查是否安装了 pylint
            if not await self._check_tool_installed('pylint'):
                logger.warning("pylint 未安装，跳过检查")
                return result
            
            cmd = [
                self.python_executable,
                "-m", "pylint",
                "--output-format=json",
                "--reports=no",
                "--max-line-length=120",
                "--disable=C0114,C0115,C0116"  # 跳过文档字符串要求
            ]
            
            if file_path:
                cmd.append(str(file_path))
            else:
                cmd.append(str(self.project_path))
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0 or stdout:
                try:
                    issues_data = json.loads(stdout.decode('utf-8'))
                    for issue in issues_data:
                        severity = issue.get('type', 'error')
                        symbol = issue.get('symbol', '')
                        
                        result.issues.append(LintIssue(
                            file=issue.get('path', ''),
                            line=issue.get('line', 0),
                            column=issue.get('column', 0),
                            code=symbol,
                            message=issue.get('message', ''),
                            severity=severity
                        ))
                        
                        if severity == "error":
                            result.errors += 1
                        elif severity == "warning" or severity == "convention":
                            result.warnings += 1
                        else:
                            result.infos += 1
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    logger.error(f"解析 pylint 输出失败：{e}")
                    
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"运行 pylint 失败：{e}")
        
        return result
    
    async def check_complexity(self, file_path: Path) -> List[ComplexityReport]:
        """
        检查代码复杂度
        
        Args:
            file_path: 要检查的文件
        
        Returns:
            List[ComplexityReport]: 复杂度报告列表
        """
        import ast
        
        reports = []
        
        try:
            if not file_path.exists():
                return reports
            
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # 计算圈复杂度
                    complexity = self._calculate_cyclomatic_complexity(node)
                    
                    # 计算认知复杂度（简化版）
                    cognitive = self._calculate_cognitive_complexity(node)
                    
                    issue_count = 0
                    if complexity > 10:
                        issue_count += 1
                    if cognitive and cognitive > 15:
                        issue_count += 1
                    
                    if issue_count > 0:
                        reports.append(ComplexityReport(
                            file=str(file_path),
                            function=node.name,
                            line=node.lineno or 0,
                            cyclomatic_complexity=complexity,
                            cognitive_complexity=cognitive,
                            issue_count=issue_count
                        ))
                        
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"检查复杂度失败：{e}")
        
        return reports
    
    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        """计算圈复杂度"""
        complexity = 1
        
        for child in ast.walk(node):
            if isinstance(child, (
                ast.If, ast.While, ast.For, ast.ExceptHandler,
                ast.With, ast.Assert, ast.comprehension
            )):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity
    
    def _calculate_cognitive_complexity(self, node: ast.AST) -> int:
        """计算认知复杂度（简化版）"""
        complexity = 0
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
                # 嵌套增加额外复杂度
                if isinstance(child.parent if hasattr(child, 'parent') else None,
                              (ast.If, ast.While, ast.For)):
                    complexity += 1
        
        return complexity
    
    async def check_code_style(self, file_path: Path) -> StyleResult:
        """
        检查代码风格
        
        Args:
            file_path: 要检查的文件
        
        Returns:
            StyleResult: 风格检查结果
        """
        result = StyleResult(success=True, is_formatted=True)
        
        try:
            # 检查是否安装了 black
            if not await self._check_tool_installed('black'):
                logger.info("black 未安装，跳过格式检查")
                return result
            
            # 使用 black --check 检查格式
            cmd = [
                self.python_executable,
                "-m", "black",
                "--check",
                "--line-length=120",
                "--quiet",
                str(file_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                result.is_formatted = False
                result.success = False
                error_msg = stderr.decode('utf-8', errors='ignore')
                result.issues.append(f"代码格式不符合 black 规范：{error_msg[:200]}")
                result.suggestions.append("运行 `black .` 自动格式化代码")
            
            # 检查 isort
            if await self._check_tool_installed('isort'):
                cmd = [
                    self.python_executable,
                    "-m", "isort",
                    "--check-only",
                    "--quiet",
                    str(file_path)
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                _, stderr = await process.communicate()
                
                if process.returncode != 0:
                    result.is_formatted = False
                    result.success = False
                    result.issues.append("导入顺序不符合 isort 规范")
                    result.suggestions.append("运行 `isort .` 自动整理导入")
                    
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"检查代码风格失败：{e}")
            result.issues.append(f"检查失败：{str(e)}")
        
        return result
    
    async def _check_tool_installed(self, tool_name: str) -> bool:
        """检查工具是否已安装"""
        try:
            cmd = [
                self.python_executable,
                "-m", tool_name,
                "--version"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except (ValueError, TypeError, RuntimeError, OSError):
            return False
