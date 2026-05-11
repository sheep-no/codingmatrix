import ast
import asyncio
import json
import logging
import re
import time
import subprocess
import sys
import importlib.util
import tempfile
import shutil
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tiktoken
from httpx import Timeout
from pydantic import BaseModel, Field, PrivateAttr, ConfigDict, create_model

from app.schema.codeRequest import ToolDefinition, AgentConfig
from app.utils.AiCodeUtil import call_siliconflow

logger = logging.getLogger(__name__)


# ==================== 进度回调类型 ====================

class ProgressType(str, Enum):
    """进度回调类型枚举"""
    STEP_START = "step_start"
    STEP_END = "step_end"
    FILE_CREATE_START = "file_create_start"
    FILE_CREATED = "file_created"
    FILE_SKIPPED = "file_skipped"
    FILE_ERROR = "file_error"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    VALIDATION = "validation"
    VALIDATION_PROGRESS = "validation_progress"
    VALIDATION_COMPLETE = "validation_complete"
    FILE_VALIDATION = "file_validation"
    DEPENDENCY_CHECK = "dependency_check"
    STRUCTURE_CHECK = "structure_check"
    COMPLETE = "complete"
    ERROR = "error"
    STATUS = "status"


# ==================== Token编码器 ====================

class TokenEncoder:
    def __init__(self, model_name: str):
        logger.info(f"初始化TokenEncoder，模型: {model_name}")
        self.model_name = model_name
        self._encoder = self._select_encoder()
        logger.debug(f"选择的编码器: {self._encoder.name}")

    def _select_encoder(self) -> tiktoken.Encoding:
        model_lower = self.model_name.lower()
        if "deepseek" in model_lower or "qwen" in model_lower:
            return tiktoken.get_encoding("cl100k_base")
        elif any(x in model_lower for x in ["gpt-4", "gpt-3.5"]):
            return tiktoken.encoding_for_model(self.model_name)
        return tiktoken.get_encoding("cl100k_base")

    def encode(self, text: str) -> List[int]:
        logger.debug(f"编码文本，长度: {len(text)} 字符")
        return self._encoder.encode(text)

    def count_tokens(self, text: str) -> int:
        """快速计算token数量"""
        token_count = len(self._encoder.encode(text))
        logger.debug(f"计算Token数量: {token_count}")
        return token_count


# ==================== 工具注册器 ====================

class ToolRegistry:
    _tool: Dict[str, ToolDefinition] = {}

    @classmethod
    def register(cls, name: str, description: str):
        logger.info(f"注册工具: {name} - {description}")

        def decorator(func: Callable):
            import inspect
            sig = inspect.signature(func)
            fields = {}
            for param_name, param in sig.parameters.items():
                if param.annotation == inspect.Parameter.empty:
                    raise ValueError(f"参数 {param_name} 必须标注类型")
                default = param.default if param.default != inspect.Parameter.empty else ...
                fields[param_name] = (param.annotation, default)
            model = create_model(f"{name}Args", **fields)
            cls._tool[name] = ToolDefinition(
                name=name,
                func=func,
                description=description,
                parameters=model
            )
            logger.debug(f"工具 {name} 注册成功，参数模型已创建")
            return func

        return decorator

    @classmethod
    def get_schema(cls) -> List[Dict]:
        logger.debug(f"获取工具schema，共有 {len(cls._tool)} 个工具")
        schemas = []
        for tool in cls._tool.values():
            try:
                # 获取Pydantic模型的schema
                params_schema = tool.parameters.schema()
                logger.debug(f"工具 {tool.name} 的schema: {json.dumps(params_schema, ensure_ascii=False)[:200]}...")
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": params_schema
                    }
                })
            except Exception as e:
                logger.error(f"获取工具 {tool.name} 的schema失败: {str(e)}")
        return schemas

    @classmethod
    def get(cls, name):
        tool = cls._tool.get(name)
        logger.debug(f"获取工具 {name}: {'找到' if tool else '未找到'}")
        return tool


# ==================== 验证相关类型和模型 ====================

class ValidationType(str, Enum):
    """验证类型枚举"""
    SYNTAX_CHECK = "syntax_check"
    IMPORT_CHECK = "import_check"
    RUNTIME_CHECK = "runtime_check"
    DEPENDENCY_CHECK = "dependency_check"
    SECURITY_CHECK = "security_check"


class ValidationResult(BaseModel):
    """验证结果模型"""
    file_path: str
    validation_type: ValidationType
    success: bool
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


# ==================== 代码验证器 ====================

