"""
代码审查 Agent - 增强版

功能：
1. 多维度代码审查（安全、性能、规范、可维护性）
2. Skill 提示词系统
3. 自动化修复建议
4. 审查报告生成
"""
import ast
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SeverityLevel(str, Enum):
    """严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    """审查类别"""
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


@dataclass
class ReviewIssue:
    """审查问题"""
    file: str
    line: int
    column: int
    category: ReviewCategory
    severity: SeverityLevel
    message: str
    suggestion: str = ""
    code_snippet: str = ""
    skill_tag: str = ""


@dataclass
class SkillPrompt:
    """Skill 提示词"""
    id: str
    name: str
    description: str
    checks: List[str] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    weight: float = 1.0


# Skill 提示词库
SKILL_PROMPTS = {
    "production": SkillPrompt(
        id="production",
        name="生产就绪",
        description="遵循生产级代码标准",
        checks=[
            "错误处理完整性",
            "日志记录",
            "配置管理",
            "环境变量使用"
        ],
        rules=[
            "所有外部调用必须有 try-except 包裹",
            "敏感信息必须从环境变量读取",
            "必须有适当的日志记录",
            "不能有硬编码的配置值"
        ],
        weight=1.5
    ),
    "security": SkillPrompt(
        id="security",
        name="安全优先",
        description="强化安全实践",
        checks=[
            "输入验证",
            "SQL 注入防护",
            "XSS 防护",
            "认证授权",
            "敏感数据加密"
        ],
        rules=[
            "所有用户输入必须验证和清理",
            "数据库查询必须使用参数化",
            "输出必须 HTML 转义",
            "密码必须哈希存储",
            "敏感数据必须加密传输"
        ],
        weight=2.0
    ),
    "performance": SkillPrompt(
        id="performance",
        name="性能优化",
        description="高性能代码设计",
        checks=[
            "算法复杂度",
            "数据库查询优化",
            "缓存使用",
            "异步处理",
            "资源管理"
        ],
        rules=[
            "避免 N+1 查询问题",
            "大数据集必须分页",
            "重复计算结果必须缓存",
            "IO 操作必须异步",
            "及时释放资源"
        ],
        weight=1.3
    ),
    "testing": SkillPrompt(
        id="testing",
        name="测试驱动",
        description="完整测试覆盖",
        checks=[
            "单元测试覆盖率",
            "集成测试",
            "边界条件测试",
            "异常场景测试"
        ],
        rules=[
            "核心功能单元测试覆盖率>80%",
            "关键路径必须有集成测试",
            "边界条件必须测试",
            "异常情况必须测试"
        ],
        weight=1.2
    ),
    "accessibility": SkillPrompt(
        id="accessibility",
        name="无障碍",
        description="符合 WCAG 无障碍标准",
        checks=[
            "语义化 HTML",
            "ARIA 属性",
            "键盘导航",
            "颜色对比度",
            "屏幕阅读器兼容"
        ],
        rules=[
            "所有图片必须有 alt 属性",
            "表单必须有 label",
            "颜色对比度至少 4.5:1",
            "支持键盘导航",
            "使用语义化标签"
        ],
        weight=1.0
    ),
    "documentation": SkillPrompt(
        id="documentation",
        name="文档完善",
        description="详细文档和注释",
        checks=[
            "函数文档字符串",
            "类文档字符串",
            "模块文档",
            "代码注释",
            "README 文档"
        ],
        rules=[
            "所有公共函数必须有 docstring",
            "复杂逻辑必须有注释",
            "模块必须有说明文档",
            "API 必须有使用示例"
        ],
        weight=0.8
    )
}


class CodeReviewAgent:
    """代码审查 Agent"""
    
    def __init__(self, skills: Optional[List[str]] = None):
        """
        初始化审查 Agent
        
        Args:
            skills: 启用的 Skill 列表
        """
        self.skills = skills or ["production", "security"]
        self.enabled_prompts = {
            skill_id: SKILL_PROMPTS[skill_id] 
            for skill_id in self.skills 
            if skill_id in SKILL_PROMPTS
        }
        self.issues: List[ReviewIssue] = []
    
    def review_file(self, filepath: Path, language: str = "python") -> List[ReviewIssue]:
        """
        审查单个文件
        
        Args:
            filepath: 文件路径
            language: 编程语言
            
        Returns:
            审查问题列表
        """
        logger.info(f"审查文件：{filepath}")
        
        if not filepath.exists():
            logger.warning(f"文件不存在：{filepath}")
            return []
        
        content = filepath.read_text(encoding='utf-8')
        
        if language == "python":
            return self.review_python_code(content, str(filepath))
        elif language == "javascript":
            return self.review_javascript_code(content, str(filepath))
        else:
            return self.review_generic_code(content, str(filepath))
    
    def review_python_code(self, code: str, filepath: str) -> List[ReviewIssue]:
        """审查 Python 代码"""
        issues = []
        
        try:
            tree = ast.parse(code)
            
            # AST 为基础的检查
            issues.extend(self._check_python_ast(tree, filepath, code))
            
        except SyntaxError as e:
            issues.append(ReviewIssue(
                file=filepath,
                line=e.lineno or 0,
                column=e.offset or 0,
                category=ReviewCategory.STYLE,
                severity=SeverityLevel.ERROR,
                message=f"语法错误：{e.msg}",
                code_snippet=code.split('\n')[e.lineno - 1] if e.lineno else ""
            ))
        
        # 基于正则的检查
        issues.extend(self._check_python_regex(code, filepath))
        
        # Skill 特定检查
        issues.extend(self._check_python_skills(code, filepath))
        
        return issues
    
    def review_javascript_code(self, code: str, filepath: str) -> List[ReviewIssue]:
        """审查 JavaScript 代码"""
        issues = []
        
        # JavaScript 正则检查
        issues.extend(self._check_js_regex(code, filepath))
        
        # Skill 特定检查
        issues.extend(self._check_js_skills(code, filepath))
        
        return issues
    
    def review_generic_code(self, code: str, filepath: str) -> List[ReviewIssue]:
        """审查通用代码（当语言不支持详细分析时）"""
        issues = []
        
        # 通用检查
        lines = code.split('\n')
        
        # 检查文件长度
        if len(lines) > 500:
            issues.append(ReviewIssue(
                file=filepath,
                line=1,
                column=0,
                category=ReviewCategory.MAINTAINABILITY,
                severity=SeverityLevel.WARNING,
                message=f"文件过长（{len(lines)}行），建议拆分"
            ))
        
        # 检查行长度
        for i, line in enumerate(lines, 1):
            if len(line) > 150:
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=150,
                    category=ReviewCategory.STYLE,
                    severity=SeverityLevel.INFO,
                    message=f"行过长（{len(line)}字符）",
                    code_snippet=line[:100]
                ))
        
        return issues
    
    def _check_python_ast(self, tree: ast.AST, filepath: str, code: str) -> List[ReviewIssue]:
        """AST 为基础的 Python 检查"""
        issues = []
        
        for node in ast.walk(tree):
            # 检查函数定义
            if isinstance(node, ast.FunctionDef):
                # 检查函数长度
                func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                if func_lines > 50:
                    issues.append(ReviewIssue(
                        file=filepath,
                        line=node.lineno,
                        column=0,
                        category=ReviewCategory.MAINTAINABILITY,
                        severity=SeverityLevel.WARNING,
                        message=f"函数过长（{func_lines}行），建议拆分",
                        code_snippet=f"def {node.name}(...)"
                    ))
                
                # 检查 docstring
                if not ast.get_docstring(node):
                    issues.append(ReviewIssue(
                        file=filepath,
                        line=node.lineno,
                        column=0,
                        category=ReviewCategory.DOCUMENTATION,
                        severity=SeverityLevel.INFO,
                        message=f"函数缺少文档字符串",
                        code_snippet=f"def {node.name}(...)"
                    ))
            
            # 检查裸 except
            if isinstance(node, ast.ExceptHandler):
                if type(node.type) is ast.Name and node.type.id == "Exception":
                    issues.append(ReviewIssue(
                        file=filepath,
                        line=node.lineno,
                        column=0,
                        category=ReviewCategory.STYLE,
                        severity=SeverityLevel.WARNING,
                        message="避免使用裸 except",
                        suggestion="使用具体的异常类型",
                        skill_tag="production"
                    ))
            
            # 检查 eval/exec 使用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ["eval", "exec"]:
                    issues.append(ReviewIssue(
                        file=filepath,
                        line=node.lineno,
                        column=0,
                        category=ReviewCategory.SECURITY,
                        severity=SeverityLevel.CRITICAL,
                        message=f"避免使用 {node.func.id}(), 存在安全风险",
                        suggestion="使用 ast.literal_eval() 或其他安全替代方案",
                        skill_tag="security"
                    ))
        
        return issues
    
    def _check_python_regex(self, code: str, filepath: str) -> List[ReviewIssue]:
        """基于正则的 Python 检查"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 检查 print 语句
            if re.search(r'\bprint\s*\(', line) and not line.strip().startswith('#'):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.STYLE,
                    severity=SeverityLevel.INFO,
                    message="生产代码应使用 logging 而非 print",
                    suggestion="使用 logger.info() 替代",
                    skill_tag="production"
                ))
            
            # 检查 TODO/FIXME
            if re.search(r'#\s*(TODO|FIXME|XXX|HACK)', line, re.IGNORECASE):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.MAINTAINABILITY,
                    severity=SeverityLevel.INFO,
                    message="发现待处理标记",
                    code_snippet=line.strip()
                ))
            
            # 检查硬编码密码
            if re.search(r'(password|passwd|pwd)\s*=\s*["\'][^"\']+["\']', line, re.IGNORECASE):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.SECURITY,
                    severity=SeverityLevel.ERROR,
                    message="发现硬编码密码",
                    suggestion="使用环境变量或配置管理",
                    skill_tag="security"
                ))
        
        return issues
    
    def _check_python_skills(self, code: str, filepath: str) -> List[ReviewIssue]:
        """Skill 特定的 Python 检查"""
        issues = []
        
        # Security skill
        if "security" in self.skills:
            # 检查 SQL 拼接
            if re.search(r'(execute|cursor\.execute)\s*\([^)]*\+', code, re.IGNORECASE):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=0,
                    column=0,
                    category=ReviewCategory.SECURITY,
                    severity=SeverityLevel.ERROR,
                    message="SQL 查询存在注入风险",
                    suggestion="使用参数化查询"
                ))
        
        # Production skill
        if "production" in self.skills:
            # 检查 import
            if re.search(r'from\s+\.\.\s+import', code):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=0,
                    column=0,
                    category=ReviewCategory.MAINTAINABILITY,
                    severity=SeverityLevel.WARNING,
                    message="避免使用相对导入跳出包"
                ))
        
        return issues
    
    def _check_js_regex(self, code: str, filepath: str) -> List[ReviewIssue]:
        """基于正则的 JavaScript 检查"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 检查 console.log
            if re.search(r'\bconsole\.log\s*\(', line):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.STYLE,
                    severity=SeverityLevel.INFO,
                    message="生产代码应移除 console.log",
                    skill_tag="production"
                ))
            
            # 检查 eval
            if re.search(r'\beval\s*\(', line):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.SECURITY,
                    severity=SeverityLevel.CRITICAL,
                    message="避免使用 eval()",
                    skill_tag="security"
                ))
            
            # 检查 var 使用
            if re.search(r'\bvar\s+\w+\s*=', line):
                issues.append(ReviewIssue(
                    file=filepath,
                    line=i,
                    column=0,
                    category=ReviewCategory.STYLE,
                    severity=SeverityLevel.INFO,
                    message="使用 let/const 替代 var",
                    suggestion="ES6+ 使用 let 或 const"
                ))
        
        return issues
    
    def _check_js_skills(self, code: str, filepath: str) -> List[ReviewIssue]:
        """Skill 特定的 JavaScript 检查"""
        issues = []
        
        # Accessibility skill
        if "accessibility" in self.skills:
            # 检查图片 alt 属性
            img_tags = re.findall(r'<img[^>]*>', code)
            for img in img_tags:
                if 'alt=' not in img:
                    issues.append(ReviewIssue(
                        file=filepath,
                        line=0,
                        column=0,
                        category=ReviewCategory.ACCESSIBILITY,
                        severity=SeverityLevel.ERROR,
                        message="图片缺少 alt 属性",
                        skill_tag="accessibility"
                    ))
        
        return issues
    
    def get_review_report(self, output_dir: Path) -> Dict[str, Any]:
        """
        生成审查报告
        
        Args:
            output_dir: 项目输出目录
            
        Returns:
            审查报告
        """
        review_results = []
        stats = {
            "total_files": 0,
            "total_issues": 0,
            "by_severity": {
                "critical": 0,
                "error": 0,
                "warning": 0,
                "info": 0
            },
            "by_category": {}
        }
        
        # 扫描所有代码文件
        for ext in ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx"]:
            for filepath in output_dir.rglob(ext):
                stats["total_files"] += 1
                issues = self.review_file(filepath, ext[2:])
                review_results.extend(issues)
                
                # 更新统计
                for issue in issues:
                    stats["total_issues"] += 1
                    stats["by_severity"][issue.severity.value] += 1
                    
                    category = issue.category.value
                    if category not in stats["by_category"]:
                        stats["by_category"][category] = 0
                    stats["by_category"][category] += 1
        
        return {
            "passed": stats["total_issues"] == 0,
            "total_files": stats["total_files"],
            "total_issues": stats["total_issues"],
            "by_severity": stats["by_severity"],
            "by_category": stats["by_category"],
            "issues": [
                {
                    "file": issue.file,
                    "line": issue.line,
                    "category": issue.category.value,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "skill_tag": issue.skill_tag
                }
                for issue in review_results
            ]
        }


def review_project(output_dir: Path, skills: List[str] = None) -> Dict[str, Any]:
    """
    审查整个项目
    
    Args:
        output_dir: 项目目录
        skills: 启用的 Skill 列表
        
    Returns:
        审查报告
    """
    agent = CodeReviewAgent(skills=skills)
    return agent.get_review_report(output_dir)
