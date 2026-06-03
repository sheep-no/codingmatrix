"""
TestGenerator - 根据代码自动生成测试用例

功能：
1. 分析代码结构（函数/类/方法）
2. 提取函数签名和依赖
3. 构建测试提示词
4. 调用 LLM 生成测试
5. 验证测试语法
6. 返回测试代码
"""

import ast
import logging
import re
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

from app.utils import call_llm
from app.agent.dynamic_model_router import LayeredModelRouter

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    args: List[str]
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    is_async: bool = False
    is_method: bool = False
    decorators: List[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """类信息"""
    name: str
    methods: List[FunctionInfo]
    base_classes: List[str] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class FileAnalysis:
    """文件分析结果"""
    file_path: str
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    imports: List[str]
    language: str
    framework: str


class TestGenerator:
    """
    根据代码自动生成测试用例

    支持：
    - Python (pytest)
    - JavaScript/TypeScript (jest/vitest)
    - Go (go test)
    - Java (JUnit)
    """

    def __init__(self, model_name: str = "Qwen/Qwen3-8B", api_key_token: Optional[str] = None):
        self.model_name = model_name
        self.api_key_token = api_key_token
        self.model_config = LayeredModelRouter.get_model_config(model_name, task_type="generate")

    async def generate_tests(
        self,
        file_path: str,
        code_content: str,
        project_path: str,
        framework: str = "pytest",
        coverage_target: float = 0.8,
        include_edge_cases: bool = True,
    ) -> str:
        """
        生成测试代码

        Args:
            file_path: 源文件路径
            code_content: 源代码内容
            project_path: 项目根目录
            framework: 测试框架（pytest/jest/vitest/go test）
            coverage_target: 目标覆盖率
            include_edge_cases: 是否包含边界测试

        Returns:
            生成的测试代码
        """
        try:
            # 1. 分析代码结构
            analysis = self._analyze_code(file_path, code_content, framework)

            if not analysis.functions and not analysis.classes:
                logger.warning(f"未发现可测试的函数或类: {file_path}")
                return self._generate_empty_test(file_path, framework)

            # 2. 构建测试提示词
            prompt = self._build_test_prompt(
                analysis, code_content, framework, coverage_target, include_edge_cases
            )

            # 3. 调用 LLM 生成测试
            system_prompt = self._get_system_prompt(framework)

            response = await call_llm(
                model=self.model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                stream=False,
                max_tokens=self.model_config["max_tokens"],
                temperature=self.model_config["temperature"],
                api_key_token=self.api_key_token,
            )

            test_code = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not test_code:
                logger.warning("LLM 返回空测试代码")
                return self._generate_empty_test(file_path, framework)

            # 4. 清理和验证测试代码
            test_code = self._clean_test_code(test_code)
            test_code = self._validate_test_syntax(test_code, framework)

            return test_code

        except Exception as e:
            logger.error(f"测试生成失败: {e}")
            return self._generate_empty_test(file_path, framework)

    def _analyze_code(self, file_path: str, code_content: str, framework: str) -> FileAnalysis:
        """分析代码结构"""
        ext = Path(file_path).suffix.lower()

        if ext == '.py':
            return self._analyze_python(file_path, code_content, framework)
        elif ext in ('.js', '.jsx', '.ts', '.tsx'):
            return self._analyze_javascript(file_path, code_content, framework)
        elif ext == '.go':
            return self._analyze_go(file_path, code_content, framework)
        else:
            return FileAnalysis(
                file_path=file_path,
                functions=[],
                classes=[],
                imports=[],
                language="unknown",
                framework=framework,
            )

    def _analyze_python(self, file_path: str, code_content: str, framework: str) -> FileAnalysis:
        """分析 Python 代码"""
        functions = []
        classes = []
        imports = []

        try:
            tree = ast.parse(code_content)
        except SyntaxError:
            return FileAnalysis(
                file_path=file_path,
                functions=[],
                classes=[],
                imports=[],
                language="python",
                framework=framework,
            )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                func_info = FunctionInfo(
                    name=node.name,
                    args=[arg.arg for arg in node.args.args if arg.arg != 'self'],
                    return_type=ast.dump(node.returns) if node.returns else None,
                    docstring=ast.get_docstring(node),
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    decorators=[ast.dump(d) for d in node.decorator_list],
                )
                functions.append(func_info)

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_info = FunctionInfo(
                            name=item.name,
                            args=[arg.arg for arg in item.args.args if arg.arg != 'self'],
                            return_type=ast.dump(item.returns) if item.returns else None,
                            docstring=ast.get_docstring(item),
                            is_async=isinstance(item, ast.AsyncFunctionDef),
                            is_method=True,
                            decorators=[ast.dump(d) for d in item.decorator_list],
                        )
                        methods.append(method_info)

                class_info = ClassInfo(
                    name=node.name,
                    methods=methods,
                    base_classes=[ast.dump(base) for base in node.bases],
                    docstring=ast.get_docstring(node),
                )
                classes.append(class_info)

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.dump(node))

        return FileAnalysis(
            file_path=file_path,
            functions=functions,
            classes=classes,
            imports=imports,
            language="python",
            framework=framework,
        )

    def _analyze_javascript(self, file_path: str, code_content: str, framework: str) -> FileAnalysis:
        """分析 JavaScript/TypeScript 代码"""
        functions = []
        classes = []
        imports = []

        # 简单的正则分析（对于复杂代码建议使用 AST 解析器）
        # 函数声明
        func_pattern = r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(func_pattern, code_content):
            func_info = FunctionInfo(
                name=match.group(1),
                args=[arg.strip().split(':')[0].strip() for arg in match.group(2).split(',') if arg.strip()],
                is_async='async' in match.group(0),
            )
            functions.append(func_info)

        # 箭头函数
        arrow_pattern = r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>'
        for match in re.finditer(arrow_pattern, code_content):
            func_info = FunctionInfo(
                name=match.group(1),
                args=[arg.strip().split(':')[0].strip() for arg in match.group(2).split(',') if arg.strip()],
                is_async='async' in match.group(0),
            )
            functions.append(func_info)

        # 类声明
        class_pattern = r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?'
        for match in re.finditer(class_pattern, code_content):
            class_info = ClassInfo(
                name=match.group(1),
                methods=[],
                base_classes=[match.group(2)] if match.group(2) else [],
            )
            classes.append(class_info)

        return FileAnalysis(
            file_path=file_path,
            functions=functions,
            classes=classes,
            imports=imports,
            language="javascript",
            framework=framework,
        )

    def _analyze_go(self, file_path: str, code_content: str, framework: str) -> FileAnalysis:
        """分析 Go 代码"""
        functions = []
        imports = []

        # Go 函数声明
        func_pattern = r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)(?:\s*\(([^)]*)\))?\s*\{'
        for match in re.finditer(func_pattern, code_content):
            args_str = match.group(2)
            args = []
            if args_str:
                for arg in args_str.split(','):
                    parts = arg.strip().split()
                    if len(parts) >= 1:
                        args.append(parts[0])

            func_info = FunctionInfo(
                name=match.group(1),
                args=args,
            )
            functions.append(func_info)

        return FileAnalysis(
            file_path=file_path,
            functions=functions,
            classes=[],
            imports=imports,
            language="go",
            framework=framework,
        )

    def _build_test_prompt(
        self,
        analysis: FileAnalysis,
        code_content: str,
        framework: str,
        coverage_target: float,
        include_edge_cases: bool,
    ) -> str:
        """构建测试提示词"""
        prompt_parts = [
            "请为以下代码生成完整的测试用例。",
            "",
            f"【源文件】: {analysis.file_path}",
            f"【语言】: {analysis.language}",
            f"【测试框架】: {framework}",
            f"【目标覆盖率】: {coverage_target * 100}%",
            "",
            "【源代码】:",
            f"```{analysis.language}",
            code_content[:3000],  # 限制代码长度
            "```",
            "",
            "【需要测试的函数/方法】:",
        ]

        for func in analysis.functions:
            args_str = ', '.join(func.args)
            prompt_parts.append(f"- {func.name}({args_str})")

        for cls in analysis.classes:
            prompt_parts.append(f"- class {cls.name}:")
            for method in cls.methods:
                args_str = ', '.join(method.args)
                prompt_parts.append(f"  - {method.name}({args_str})")

        prompt_parts.extend([
            "",
            "【要求】:",
            "1. 为每个函数/方法生成至少 3 个测试用例",
            "2. 包含正常输入、边界条件、错误处理测试",
            f"3. 使用 {framework} 的标准写法",
            "4. 包含必要的 mock 和 fixture",
            "5. 测试代码必须可直接运行",
            "6. 添加清晰的测试说明注释",
        ])

        if include_edge_cases:
            prompt_parts.extend([
                "",
                "【边界测试要求】:",
                "- 空输入（None/空列表/空字符串）",
                "- 极值（最大/最小/零）",
                "- 异常输入（类型错误/格式错误）",
                "- 并发场景（如适用）",
            ])

        return '\n'.join(prompt_parts)

    def _get_system_prompt(self, framework: str) -> str:
        """获取系统提示词"""
        return f"""你是一位资深测试工程师，擅长编写高质量的测试代码。

你的任务是根据提供的源代码生成完整的测试用例。

要求：
1. 测试代码必须遵循 {framework} 的最佳实践
2. 测试名称清晰描述测试目的
3. 每个测试只验证一个行为
4. 使用适当的 mock 隔离外部依赖
5. 包含充分的边界测试和异常测试
6. 测试代码必须可直接运行，无需修改

输出格式：
- 直接输出测试代码，不要解释
- 包含必要的 import 语句
- 包含必要的 fixture 定义"""

    def _clean_test_code(self, test_code: str) -> str:
        """清理测试代码"""
        # 移除 markdown 代码块标记
        test_code = re.sub(r'```(?:python|javascript|typescript|go|java)?\s*', '', test_code)
        test_code = re.sub(r'```\s*', '', test_code)

        # 移除多余的空行
        test_code = re.sub(r'\n{3,}', '\n\n', test_code)

        return test_code.strip()

    def _validate_test_syntax(self, test_code: str, framework: str) -> str:
        """验证测试语法"""
        if framework in ('pytest', 'unittest'):
            try:
                ast.parse(test_code)
            except SyntaxError as e:
                logger.warning(f"测试代码语法错误: {e}")
                # 尝试修复常见的语法问题
                test_code = self._fix_common_syntax_issues(test_code, 'python')
        elif framework in ('jest', 'vitest', 'mocha'):
            # JavaScript 语法验证需要 Node.js
            pass

        return test_code

    def _fix_common_syntax_issues(self, code: str, language: str) -> str:
        """修复常见的语法问题"""
        if language == 'python':
            # 修复缺少的冒号
            code = re.sub(r'(def\s+\w+\s*\([^)]*\))\s*\n', r'\1:\n', code)
            code = re.sub(r'(class\s+\w+[^:]*)\s*\n', r'\1:\n', code)
            code = re.sub(r'(if\s+[^:]+)\s*\n', r'\1:\n', code)
            code = re.sub(r'(for\s+[^:]+)\s*\n', r'\1:\n', code)
            code = re.sub(r'(while\s+[^:]+)\s*\n', r'\1:\n', code)

        return code

    def _generate_empty_test(self, file_path: str, framework: str) -> str:
        """生成空测试文件"""
        if framework in ('pytest', 'unittest'):
            return f'''"""
测试文件: {file_path}
自动生成的测试模板
"""

import pytest


# TODO: 添加测试用例
def test_placeholder():
    """占位测试，确保测试文件可被发现"""
    assert True
'''
        elif framework in ('jest', 'vitest', 'mocha'):
            return f'''/**
 * 测试文件: {file_path}
 * 自动生成的测试模板
 */

describe('{Path(file_path).stem}', () => {{
  // TODO: 添加测试用例
  it('should pass placeholder test', () => {{
    expect(true).toBe(true);
  }});
}});
'''
        elif framework == 'go test':
            return f'''package {Path(file_path).stem}_test

import "testing"

// TODO: 添加测试用例
func TestPlaceholder(t *testing.T) {{
    // 占位测试
}}
'''
        else:
            return f'# 测试文件: {file_path}\n# TODO: 添加测试用例\n'


# 全局实例
_test_generator: Optional[TestGenerator] = None


def get_test_generator(model_name: str = "Qwen/Qwen3-8B", api_key_token: Optional[str] = None) -> TestGenerator:
    """获取测试生成器实例"""
    global _test_generator
    if _test_generator is None:
        _test_generator = TestGenerator(model_name=model_name, api_key_token=api_key_token)
    return _test_generator
