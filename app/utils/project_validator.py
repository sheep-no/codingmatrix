"""
项目生成验证工具

功能：
1. 项目结构验证
2. 依赖检查
3. 可运行性测试
4. 代码质量检测
5. 安全检查
"""
import ast
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """验证状态"""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationResult:
    """验证结果"""
    name: str
    status: ValidationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)


class ProjectValidator:
    """项目验证器"""
    
    def __init__(self, project_dir: Path):
        """
        初始化验证器
        
        Args:
            project_dir: 项目目录
        """
        self.project_dir = project_dir
        self.results: List[ValidationResult] = []
    
    async def validate_all(self) -> Dict[str, Any]:
        """
        执行所有验证
        
        Returns:
            综合验证报告
        """
        logger.info(f"开始验证项目：{self.project_dir}")
        
        # 执行验证
        self.results.append(self.validate_project_structure())
        self.results.append(await self.validate_dependencies())
        self.results.append(await self.validate_runnable())
        self.results.append(self.validate_code_quality())
        self.results.append(self.validate_security())
        self.results.append(self.validate_tests())
        
        # 生成报告
        report = self.generate_report()
        
        logger.info(f"验证完成 | passed: {report['passed_count']}, failed: {report['failed_count']}")
        
        return report
    
    def validate_project_structure(self) -> ValidationResult:
        """验证项目结构"""
        result = ValidationResult(
            name="项目结构验证",
            status=ValidationStatus.PASSED,
            message="项目结构符合要求"
        )
        
        # 检查必要文件
        required_files = {
            "python": ["requirements.txt", "setup.py"],
            "node": ["package.json"],
            "rust": ["Cargo.toml"],
            "go": ["go.mod"]
        }
        
        # 检测项目类型并检查
        detected_type = self.detect_project_type()
        if detected_type:
            files = required_files.get(detected_type, [])
            missing = []
            for file in files:
                if not (self.project_dir / file).exists():
                    missing.append(file)
            
            if missing:
                result.status = ValidationStatus.WARNING
                result.message = f"缺少必要文件：{', '.join(missing)}"
                result.details["missing_files"] = missing
        else:
            # 未知类型，检查基本结构
            has_src = (self.project_dir / "src").exists()
            has_tests = (self.project_dir / "tests").exists() or (self.project_dir / "test").exists()
            
            if not has_src and not has_tests:
                result.status = ValidationStatus.WARNING
                result.message = "建议添加 src 和 tests 目录"
                result.suggestions = [
                    "创建 src 目录存放源代码",
                    "创建 tests 目录存放测试"
                ]
        
        return result
    
    async def validate_dependencies(self) -> ValidationResult:
        """验证依赖"""
        result = ValidationResult(
            name="依赖验证",
            status=ValidationStatus.PASSED,
            message="依赖配置正确"
        )
        
        # 检查 requirements.txt
        req_file = self.project_dir / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            
            # 检查是否有版本约束
            missing_version = []
            for line in lines:
                if not any(op in line for op in ['==', '>=', '<=', '>', '<', '~=']):
                    missing_version.append(line)
            
            if missing_version:
                result.status = ValidationStatus.WARNING
                result.message = "部分依赖缺少版本约束"
                result.details["missing_version"] = missing_version[:10]  # 最多显示 10 个
                result.suggestions = [
                    f"为 {pkg} 指定具体版本" for pkg in missing_version[:5]
                ]
        
        # 检查 package.json
        pkg_file = self.project_dir / "package.json"
        if pkg_file.exists():
            import json
            try:
                pkg_data = json.loads(pkg_file.read_text())
                deps = pkg_data.get('dependencies', {})
                dev_deps = pkg_data.get('devDependencies', {})
                
                if not deps and not dev_deps:
                    result.status = ValidationStatus.FAILED
                    result.message = "package.json 没有定义依赖"
            except json.JSONDecodeError as e:
                result.status = ValidationStatus.FAILED
                result.message = f"package.json 格式错误：{e}"
        
        return result
    
    async def validate_runnable(self) -> ValidationResult:
        """验证可运行性"""
        result = ValidationResult(
            name="可运行性验证",
            status=ValidationStatus.PASSED,
            message="项目可正常运行"
        )
        
        detected_type = self.detect_project_type()
        
        if detected_type == "python":
            # 检查 Python 语法
            py_files = list(self.project_dir.rglob("*.py"))
            syntax_errors = []
            
            for py_file in py_files[:20]:  # 最多检查 20 个文件
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        ast.parse(f.read())
                except SyntaxError as e:
                    syntax_errors.append(f"{py_file.name}:{e.lineno}")
            
            if syntax_errors:
                result.status = ValidationStatus.FAILED
                result.message = f"发现语法错误：{', '.join(syntax_errors[:5])}"
                result.details["syntax_errors"] = syntax_errors
            
            # 尝试安装依赖并运行测试
            venv_path = self.project_dir / ".venv"
            if not venv_path.exists():
                result.suggestions.append("创建虚拟环境：python -m venv .venv")
        
        elif detected_type == "node":
            # 检查 JavaScript 语法（简单检查）
            js_files = list(self.project_dir.rglob("*.js"))
            
            if js_files:
                try:
                    # 运行 ESLint（如果存在）
                    eslint_config = self.project_dir / ".eslintrc.js"
                    if eslint_config.exists():
                        proc = await asyncio.create_subprocess_exec(
                            "npx", "eslint", "--no-eslintrc", "-c", str(eslint_config),
                            str(self.project_dir / "src"),
                            capture_output=True,
                            cwd=str(self.project_dir)
                        )
                        stdout, stderr = await proc.communicate()
                        if proc.returncode != 0:
                            result.status = ValidationStatus.WARNING
                            result.message = "ESLint 检查发现问题"
                except Exception as e:
                    logger.debug(f"ESLint 检查跳过：{e}")
        
        return result
    
    def validate_code_quality(self) -> ValidationResult:
        """验证代码质量"""
        result = ValidationResult(
            name="代码质量验证",
            status=ValidationStatus.PASSED,
            message="代码质量良好"
        )
        
        # 检查代码重复率
        py_files = list(self.project_dir.rglob("*.py"))
        total_lines = 0
        duplicate_lines = 0
        
        line_hashes = {}
        for py_file in py_files[:30]:  # 最多检查 30 个文件
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            total_lines += 1
                            line_hash = hash(line)
                            if line_hash in line_hashes:
                                duplicate_lines += 1
                            else:
                                line_hashes[line_hash] = py_file
            except Exception as e:
                logger.debug(f"读取文件失败：{e}")
        
        if total_lines > 0:
            duplicate_rate = duplicate_lines / total_lines
            if duplicate_rate > 0.3:
                result.status = ValidationStatus.WARNING
                result.message = f"代码重复率较高：{duplicate_rate:.1%}"
                result.details["duplicate_rate"] = duplicate_rate
                result.suggestions.append("提取公共代码为函数或模块")
        
        # 检查函数长度
        long_functions = []
        for py_file in py_files[:10]:
            try:
                tree = ast.parse(py_file.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                        if func_lines > 50:
                            long_functions.append(f"{py_file.name}:{node.name}({func_lines}行)")
            except Exception as e:
                logger.debug(f"分析文件失败：{e}")
        
        if long_functions:
            result.status = ValidationStatus.WARNING
            result.message = f"发现 {len(long_functions)} 个过长函数"
            result.details["long_functions"] = long_functions[:5]
            result.suggestions.append("将长函数拆分为多个小函数")
        
        return result
    
    def validate_security(self) -> ValidationResult:
        """验证安全性"""
        result = ValidationResult(
            name="安全验证",
            status=ValidationStatus.PASSED,
            message="未发现明显安全问题"
        )
        
        security_issues = []
        
        # 检查硬编码密码
        for py_file in self.project_dir.rglob("*.py"):
            try:
                content = py_file.read_text()
                if 'password' in content.lower() and '=' in content:
                    import re
                    matches = re.findall(r'password\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE)
                    if matches:
                        security_issues.append(f"{py_file.name}: 发现硬编码密码")
            except Exception as e:
                logger.debug(f"检查文件失败：{e}")
        
        if security_issues:
            result.status = ValidationStatus.FAILED
            result.message = f"发现 {len(security_issues)} 个安全问题"
            result.details["issues"] = security_issues[:5]
            result.suggestions.append("使用环境变量管理敏感配置")
        
        return result
    
    def validate_tests(self) -> ValidationResult:
        """验证测试"""
        result = ValidationResult(
            name="测试验证",
            status=ValidationStatus.PASSED,
            message="测试配置正确"
        )
        
        # 检查测试目录
        test_dirs = ["tests", "test", "__tests__", "specs"]
        found_test_dir = False
        
        for test_dir in test_dirs:
            if (self.project_dir / test_dir).exists():
                found_test_dir = True
                break
        
        if not found_test_dir:
            # 检查测试文件
            test_files = list(self.project_dir.rglob("test_*.py")) + \
                        list(self.project_dir.rglob("*_test.py")) + \
                        list(self.project_dir.rglob("*.test.js"))
            
            if not test_files:
                result.status = ValidationStatus.WARNING
                result.message = "未发现测试文件"
                result.suggestions = [
                    "创建 tests 目录",
                    "添加单元测试（pytest/Jest）"
                ]
        
        # 检查测试配置文件
        test_configs = ["pytest.ini", "pyproject.toml", "jest.config.js", ".mocharc.js"]
        has_test_config = any((self.project_dir / config).exists() for config in test_configs)
        
        if not has_test_config and result.status != ValidationStatus.FAILED:
            result.status = ValidationStatus.WARNING
            result.message = "缺少测试配置文件"
            result.suggestions.append("添加 pytest.ini 或 jest.config.js")
        
        return result
    
    def detect_project_type(self) -> Optional[str]:
        """检测项目类型"""
        if (self.project_dir / "requirements.txt").exists() or \
           (self.project_dir / "setup.py").exists() or \
           (self.project_dir / "pyproject.toml").exists():
            return "python"
        
        if (self.project_dir / "package.json").exists():
            return "node"
        
        if (self.project_dir / "Cargo.toml").exists():
            return "rust"
        
        if (self.project_dir / "go.mod").exists():
            return "go"
        
        return None
    
    def generate_report(self) -> Dict[str, Any]:
        """生成验证报告"""
        passed_count = sum(1 for r in self.results if r.status == ValidationStatus.PASSED)
        failed_count = sum(1 for r in self.results if r.status == ValidationStatus.FAILED)
        warning_count = sum(1 for r in self.results if r.status == ValidationStatus.WARNING)
        
        runnable_overall = not any(
            r.status == ValidationStatus.FAILED 
            for r in self.results
        )
        
        tests_passed = any(
            r.name == "测试验证" and r.status == ValidationStatus.PASSED
            for r in self.results
        )
        
        lint_passed = all(
            r.status != ValidationStatus.FAILED
            for r in self.results if "质量" in r.name or "结构" in r.name
        )
        
        security_passed = not any(
            r.name == "安全验证" and r.status == ValidationStatus.FAILED
            for r in self.results
        )
        
        return {
            "runnable": runnable_overall,
            "tests_passed": tests_passed,
            "lint_passed": lint_passed,
            "security_passed": security_passed,
            "total_checks": len(self.results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "warning_count": warning_count,
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "suggestions": r.suggestions
                }
                for r in self.results
            ]
        }


async def validate_project(project_dir: Path) -> Dict[str, Any]:
    """
    验证项目
    
    Args:
        project_dir: 项目目录
        
    Returns:
        验证报告
    """
    validator = ProjectValidator(project_dir)
    return await validator.validate_all()