class CodeValidator:
    """代码验证器，负责验证Python代码的正确性"""

    def __init__(self, project_path: Path, config: AgentConfig):
        self.project_path = project_path
        self.config = config
        self._installed_packages = self._get_installed_packages()
        self._standard_lib_modules = self._get_standard_library_modules()

    def _get_installed_packages(self) -> set:
        """获取已安装的包"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                check=False
            )
            packages = set()
            for line in result.stdout.splitlines():
                if '==' in line:
                    packages.add(line.split('==')[0].lower().replace('-', '_'))
            return packages
        except Exception as e:
            logger.warning(f"获取已安装包失败: {e}")
            return set()

    def _get_standard_library_modules(self) -> set:
        """获取Python标准库模块"""
        try:
            import sys
            standard_lib = set()
            for name in sys.stdlib_module_names:
                standard_lib.add(name)
            return standard_lib
        except Exception as e:
            logger.warning(f"获取标准库模块失败: {e}")
            return set()

    async def validate_python_file(self, file_path: Path) -> ValidationResult:
        """验证单个Python文件"""
        logger.info(f"开始验证Python文件: {file_path}")

        if not file_path.exists():
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SYNTAX_CHECK,
                success=False,
                issues=["文件不存在"]
            )

        if not file_path.suffix == '.py':
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SYNTAX_CHECK,
                success=True,
                issues=["非Python文件，跳过语法检查"]
            )

        # 执行所有验证
        syntax_result = await self._validate_syntax(file_path)
        import_result = await self._validate_imports(file_path)
        runtime_result = await self._validate_runtime(file_path)
        security_result = await self._validate_security(file_path)

        # 合并结果
        all_issues = []
        all_warnings = []

        for result in [syntax_result, import_result, runtime_result, security_result]:
            all_issues.extend(result.issues)
            all_warnings.extend(result.warnings)

        success = all(not result.issues for result in [syntax_result, import_result, runtime_result])

        return ValidationResult(
            file_path=str(file_path),
            validation_type=ValidationType.SYNTAX_CHECK,
            success=success,
            issues=all_issues,
            warnings=all_warnings,
            details={
                "syntax_check": syntax_result.dict(),
                "import_check": import_result.dict(),
                "runtime_check": runtime_result.dict(),
                "security_check": security_result.dict()
            }
        )

    async def _validate_syntax(self, file_path: Path) -> ValidationResult:
        """验证Python语法"""
        logger.debug(f"验证语法: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 基本语法检查
            try:
                ast.parse(content)
            except SyntaxError as e:
                return ValidationResult(
                    file_path=str(file_path),
                    validation_type=ValidationType.SYNTAX_CHECK,
                    success=False,
                    issues=[f"语法错误: {e.msg} (行: {e.lineno}, 列: {e.offset})"]
                )

            # 额外的AST检查
            issues = []
            warnings = []

            try:
                tree = ast.parse(content)

                # 检查未使用的导入
                issues.extend(self._check_unused_imports(tree))

                # 检查未定义的变量
                issues.extend(self._check_undefined_variables(tree))

                # 检查语法警告
                warnings.extend(self._check_syntax_warnings(tree))

            except Exception as e:
                logger.warning(f"AST分析失败: {e}")
                warnings.append(f"AST分析失败: {str(e)}")

            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SYNTAX_CHECK,
                success=len(issues) == 0,
                issues=issues,
                warnings=warnings,
                details={"ast_analysis": "completed"}
            )

        except Exception as e:
            logger.error(f"语法验证失败: {e}")
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SYNTAX_CHECK,
                success=False,
                issues=[f"语法验证失败: {str(e)}"]
            )

    async def _validate_imports(self, file_path: Path) -> ValidationResult:
        """验证导入语句"""
        logger.debug(f"验证导入: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            issues = []
            warnings = []
            imports_found = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports_found.append(alias.name)

                        # 检查是否为标准库
                        if not self._is_importable(alias.name):
                            if alias.name not in self._standard_lib_modules:
                                issues.append(f"无法导入的模块: {alias.name}")

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports_found.append(node.module)

                        if not self._is_importable(node.module):
                            if node.module not in self._standard_lib_modules:
                                issues.append(f"无法导入的模块: {node.module}")

            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.IMPORT_CHECK,
                success=len(issues) == 0,
                issues=issues,
                warnings=warnings,
                details={"imports_checked": imports_found}
            )

        except Exception as e:
            logger.error(f"导入验证失败: {e}")
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.IMPORT_CHECK,
                success=False,
                issues=[f"导入验证失败: {str(e)}"]
            )

    async def _validate_runtime(self, file_path: Path) -> ValidationResult:
        """运行时验证（安全执行）"""
        logger.debug(f"运行时验证: {file_path}")

        if not self.config.enable_runtime_validation:
            logger.debug("运行时验证已禁用")
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.RUNTIME_CHECK,
                success=True,
                issues=[],
                warnings=["运行时验证已禁用"]
            )

        try:
            # 在临时目录中执行验证
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_file = Path(temp_dir) / file_path.name

                # 复制文件到临时目录
                shutil.copy2(file_path, temp_file)

                # 执行Python文件（带有超时）
                cmd = [sys.executable, "-c", f"import ast; exec(open(r'{temp_file}').read())"]

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,  # 10秒超时
                        cwd=temp_dir
                    )

                    issues = []
                    warnings = []

                    if result.returncode != 0:
                        error_msg = result.stderr.strip()[:500]  # 截断错误信息
                        issues.append(f"运行时错误: {error_msg}")

                    # 检查标准输出中的警告
                    if result.stdout:
                        warnings.append(f"运行时输出: {result.stdout.strip()[:200]}")

                    return ValidationResult(
                        file_path=str(file_path),
                        validation_type=ValidationType.RUNTIME_CHECK,
                        success=result.returncode == 0,
                        issues=issues,
                        warnings=warnings,
                        details={
                            "returncode": result.returncode,
                            "stderr": result.stderr[:200],
                            "stdout": result.stdout[:200]
                        }
                    )

                except subprocess.TimeoutExpired:
                    return ValidationResult(
                        file_path=str(file_path),
                        validation_type=ValidationType.RUNTIME_CHECK,
                        success=False,
                        issues=["执行超时（10秒）"]
                    )

        except Exception as e:
            logger.error(f"运行时验证失败: {e}")
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.RUNTIME_CHECK,
                success=False,
                issues=[f"运行时验证失败: {str(e)}"]
            )

    async def _validate_security(self, file_path: Path) -> ValidationResult:
        """安全验证"""
        logger.debug(f"安全验证: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            issues = []
            warnings = []

            # 检查危险函数调用
            dangerous_calls = [
                'eval', 'exec', 'compile', '__import__',
                'open', 'os.system', 'subprocess.call',
                'pickle.loads', 'marshal.loads'
            ]

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in dangerous_calls:
                            warnings.append(f"使用了潜在危险函数: {node.func.id}")

                    # 检查exec/eval的使用
                    if isinstance(node.func, ast.Name) and node.func.id in ['eval', 'exec']:
                        # 检查是否使用了字符串字面量
                        if len(node.args) > 0:
                            arg = node.args[0]
                            if isinstance(arg, ast.Str):
                                warnings.append(f"直接执行字符串代码: {arg.s[:50]}...")

            # 检查硬编码的敏感信息
            sensitive_patterns = [
                (r'password\s*=\s*[\'\"].+?[\'\"]', "硬编码密码"),
                (r'api[_-]?key\s*=\s*[\'\"].+?[\'\"]', "硬编码API密钥"),
                (r'token\s*=\s*[\'\"].+?[\'\"]', "硬编码令牌"),
                (r'secret\s*=\s*[\'\"].+?[\'\"]', "硬编码密钥")
            ]

            for pattern, description in sensitive_patterns:
                import re
                if re.search(pattern, content, re.IGNORECASE):
                    warnings.append(description)

            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SECURITY_CHECK,
                success=True,  # 安全检查通常只是警告
                issues=[],
                warnings=warnings,
                details={"security_checks_performed": len(warnings)}
            )

        except Exception as e:
            logger.error(f"安全验证失败: {e}")
            return ValidationResult(
                file_path=str(file_path),
                validation_type=ValidationType.SECURITY_CHECK,
                success=True,
                warnings=[f"安全验证失败: {str(e)}"]
            )

    def _is_importable(self, module_name: str) -> bool:
        """检查模块是否可导入"""
        try:
            # 检查是否为Python标准库
            if module_name in self._standard_lib_modules:
                return True

            # 检查是否已安装
            if module_name.lower().replace('-', '_') in self._installed_packages:
                return True

            # 尝试导入
            spec = importlib.util.find_spec(module_name)
            return spec is not None

        except Exception:
            return False

    def _check_unused_imports(self, tree: ast.AST) -> List[str]:
        """检查未使用的导入"""
        issues = []

        class ImportVisitor(ast.NodeVisitor):
            def __init__(self):
                self.imports = set()
                self.used_names = set()

            def visit_Import(self, node):
                for alias in node.names:
                    self.imports.add(alias.asname or alias.name)

            def visit_ImportFrom(self, node):
                for alias in node.names:
                    self.imports.add(alias.asname or alias.name)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    self.used_names.add(node.id)

        visitor = ImportVisitor()
        visitor.visit(tree)

        unused_imports = visitor.imports - visitor.used_names
        for imp in unused_imports:
            issues.append(f"未使用的导入: {imp}")

        return issues

    def _check_undefined_variables(self, tree: ast.AST) -> List[str]:
        """检查未定义的变量"""
        issues = []

        class VariableVisitor(ast.NodeVisitor):
            def __init__(self):
                self.defined = set()
                self.undefined = set()

            def visit_FunctionDef(self, node):
                # 函数参数是已定义的
                self.defined.update(arg.arg for arg in node.args.args)
                self.generic_visit(node)

            def visit_Assign(self, node):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.defined.add(target.id)
                self.generic_visit(node)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    if node.id not in self.defined and node.id not in dir(__builtins__):
                        self.undefined.add(node.id)
                self.generic_visit(node)

        visitor = VariableVisitor()
        visitor.visit(tree)

        for var in visitor.undefined:
            issues.append(f"可能未定义的变量: {var}")

        return issues

    def _check_syntax_warnings(self, tree: ast.AST) -> List[str]:
        """检查语法警告"""
        warnings = []

        class WarningVisitor(ast.NodeVisitor):
            def visit_Compare(self, node):
                # 检查常量比较
                if isinstance(node.left, ast.Num) or isinstance(node.left, ast.Str):
                    for op, right in zip(node.ops, node.comparators):
                        if isinstance(right, ast.Num) or isinstance(right, ast.Str):
                            warnings.append("常量比较可能总是True或False")
                self.generic_visit(node)

            def visit_For(self, node):
                # 检查未使用的循环变量
                if isinstance(node.target, ast.Name):
                    warnings.append(f"循环变量 {node.target.id} 可能未使用")
                self.generic_visit(node)

        visitor = WarningVisitor()
        visitor.visit(tree)

        return warnings


# ==================== 项目验证器 ====================

class ProjectValidator:
    """支持混合策略的验证器，集成代码验证"""

    def __init__(self, project_path: Path, config: AgentConfig):
        logger.info(f"初始化ProjectValidator，项目路径: {project_path}")
        self.project_path = project_path
        self.config = config
        self.validation_report = {}
        self._semaphore = asyncio.Semaphore(config.max_concurrent_validations)
        self.code_validator = CodeValidator(project_path, config)
        logger.debug(f"并发信号量大小: {config.max_concurrent_validations}")

    async def run_full_validation(self, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """运行完整验证"""
        logger.info("开始完整项目验证")

        validation_results = {
            "runnable": True,
            "errors": [],
            "warnings": [],
            "file_validations": [],
            "dependency_check": None,
            "structure_check": None,
            "entrypoint_check": None
        }

        try:
            # 验证所有Python文件
            validation_results["file_validations"] = await self._validate_all_files(callback)

            # 检查依赖
            validation_results["dependency_check"] = await self._check_dependencies(callback)

            # 检查项目结构
            validation_results["structure_check"] = await self._check_project_structure(callback)

            # 检查入口点
            validation_results["entrypoint_check"] = await self._check_entrypoint(callback)

            # 汇总结果
            all_errors = []
            all_warnings = []

            for file_val in validation_results["file_validations"]:
                all_errors.extend(file_val.get("issues", []))
                all_warnings.extend(file_val.get("warnings", []))

            validation_results["errors"] = all_errors
            validation_results["warnings"] = all_warnings
            validation_results["runnable"] = len(all_errors) == 0

            logger.info(f"验证完成，可运行: {validation_results['runnable']}, 错误数: {len(all_errors)}")

            if callback:
                await self._send_validation_callback(callback, validation_results)

            return validation_results

        except Exception as e:
            logger.error(f"验证过程中发生错误: {str(e)}")
            validation_results.update({
                "runnable": False,
                "errors": [f"验证过程异常: {str(e)}"]
            })
            return validation_results

    async def _validate_all_files(self, callback: Optional[Callable] = None) -> List[Dict]:
        """验证所有Python文件"""
        logger.info("开始验证所有文件")

        results = []
        py_files = list(self.project_path.rglob("*.py"))

        if not py_files:
            logger.warning("项目中未找到Python文件")
            return results

        logger.info(f"找到 {len(py_files)} 个Python文件")

        if callback:
            await self._send_progress_callback(
                callback,
                "开始文件验证",
                {"total_files": len(py_files), "current_file": 0}
            )

        # 并发验证文件
        tasks = []
        for i, file_path in enumerate(py_files):
            task = asyncio.create_task(
                self._validate_single_file(file_path, i, len(py_files), callback),
                name=f"validate_{file_path.name}"
            )
            tasks.append(task)

        # 限制并发数
        batch_size = self.config.max_concurrent_validations
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)

            if callback:
                await self._send_progress_callback(
                    callback,
                    "批量文件验证完成",
                    {"completed": min(i + batch_size, len(py_files)), "total": len(py_files)}
                )

        return results

    async def _validate_single_file(
            self,
            file_path: Path,
            index: int,
            total: int,
            callback: Optional[Callable] = None
    ) -> Dict:
        """验证单个文件"""
        logger.debug(f"验证文件 {index + 1}/{total}: {file_path}")

        if callback:
            await self._send_progress_callback(
                callback,
                f"正在验证文件: {file_path.name}",
                {"current_file": index + 1, "total_files": total, "file_path": str(file_path)}
            )

        async with self._semaphore:
            validation_result = await self.code_validator.validate_python_file(file_path)

            result_dict = validation_result.dict()

            if callback and not validation_result.success:
                await self._send_progress_callback(
                    callback,
                    f"文件验证失败: {file_path.name}",
                    {
                        "file_path": str(file_path),
                        "issues": validation_result.issues,
                        "warnings": validation_result.warnings
                    }
                )

            logger.debug(f"文件验证完成: {file_path} - 成功: {validation_result.success}")
            return result_dict

    async def _check_dependencies(self, callback: Optional[Callable] = None) -> Dict:
        """检查项目依赖"""
        logger.info("检查项目依赖")

        requirements_file = self.project_path / "requirements.txt"
        results = {
            "has_requirements": False,
            "installed": [],
            "missing": [],
            "version_mismatches": []
        }

        if not requirements_file.exists():
            logger.warning("未找到requirements.txt文件")
            if callback:
                await self._send_progress_callback(
                    callback,
                    "未找到requirements.txt文件",
                    {"warning": "项目缺少依赖声明文件"}
                )
            return results

        results["has_requirements"] = True

        try:
            with open(requirements_file, 'r', encoding='utf-8') as f:
                requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

            for req in requirements:
                # 简单的依赖检查
                pkg_name = req.split('==')[0].split('>=')[0].split('<=')[0].strip()
                pkg_name_normalized = pkg_name.lower().replace('-', '_')

                if pkg_name_normalized in self.code_validator._installed_packages:
                    results["installed"].append(req)
                else:
                    results["missing"].append(req)

            logger.info(f"依赖检查完成: 已安装 {len(results['installed'])}, 缺失 {len(results['missing'])}")

            if callback:
                await self._send_progress_callback(
                    callback,
                    "依赖检查完成",
                    results
                )

        except Exception as e:
            logger.error(f"依赖检查失败: {e}")
            results["error"] = str(e)

        return results

    async def _check_project_structure(self, callback: Optional[Callable] = None) -> Dict:
        """检查项目结构"""
        logger.info("检查项目结构")

        results = {
            "has_readme": False,
            "has_main": False,
            "has_setup": False,
            "has_tests": False,
            "structure_issues": []
        }

        # 检查README
        readme_patterns = ["README.md", "README.rst", "README.txt"]
        for pattern in readme_patterns:
            if (self.project_path / pattern).exists():
                results["has_readme"] = True
                break

        # 检查主文件
        main_patterns = ["main.py", "app.py", "run.py", "__main__.py"]
        for pattern in main_patterns:
            if (self.project_path / pattern).exists():
                results["has_main"] = True
                break

        # 检查setup文件
        setup_patterns = ["setup.py", "setup.cfg", "pyproject.toml"]
        for pattern in setup_patterns:
            if (self.project_path / pattern).exists():
                results["has_setup"] = True
                break

        # 检查测试目录
        test_dirs = ["tests", "test"]
        for test_dir in test_dirs:
            if (self.project_path / test_dir).exists():
                results["has_tests"] = True
                break

        # 报告结构问题
        if not results["has_readme"]:
            results["structure_issues"].append("缺少README文档")
        if not results["has_main"]:
            results["structure_issues"].append("未找到主程序文件")

        logger.info(f"项目结构检查完成: {results}")

        if callback:
            await self._send_progress_callback(
                callback,
                "项目结构检查完成",
                results
            )

        return results

    async def _check_entrypoint(self, callback: Optional[Callable] = None) -> Dict:
        """检查项目入口点"""
        logger.info("检查项目入口点")

        results = {
            "entrypoint_found": False,
            "entrypoint_file": None,
            "executable": False,
            "issues": []
        }

        # 寻找可能的入口点
        entrypoint_files = ["main.py", "app.py", "run.py"]

        for file_name in entrypoint_files:
            file_path = self.project_path / file_name
            if file_path.exists():
                results["entrypoint_found"] = True
                results["entrypoint_file"] = file_name

                # 检查文件是否可执行
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_line = f.readline()

                    # 检查是否有shebang
                    if first_line.startswith('#!'):
                        results["executable"] = True

                    # 检查是否有if __name__ == "__main__"
                    content = file_path.read_text(encoding='utf-8')
                    if 'if __name__ == "__main__"' in content:
                        results["executable"] = True

                    break
                except Exception as e:
                    results["issues"].append(f"检查入口点失败: {str(e)}")

        if not results["entrypoint_found"]:
            results["issues"].append("未找到项目入口点文件")

        logger.info(f"入口点检查完成: {results}")

        if callback:
            await self._send_progress_callback(
                callback,
                "入口点检查完成",
                results
            )

        return results

    async def _send_progress_callback(self, callback: Callable, message: str, data: Dict):
        """发送进度回调"""
        if callback:
            try:
                progress_data = {
                    "type": "validation_progress",
                    "message": message,
                    **data,
                    "timestamp": time.time()
                }
                callback(json.dumps(progress_data, ensure_ascii=False))
            except Exception as e:
                logger.error(f"发送验证进度回调失败: {e}")

    async def _send_validation_callback(self, callback: Callable, validation_results: Dict):
        """发送验证完成回调"""
        if callback:
            try:
                progress_data = {
                    "type": "validation_complete",
                    "message": "项目验证完成",
                    "runnable": validation_results["runnable"],
                    "error_count": len(validation_results["errors"]),
                    "warning_count": len(validation_results["warnings"]),
                    "timestamp": time.time()
                }
                callback(json.dumps(progress_data, ensure_ascii=False))
            except Exception as e:
                logger.error(f"发送验证完成回调失败: {e}")


# ==================== 工具实现 ====================

_file_locks: Dict[str, asyncio.Lock] = {}


@ToolRegistry.register("create_project_file", "创建项目文件到指定路径")
async def create_project_file(
        file_path: str,
        content: str,
        overwrite: bool = False,
        session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    logger.info(f"创建项目文件: {file_path}, 覆盖: {overwrite}, 会话: {session_id}")
    logger.debug(f"文件内容长度: {len(content)} 字符")

    lock_key = session_id or "global"
    if lock_key not in _file_locks:
        _file_locks[lock_key] = asyncio.Lock()

    async with _file_locks[lock_key]:
        try:
            import aiofiles
            from pathlib import Path

            # 记录更多路径信息
            path = Path(file_path)
            logger.debug(f"解析的Path对象: {path}")
            logger.debug(f"绝对路径: {path.absolute()}")
            logger.debug(f"当前工作目录: {Path.cwd()}")

            # 检查文件是否存在
            if path.exists():
                logger.warning(f"文件已存在: {file_path}")
                logger.debug(f"文件大小: {path.stat().st_size} 字节")
                if not overwrite:
                    logger.warning(f"文件已存在且不允许覆盖: {file_path}")
                    return {"status": "skipped", "message": f"文件已存在: {file_path}"}

            # 创建目录
            logger.debug(f"创建父目录: {path.parent}")
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"父目录创建成功，是否存在: {path.parent.exists()}")

            # 写入文件
            logger.debug(f"开始写入文件: {file_path}")
            async with aiofiles.open(file_path, 'w', encoding="utf-8") as f:
                await f.write(content)

            logger.info(f"文件创建成功: {file_path}, 大小: {len(content)} 字符")

            # 验证文件是否真的创建成功
            if path.exists():
                actual_size = path.stat().st_size
                logger.debug(f"文件实际大小: {actual_size} 字节")
                if actual_size == len(content):
                    logger.debug("文件大小验证成功")
                else:
                    logger.warning(f"文件大小不匹配，预期: {len(content)}, 实际: {actual_size}")

            return {"status": "success", "file_path": str(path.resolve())}
        except Exception as e:
            logger.error(f"创建文件失败: {file_path}, 错误: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}


@ToolRegistry.register("list_directory", "列出目录结构")
async def list_directory(path: str = ".") -> str:
    logger.info(f"列出目录: {path}")
    from pathlib import Path

    def tree(p: Path, prefix: str = "") -> List[str]:
        lines = []
        if p.is_dir():
            lines.append(f"{prefix}{p.name}/")
            children = sorted(p.iterdir())
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                lines.extend(tree(child, prefix + ("    " if is_last else "│   ")))
        else:
            lines.append(f"{prefix}{p.name}")
        return lines  # 确保始终返回列表

    try:
        result = "\n".join(tree(Path(path)))
        logger.debug(f"目录列表生成成功，行数: {len(result.splitlines())}")
        return result
    except Exception as e:
        logger.error(f"列出目录失败: {path}, 错误: {str(e)}")
        return f"列出目录失败: {str(e)}"


@ToolRegistry.register("validate_file", "验证代码文件语法和逻辑")
async def validate_file(file_path: str) -> Dict[str, Any]:
    """验证单个文件的代码"""
    logger.info(f"验证文件: {file_path}")

    try:
        path = Path(file_path)
        if not path.exists():
            return {"status": "error", "message": f"文件不存在: {file_path}"}

        # 创建验证器（简化版）
        validator = CodeValidator(path.parent, AgentConfig())
        result = await validator.validate_python_file(path)

        return {
            "status": "success",
            "file_path": file_path,
            "valid": result.success,
            "issues": result.issues,
            "warnings": result.warnings,
            "details": result.details
        }

    except Exception as e:
        logger.error(f"文件验证失败: {e}")
        return {"status": "error", "message": str(e)}


@ToolRegistry.register("validate_project", "验证整个项目")
async def validate_project(project_path: str) -> Dict[str, Any]:
    """验证整个项目的代码"""
    logger.info(f"验证项目: {project_path}")

    try:
        path = Path(project_path)
        validator = ProjectValidator(path, AgentConfig())
        result = await validator.run_full_validation()

        return {
            "status": "success",
            "project_path": project_path,
            "runnable": result.get("runnable", False),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            "file_validations": result.get("file_validations", []),
            "dependency_check": result.get("dependency_check"),
            "structure_check": result.get("structure_check")
        }

    except Exception as e:
        logger.error(f"项目验证失败: {e}")
        return {"status": "error", "message": str(e)}


# ==================== 增强的ProjectGeneratorAgent ====================

class ProjectGeneratorAgent(BaseModel):
    """项目生成Agent核心（适配call_siliconflow + 动态工具注入）"""
    config: AgentConfig = Field(default_factory=AgentConfig)
    _encoder: Any = PrivateAttr(default=None)
    _callback_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        logger.info("初始化ProjectGeneratorAgent")
        super().__init__(**data)
        self._encoder = TokenEncoder(self.config.model)
        logger.debug(f"Agent配置: model={self.config.model}, timeout={self.config.timeout}")

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """估算消息Token占用"""
        total = 0
        for msg in messages:
            total += self._encoder.count_tokens(msg["content"])
            if "tool_calls" in msg:
                total += self._encoder.count_tokens(json.dumps(msg["tool_calls"]))
        logger.debug(f"Token估算: {total}")
        return total

    def _generate_tools_prompt(self, tools_schema: List[Dict]) -> str:
        """从工具schema自动生成描述文本"""
        logger.info(f"生成工具描述，共有 {len(tools_schema)} 个工具")
        parts = []
        for i, tool in enumerate(tools_schema, 1):
            func = tool["function"]
            name = func["name"]
            desc = func["description"]
            params = func["parameters"].get("properties", {})
            required = func["parameters"].get("required", [])

            param_desc = []
            for param_name, param_info in params.items():
                try:
                    # 安全地获取参数类型
                    param_type = param_info.get("type", "unknown")
                    # 如果有anyOf字段，可能是Union类型
                    if "anyOf" in param_info:
                        anyof_types = []
                        for item in param_info["anyOf"]:
                            if isinstance(item, dict):
                                item_type = item.get("type", "unknown")
                                anyof_types.append(item_type)
                            else:
                                anyof_types.append(str(item))
                        param_type = " | ".join(anyof_types)

                    is_required = param_name in required
                    param_desc.append(f"     * {param_name}: {param_type} {'(必填)' if is_required else '(可选)'}")

                except Exception as e:
                    logger.error(f"处理参数 {param_name} 失败: {str(e)}")
                    param_desc.append(f"     * {param_name}: 类型解析失败")

            parts.append(
                f"{i}. **{name}**\n"
                f"   描述: {desc}\n"
                f"   参数:\n" + "\n".join(param_desc)
            )

            logger.debug(f"工具 {name} 的描述生成完成")

        result = "\n\n".join(parts)
        logger.debug(f"工具描述生成完成，长度: {len(result)} 字符")
        return result

    async def _safe_callback(self, msg: str, callback: Optional[Callable]):
        """安全执行回调"""
        if callback:
            async with self._callback_lock:
                try:
                    callback(msg)
                except Exception as e:
                    logger.error(f"Agent回调执行失败: {str(e)}")

    async def _progress_callback(self, progress_type: ProgressType, data: Dict, callback: Optional[Callable]):
        """进度回调"""
        if callback:
            progress_data = {
                "type": progress_type.value,
                **data
            }
            progress_msg = json.dumps(progress_data, ensure_ascii=False)
            await self._safe_callback(progress_msg, callback)

    async def generate_project(
            self,
            requirement: str,
            output_dir: str = "./generated_project",
            session_id: Optional[str] = None,
            callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """生成完整项目主入口（动态工具注入）"""
        logger.info(f"开始生成项目，需求: {requirement[:100]}...")
        logger.info(f"输出目录: {output_dir}, 会话ID: {session_id}")

        # 发送开始状态
        await self._progress_callback(ProgressType.STATUS, {
            "message": "开始项目生成",
            "requirement": requirement[:100]
        }, callback)
        from pathlib import Path
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建输出目录: {output_path}")

        # 获取工具列表并生成描述
        tools_schema = ToolRegistry.get_schema()
        tools_description = self._generate_tools_prompt(tools_schema)

        # 系统提示词（精简版本）
        system_prompt = f"""你是一位资深Python软件工程师，擅长全栈开发、游戏、CLI工具、数据处理等多领域项目构建。

        **核心任务**：在 `{output_dir}` 生成**工程规范、可直接运行**的Python项目。

        ### 第一步：需求分析与分类
        在编码前，分析用户需求的关键词并**确定项目类型**：

        - **游戏类**：关键词含"游戏/pygame/图形/精灵/碰撞/键盘"
        - **Web类**：关键词含"API/接口/Web/HTTP/FastAPI/Django"
        - **CLI类**：关键词含"命令行/脚本/工具/CLI/参数"
        - **数据类**：关键词含"数据/分析/爬虫/ETL/Pandas/Excel"
        - **科学计算**：关键词含"算法/NumPy/矩阵/可视化/计算"
        - **通用脚本**：无法归入以上类别

        **你的思考应包含**：项目类型判断、技术栈选择、核心模块规划

        ---

        ### 第二步：文件创建工具说明

        #### 【可用工具列表】
        你必须使用以下工具来创建项目文件：

        {tools_description}

        ---

        ### 第三步：强制返回格式（必须遵守）

        #### 【格式A：工具调用格式】
        当你需要创建文件时，必须且只能返回以下JSON格式：
        ```json
        {{
          "tool_calls": [
            {{
              "id": "call_001",
              "function": {{
                "name": "create_project_file",
                "arguments": {{
                  "file_path": "项目相对路径/文件名",
                  "content": "文件内容",
                  "overwrite": false
                }}
              }}
            }}
          ]
        }}
        ```
        【格式B：完成信号格式】
        当所有文件创建完成后，必须且只能返回以下格式：

        ```json
        {{
          "status": "completed",
          "message": "项目生成完成，所有必要文件已创建。",
          "files_created": ["文件1", "文件2"]
        }}
        ```
        第四步：操作流程（必须按顺序）
        1. 单文件操作
        禁止一次性返回多个文件的代码
        每次只能创建一个文件
        创建完一个文件后，等待我的确认
        2. 创建顺序
        先创建主程序文件 main.py
        再创建 requirements.txt
        再创建 README.md
        最后创建其他配置文件
        3. 文件内容格式
        每个文件的代码必须完整，不要拆分。
        禁止行为
        禁止在文本中直接包含代码块（如 python）
        禁止一次性创建多个文件
        禁止返回纯文本说明而没有工具调用
        禁止在工具调用之外创建文件
        禁止跳过工具直接说"文件已创建"
        正确示例
        用户需求: "创建一个Hello World程序"
        你的正确响应:
        ```json
        {{
          "tool_calls": [
            {{
              "id": "call_001",
              "function": {{
                "name": "create_project_file",
                "arguments": {{
                  "file_path": "./projects/user_api/main.py",
                  "content": "print('Hello World')",
                  "overwrite": false
                }}
              }}
            }}
          ]
        }}
        ```
        等待我的确认后，继续下一个文件
        交互流程
        我：用户需求
        你：创建第一个文件（JSON格式）
        我：工具执行结果
        你：创建第二个文件（JSON格式）
        ... 重复直到完成
        你：最终完成信号（JSON格式）
        项目完成条件
        当且仅当你完成了以下所有文件后，才能发送完成信号：
        在项目刚开始规划时候不允许创建文件，当创建文件的时候一定要返回
        ```json
        {{
          "tool_calls": [
            {{
              "id": "call_001",
              "function": {{
                "name": "create_project_file",
                "arguments": {{
                  "file_path": "./projects/user_api/main.py",
                  "content": "print('Hello World')",
                  "overwrite": false
                }}
              }}
            }}
          ]
        }}
        ```
        来表示需要调用工具来创建文件
        main.py（主程序）
        requirements.txt（依赖）
        README.md（文档）
        其他必要的配置文件
        创建文件必须一次性输入文件的所有内容如果不一次性输入所有内容你没有第二次输入的机会，也就是content必须是这个文件的全部完整无报错代码
        重要提醒：如果你不遵守JSON格式，系统将无法解析你的响应，项目将失败,文件如果已经创建那么说明你已经创建过文件直接跳过即可。
        系统会在每次创建文件后自动返回当前目录的快照，你无需主动调用list_directory工具。
        现在开始项目生成。请先思考项目类型和需要创建哪些文件，然后开始创建第一个文件。
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"需求：{requirement}\n输出目录：{output_dir}"}
        ]

        steps = []
        total_tools_executed = 0
        logger.info(f"开始生成流程，最大步数: 40")

        # 发送总步数信息
        await self._progress_callback(ProgressType.STATUS, {
            "message": "准备开始生成",
            "total_steps": 40
        }, callback)

        while len(steps) < 40:
            current_step = len(steps) + 1
            max_steps = 40

            # 步骤开始回调
            await self._progress_callback(ProgressType.STEP_START, {
                "message": f"第 {current_step} 步开始",
                "step": current_step,
                "max_steps": max_steps
            }, callback)

            # Token守卫
            token_usage = self._estimate_tokens(messages)
            logger.debug(f"当前Token使用量: {token_usage}")
            if token_usage > self.config.max_thinking_tokens * 0.8:
                logger.warning(f"Token使用量达到阈值({self.config.max_thinking_tokens * 0.8})，进行摘要")
                await self._progress_callback(ProgressType.STATUS, {
                    "message": "Token使用量达到阈值，正在摘要历史消息",
                    "token_usage": token_usage,
                    "threshold": self.config.max_thinking_tokens * 0.8
                }, callback)
                messages = [messages[0]] + messages[-6:]
                logger.debug(f"消息列表已摘要，保留 {len(messages)} 条消息")

            # 调用LLM
            logger.info(f"调用LLM API")
            await self._progress_callback(ProgressType.STATUS, {
                "message": "正在分析需求并规划文件结构",
                "step": current_step
            }, callback)

            response = await self._call_llm(messages, stream=self.config.stream, callback=callback)

            if not response.get("choices"):
                logger.error("LLM返回无选择结果")
                await self._progress_callback(ProgressType.ERROR, {
                    "message": "LLM返回无选择结果",
                    "step": current_step
                }, callback)
                break

            choice = response["choices"][0]
            assistant_content = choice["message"]["content"]
            logger.info(f"LLM响应内容长度: {len(assistant_content)} 字符")

            # 解析工具调用
            tool_calls, pure_text = self._parse_tool_calls(assistant_content)
            logger.info(f"解析结果: 工具调用 {len(tool_calls)} 个，纯文本长度 {len(pure_text)}")

            if tool_calls:
                logger.info(f"检测到 {len(tool_calls)} 个工具调用")
                await self._progress_callback(ProgressType.STATUS, {
                    "message": f"准备执行 {len(tool_calls)} 个工具调用",
                    "step": current_step,
                    "tool_count": len(tool_calls)
                }, callback)

                # 发送每个文件创建开始回调
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    args = tool_call["function"].get("arguments", {})
                    file_path = args.get("file_path")

                    if tool_name == "create_project_file" and file_path:
                        await self._progress_callback(ProgressType.FILE_CREATE_START, {
                            "message": f"开始创建文件",
                            "step": current_step,
                            "file_path": file_path,
                            "tool_name": tool_name
                        }, callback)

                # 执行工具
                tool_messages = await self._execute_tools(tool_calls, session_id, callback)
                logger.debug(f"工具执行完成，返回 {len(tool_messages)} 条消息")

                # 检查失败和文件验证 - 重新规划逻辑
                failed_tools = []
                for msg in tool_messages:
                    try:
                        result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        status = result.get("status", "")

                        # 如果是创建文件操作，验证文件是否真的存在
                        if status == "success":
                            file_path = result.get("file_path", "")
                            if file_path:
                                # 验证文件是否存在
                                from pathlib import Path
                                file_obj = Path(file_path)
                                if not file_obj.exists():
                                    failed_tools.append({
                                        "tool_id": msg.tool_call_id,
                                        "error": f"文件创建后验证失败：文件不存在 {file_path}",
                                        "file_path": file_path
                                    })
                                    logger.error(f"文件创建验证失败：{file_path} 不存在")
                                else:
                                    # 文件存在，发送创建成功回调
                                    await self._progress_callback(ProgressType.FILE_CREATED, {
                                        "message": "文件创建成功",
                                        "step": current_step,
                                        "file_path": file_path,
                                        "file_size": file_obj.stat().st_size if file_obj.exists() else 0
                                    }, callback)
                        elif status == "error":
                            failed_tools.append({
                                "tool_id": msg.tool_call_id,
                                "error": result.get("message", "未知错误")
                            })
                        elif status == "skipped":
                            await self._progress_callback(ProgressType.FILE_SKIPPED, {
                                "message": "文件已存在，跳过创建",
                                "step": current_step,
                                "file_path": result.get("file_path", "")
                            }, callback)
                    except Exception as e:
                        logger.error(f"处理工具结果失败: {str(e)}")
                        failed_tools.append({
                            "tool_id": msg.tool_call_id if hasattr(msg, 'tool_call_id') else 'unknown',
                            "error": f"处理结果异常: {str(e)}"
                        })

                if failed_tools and len(steps) < 9:  # 只在前期允许重新规划（前9步）
                    logger.warning(f"检测到 {len(failed_tools)} 个工具执行失败")

                    # 发送错误回调
                    await self._progress_callback(ProgressType.ERROR, {
                        "message": f"检测到 {len(failed_tools)} 个工具执行失败，正在重新规划",
                        "step": current_step,
                        "error_count": len(failed_tools),
                        "errors": [tool["error"] for tool in failed_tools]
                    }, callback)

                    # 添加失败信息到对话历史，让AI重新规划
                    error_info = "\n".join([f"- {tool['error']}" for tool in failed_tools])
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({
                        "role": "system",
                        "content": f"工具执行失败，请重新规划文件创建：\n{error_info}\n\n请确保文件路径正确、目录存在，然后重新尝试。"
                    })

                    # 不记录这一步，重新循环
                    continue  # 关键：跳过后续代码，重新开始当前步骤

                # 追加历史（只有在工具执行成功时才执行到这里）
                messages.append({"role": "assistant", "content": assistant_content})
                for msg in tool_messages:
                    messages.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})

                    # 检查是否为成功的文件创建，并附加目录快照
                    try:
                        result_data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        if isinstance(result_data, dict) and result_data.get("status") == "success":
                            snapshot = await list_directory(str(output_path))
                            snapshot_msg = {
                                "role": "system",
                                "content": f"【系统提示】文件 `{result_data.get('file_path', '未知')}` 创建成功。当前项目目录状态如下：\n```\n{snapshot}\n```\n请基于以上状态规划下一步。"
                            }
                            messages.append(snapshot_msg)
                            logger.info(f"已为文件 {result_data.get('file_path')} 附加目录快照")
                    except json.JSONDecodeError:
                        # 如果工具返回内容不是JSON，则忽略
                        pass
                    except Exception as e:
                        logger.error(f"生成或附加目录快照时出错: {e}")

                steps.append({
                    "type": "tool_calls",
                    "content": pure_text,
                    "tools": [{"id": msg.tool_call_id, "result": msg.content} for msg in tool_messages]
                })
                total_tools_executed += len(tool_calls)

                # 步骤结束回调
                await self._progress_callback(ProgressType.STEP_END, {
                    "message": f"第 {current_step} 步完成",
                    "step": current_step,
                    "tools_executed": len(tool_calls),
                    "total_tools_executed": total_tools_executed,
                    "files_created": total_tools_executed
                }, callback)

                logger.info(
                    f"第 {current_step} 步完成，创建了 {len(tool_calls)} 个工具调用，累计工具调用: {total_tools_executed}")

            elif pure_text:
                # 纯文本回复
                logger.debug(f"收到纯文本回复: {pure_text[:100]}...")

                # 扩展完成检测关键词
                completion_indicators = [
                    "完成", "success", "finished", "done", "项目生成完成",
                    "所有文件已创建", "项目创建完毕", "生成完毕", "【完成】"
                ]

                has_completion = any(indicator in pure_text.lower() for indicator in completion_indicators)

                if has_completion:
                    logger.info("收到完成信号")
                    steps.append({"type": "final", "content": pure_text})

                    # 项目完成回调
                    await self._progress_callback(ProgressType.COMPLETE, {
                        "message": "项目生成完成",
                        "step": current_step,
                        "total_steps": len(steps),
                        "total_files_created": total_tools_executed,
                        "output_dir": str(output_path.resolve())
                    }, callback)
                    break
                else:
                    messages.append({"role": "assistant", "content": pure_text})
                    steps.append({"type": "message", "content": pure_text})
                    logger.debug(f"添加纯文本消息到对话历史")

                    # 步骤结束回调（对于纯文本步骤）
                    await self._progress_callback(ProgressType.STEP_END, {
                        "message": f"第 {current_step} 步完成",
                        "step": current_step,
                        "tools_executed": 0,
                        "total_tools_executed": total_tools_executed
                    }, callback)

        # 服务端验证
        validation_report = {}
        if self.config.enable_validation:
            logger.info("启用服务端验证")
            await self._progress_callback(ProgressType.VALIDATION, {
                "message": "启动服务端验证",
                "step": len(steps) + 1,
                "validation_level": self.config.validation_level
            }, callback)

            validator = ProjectValidator(output_path, self.config)
            validation_report = await validator.run_full_validation(callback)

            # 发送验证结果摘要
            if validation_report.get("runnable", True):
                error_count = len(validation_report.get("errors", []))
                warning_count = len(validation_report.get("warnings", []))

                if error_count > 0:
                    await self._progress_callback(ProgressType.VALIDATION, {
                        "message": f"验证完成，发现 {error_count} 个错误，{warning_count} 个警告",
                        "status": "completed_with_errors",
                        "errors": validation_report.get("errors", [])[:5],  # 只显示前5个错误
                        "warnings": validation_report.get("warnings", [])[:5]
                    }, callback)
                else:
                    await self._progress_callback(ProgressType.VALIDATION, {
                        "message": f"验证通过，发现 {warning_count} 个警告",
                        "status": "success",
                        "warnings": validation_report.get("warnings", [])[:5]
                    }, callback)
            else:
                missing = validation_report.get("server_environment", {}).get("missing", [])
                errors = validation_report.get("errors", [])
                logger.warning(f"验证未通过，错误: {errors}")
                await self._progress_callback(ProgressType.VALIDATION, {
                    "message": f"验证未通过，发现 {len(errors)} 个错误",
                    "status": "failed",
                    "errors": errors[:10],  # 只显示前10个错误
                    "missing_deps": missing
                }, callback)
        else:
            logger.info("验证已禁用")
            await self._progress_callback(ProgressType.VALIDATION, {
                "message": "验证已禁用",
                "status": "skipped"
            }, callback)

        result = {
            "success": len([s for s in steps if s.get("type") == "final"]) > 0,
            "steps": steps,
            "output_dir": str(output_path.resolve()),
            "total_files_created": total_tools_executed,
            "validation": validation_report
        }

        logger.info(f"项目生成完成，结果: {result['success']}, 累计工具调用: {total_tools_executed}")
        return result

    async def _call_llm(
            self,
            messages: List[Dict],
            callback: Optional[Callable[[str], None]] = None,
            stream: bool = False
    ) -> Dict[str, Any]:
        """调用LLM，支持流式和非流式"""
        logger.debug("准备调用LLM API")

        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            prompt_parts.append(f"【{role.upper()}】\n{content}")

        prompt = "\n\n".join(prompt_parts)
        logger.debug(f"构建的prompt长度: {len(prompt)} 字符")

        try:
            logger.info(f"调用SiliconFlow API，模型: {self.config.model}, 流式: {stream}")

            response_obj = await call_siliconflow(
                prompt=prompt,
                model=self.config.model,
                stream=stream,
                timeout=Timeout(self.config.timeout, connect=10.0),
                max_tokens=self.config.max_output_tokens,
                thinking_budget=self.config.max_thinking_tokens,
                temperature=self.config.temperature
            )

            if not stream:
                # 非流式：直接返回
                logger.debug(f"非流式API调用成功，响应长度: {len(str(response_obj))} 字符")
                return response_obj  # 直接返回原始响应

            # 流式：处理生成器
            full_response = ""
            full_think = ""  # 累积完整的思考内容

            logger.info("开始流式读取响应")
            chunk_count = 0

            # call_siliconflow 返回的是异步生成器，每次yield的是JSON字符串
            async for chunk_str in response_obj:
                chunk_count += 1

                if chunk_str.strip() == "[DONE]":
                    logger.debug(f"收到 [DONE] 标记，共接收 {chunk_count} 个 chunks")
                    break

                try:
                    chunk = json.loads(chunk_str)

                    # 如果是工具调用相关的chunk，累积到full_response
                    if chunk.get("choices") and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})

                        # 提取思考内容（硅基流动使用 reasoning_content 字段）
                        think_content = delta.get("reasoning_content", "")
                        # 提取回复内容
                        content = delta.get("content", "")

                        # 处理思考内容（仅在有内容时推送）
                        if think_content and callback:
                            await self._progress_callback(ProgressType.THINKING, {
                                "message": think_content
                            }, callback)

                        # 累积最终回复内容（包含可能的工具调用）
                        if content:
                            full_response += content

                except json.JSONDecodeError as e:
                    logger.debug(f"无法解析chunk: {chunk_str[:100]}, 错误: {e}")
                    continue

            logger.info(
                f"流式响应完成，共 {chunk_count} 个 chunks，思考长度: {len(full_think)}, 回复长度: {len(full_response)}")
            return {
                "choices": [{
                    "message": {
                        "content": full_response  # 只返回原始响应内容
                    }
                }]
            }

        except Exception as e:
            logger.error(f"流式API调用失败: {str(e)}")
            raise e

    def _parse_tool_calls(self, content: str) -> tuple[List[Dict], str]:
        """从LLM回复中提取工具调用，支持多种格式"""
        logger.debug("开始解析工具调用")
        logger.debug(f"原始内容前500字符: {content[:500]}")
        import re
        content_clean = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
        if content_clean != content:
            logger.debug(f"移除了 <think> 标签，清理后长度: {len(content_clean)}")
        json_block_pattern = r'```json\s*(\{\s*"tool_calls"\s*:\s*\[.*?\]\s*\})\s*```'
        json_match = re.search(json_block_pattern, content_clean, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                tool_calls = data.get("tool_calls", [])
                if tool_calls:
                    logger.info(f"从JSON代码块解析到 {len(tool_calls)} 个工具调用")
                    pure_text = re.sub(json_block_pattern, '', content_clean, flags=re.DOTALL).strip()
                    return tool_calls, pure_text
            except json.JSONDecodeError as e:
                logger.debug(f"JSON代码块解析失败: {e}")

        # 尝试2: 提取纯 JSON 对象（无代码块包裹）
        pattern = r'\{\s*"tool_calls"\s*:\s*\[.*?\]\s*\}'
        match = re.search(pattern, content_clean, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group())
                tool_calls = data.get("tool_calls", [])
                if tool_calls:
                    logger.info(f"从纯JSON解析到 {len(tool_calls)} 个工具调用")
                    pure_text = re.sub(pattern, '', content_clean, flags=re.DOTALL).strip()
                    return tool_calls, pure_text
            except json.JSONDecodeError as e:
                logger.debug(f"纯JSON解析失败: {e}")

        # 尝试3: 如果LLM直接输出了代码块，尝试提取
        direct_code_pattern = r'^(\w+\.\w+):\s*```(?:\w+)?\s*\n([\s\S]*?)\n```'
        direct_matches = re.findall(direct_code_pattern, content_clean, re.MULTILINE)

        if direct_matches:
            logger.warning("LLM未使用工具调用，直接输出了文件内容，尝试转换为工具调用")
            tool_calls = []

            for i, (filename, code_content) in enumerate(direct_matches, 1):
                file_path = f"./projects/user_api/{filename}"

                tool_call = {
                    "id": f"call_{i:03d}",
                    "function": {
                        "name": "create_project_file",
                        "arguments": {
                            "file_path": file_path,
                            "content": code_content.strip(),
                            "overwrite": False
                        }
                    }
                }
                tool_calls.append(tool_call)

            pure_text = re.sub(direct_code_pattern, '', content_clean, flags=re.MULTILINE).strip()
            return tool_calls, pure_text

        # 无工具调用
        logger.warning(f"未找到任何工具调用格式，返回纯文本（长度: {len(content_clean)}）")
        return [], content_clean

    async def _execute_tools(
            self,
            tool_calls: List[Dict],
            session_id: Optional[str],
            callback: Optional[Callable] = None
    ) -> List[Any]:
        """并发执行工具"""
        logger.info(f"并发执行 {len(tool_calls)} 个工具")
        logger.debug(f"工具调用详情: {json.dumps(tool_calls, ensure_ascii=False, indent=2)}")

        tasks = []

        for call in tool_calls:
            tool_name = call["function"]["name"]
            tool_id = call["id"]

            logger.debug(f"准备执行工具: {tool_name} (ID: {tool_id})")

            # 工具开始回调
            await self._progress_callback(ProgressType.TOOL_START, {
                "message": f"开始执行工具: {tool_name}",
                "tool_name": tool_name,
                "tool_id": tool_id
            }, callback)

            tool_def = ToolRegistry.get(tool_name)
            if not tool_def:
                logger.error(f"工具不存在: {tool_name}")
                tasks.append(self._create_error_message(tool_id, f"工具不存在: {tool_name}"))
                continue

            # 参数验证
            try:
                args = call["function"]["arguments"]
                logger.debug(f"原始参数: {args}")

                # 如果参数是字符串，尝试解析JSON
                if isinstance(args, str):
                    args = json.loads(args)
                    logger.debug(f"解析后的参数: {args}")

                if tool_name == "create_project_file":
                    args["session_id"] = session_id
                    logger.debug(f"添加session_id后的参数: {args}")

                validated_args = tool_def.parameters(**args).dict()
                logger.debug(f"工具 {tool_name} 参数验证成功: {validated_args}")
            except Exception as e:
                logger.error(f"工具 {tool_name} 参数验证失败: {str(e)}", exc_info=True)
                tasks.append(self._create_error_message(tool_id, f"参数验证失败: {str(e)}"))
                continue

            # 创建任务
            task = asyncio.create_task(
                self._run_single_tool(tool_def, validated_args, tool_id, callback),
                name=tool_name
            )
            tasks.append(task)
            logger.debug(f"创建工具任务: {tool_name}")

        logger.info(f"等待 {len(tasks)} 个工具任务完成")
        results = await asyncio.gather(*tasks)

        # 记录每个工具的执行结果
        for i, result in enumerate(results):
            logger.debug(f"工具 {i + 1} 执行结果: {result.content[:200] if hasattr(result, 'content') else result}")

            # 判断是否为创建文件且成功的工具调用
            try:
                result_content = json.loads(result.content) if isinstance(result.content, str) else result.content
                if isinstance(result_content, dict) and result_content.get("status") == "success":
                    # 获取项目根目录（这里假设为output_dir，需要您从类上下文中传递或获取）
                    # 您需要确保在执行此方法时能访问到项目根目录路径，例如 self.current_output_dir
                    project_root = self.current_output_dir or Path(".").resolve()
                    directory_snapshot = await list_directory(str(project_root))

                    # 将目录快照构建为一条特殊的系统消息
                    # 可以添加到 results 中作为一个新的"工具消息"，或者在外部处理
                    snapshot_message = type('ToolMessage', (), {
                        'tool_call_id': f"snapshot_{int(time.time())}",
                        'content': json.dumps({
                            "type": "directory_snapshot",
                            "message": "文件创建成功，当前项目目录结构如下：",
                            "snapshot": directory_snapshot
                        })
                    })()
                    # 可以将此消息也加入到 results 列表中，后续统一处理
                    # 更优的方案是在此方法外，根据 results 里的成功状态来添加快照消息到 messages
            except Exception as e:
                logger.debug(f"生成目录快照时忽略错误或非文件创建工具: {e}")

        logger.debug(f"所有工具任务完成")
        return results

    async def _run_single_tool(
            self,
            tool_def: ToolDefinition,
            args: Dict,
            tool_id: str,
            callback: Optional[Callable] = None
    ) -> Any:
        """执行单个工具"""
        logger.info(f"执行工具: {tool_def.name}, 参数: {json.dumps(args, ensure_ascii=False)[:200]}...")
        try:
            result = await tool_def.func(**args)
            logger.info(
                f"工具 {tool_def.name} 执行成功，结果: {json.dumps(result, ensure_ascii=False)[:200] if isinstance(result, dict) else str(result)[:200]}...")

            # 工具结果回调
            if callback:
                await self._progress_callback(ProgressType.TOOL_RESULT, {
                    "message": f"工具执行成功: {tool_def.name}",
                    "tool_name": tool_def.name,
                    "tool_id": tool_id,
                    "status": "success"
                }, callback)

            return type('ToolMessage', (), {
                'tool_call_id': tool_id,
                'content': json.dumps(result) if isinstance(result, dict) else str(result)
            })()

        except Exception as e:
            logger.error(f"工具 {tool_def.name} 执行失败: {str(e)}", exc_info=True)

            # 工具错误回调
            if callback:
                await self._progress_callback(ProgressType.TOOL_RESULT, {
                    "message": f"工具执行失败: {tool_def.name}",
                    "tool_name": tool_def.name,
                    "tool_id": tool_id,
                    "status": "error",
                    "error": str(e)
                }, callback)

            return type('ToolMessage', (), {
                'tool_call_id': tool_id,
                'content': f"错误: {str(e)}"
            })()

    @staticmethod
    async def _create_error_message(tool_id: str, error: str):
        """创建错误消息"""
        logger.debug(f"创建错误消息，工具ID: {tool_id}, 错误: {error}")
        return type('ToolMessage', (), {
            'tool_call_id': tool_id,
            'content': error
        })()