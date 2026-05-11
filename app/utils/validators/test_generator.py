"""
测试生成器 - 自动生成单元测试
"""
import ast
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    lineno: int
    args: List[str]
    return_annotation: Optional[str]
    docstring: Optional[str]
    is_async: bool = False
    is_method: bool = False
    class_name: Optional[str] = None


@dataclass
class TestInfo:
    """测试用例信息"""
    function_name: str
    test_name: str
    test_code: str
    description: str
    inputs: List[str]
    expected_output: Optional[str]


@dataclass
class TestGenerationResult:
    """测试生成结果"""
    success: bool
    file_path: str
    tests_generated: int
    test_code: str
    functions_analyzed: int = 0
    duration_seconds: float = 0.0


class TestGenerator:
    """测试生成器"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
    
    async def generate_unit_tests(
        self,
        file_path: Path,
        include_docstrings: bool = True
    ) -> TestGenerationResult:
        """
        为单个文件生成单元测试
        
        Args:
            file_path: 要测试的文件
            include_docstrings: 是否包含文档字符串
        
        Returns:
            TestGenerationResult: 生成结果
        """
        import time
        start_time = time.time()
        
        if not file_path.exists():
            return TestGenerationResult(
                success=False,
                file_path=str(file_path),
                tests_generated=0,
                test_code="",
                duration_seconds=0.0
            )
        
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            # 分析函数
            functions = self._analyze_functions(tree)
            logger.info(f"分析到 {len(functions)} 个函数")
            
            # 生成测试
            test_cases = []
            for func in functions:
                # 跳过测试函数和私有函数
                if func.name.startswith('test_') or func.name.startswith('_'):
                    continue
                
                test_info = self._generate_test_for_function(func)
                if test_info:
                    test_cases.append(test_info)
            
            # 生成测试代码
            test_code = self._build_test_module(
                test_cases,
                file_path,
                include_docstrings
            )
            
            return TestGenerationResult(
                success=True,
                file_path=str(file_path),
                tests_generated=len(test_cases),
                test_code=test_code,
                functions_analyzed=len(functions),
                duration_seconds=time.time() - start_time
            )
            
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"生成测试失败：{e}")
            return TestGenerationResult(
                success=False,
                file_path=str(file_path),
                tests_generated=0,
                test_code="",
                duration_seconds=time.time() - start_time
            )
    
    def _analyze_functions(self, tree: ast.AST) -> List[FunctionInfo]:
        """分析 AST 树中的函数"""
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(self._extract_function_info(node, is_async=False))
            elif isinstance(node, ast.AsyncFunctionDef):
                functions.append(self._extract_function_info(node, is_async=True))
        
        return functions
    
    def _extract_function_info(
        self,
        node,
        is_async: bool
    ) -> FunctionInfo:
        """从 AST 节点提取函数信息"""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        
        # 移除 self/cls
        if args and args[0] in ['self', 'cls']:
            args = args[1:]
        
        # 获取返回类型注解
        return_annotation = None
        if node.returns:
            return_annotation = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
        
        # 获取文档字符串
        docstring = None
        if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, (ast.Str, ast.Constant))):
            docstring = node.body[0].value.s if hasattr(node.body[0].value, 's') else node.body[0].value.value
        
        # 判断是否是方法
        is_method = False
        class_name = None
        # 查找父类（简化实现）
        for parent in ast.walk(ast.parse("")):  # 这里需要更好的实现
            pass
        
        return FunctionInfo(
            name=node.name,
            lineno=node.lineno or 0,
            args=args,
            return_annotation=return_annotation,
            docstring=docstring,
            is_async=is_async,
            is_method=is_method,
            class_name=class_name
        )
    
    def _generate_test_for_function(
        self,
        func: FunctionInfo
    ) -> Optional[TestInfo]:
        """为单个函数生成测试"""
        # 生成测试函数名
        test_name = f"test_{func.name}"
        
        # 生成测试代码
        test_lines = []
        
        # 装饰器
        if func.is_async:
            test_lines.append("@pytest.mark.asyncio")
        
        # 函数定义
        test_lines.append(f"async def {test_name}():" if func.is_async else f"def {test_name}():")
        
        # 函数文档
        if func.docstring:
            test_lines.append(f'    """测试 {func.name} 功能"""')
        
        # 准备测试数据
        test_inputs = self._generate_test_inputs(func)
        
        # 生成调用代码
        call_args = ", ".join(test_inputs)
        if func.is_method and func.class_name:
            test_lines.append(f"    instance = {func.class_name}()")
            test_lines.append(f"    result = instance.{func.name}({call_args})")
        else:
            test_lines.append(f"    result = {func.name}({call_args})")
        
        # 生成断言
        test_lines.extend(self._generate_assertions(func, "result"))
        
        test_code = "\n".join(test_lines)
        
        return TestInfo(
            function_name=func.name,
            test_name=test_name,
            test_code=test_code,
            description=f"测试 {func.name} 功能",
            inputs=test_inputs,
            expected_output=func.return_annotation
        )
    
    def _generate_test_inputs(self, func: FunctionInfo) -> List[str]:
        """生成测试输入参数"""
        inputs = []
        
        for arg in func.args:
            # 根据参数名和类型生成默认值
            if 'id' in arg.lower() or 'num' in arg.lower():
                inputs.append("1")
            elif 'name' in arg.lower() or 'str' in arg.lower():
                inputs.append('"test"')
            elif 'count' in arg.lower() or 'size' in arg.lower():
                inputs.append("10")
            elif 'list' in arg.lower() or 'items' in arg.lower():
                inputs.append("[1, 2, 3]")
            elif 'dict' in arg.lower() or 'data' in arg.lower():
                inputs.append('{"key": "value"}')
            elif 'bool' in arg.lower() or 'flag' in arg.lower():
                inputs.append("True")
            else:
                # 默认值
                inputs.append("None")
        
        return inputs
    
    def _generate_assertions(
        self,
        func: FunctionInfo,
        result_var: str
    ) -> List[str]:
        """生成断言"""
        assertions = []
        
        # 根据返回类型生成断言
        if func.return_annotation:
            if 'str' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, str)")
            elif 'int' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, int)")
            elif 'float' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, float)")
            elif 'bool' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, bool)")
            elif 'List' in func.return_annotation or 'list' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, list)")
            elif 'Dict' in func.return_annotation or 'dict' in func.return_annotation:
                assertions.append(f"    assert isinstance({result_var}, dict)")
            elif 'None' in func.return_annotation:
                assertions.append(f"    assert {result_var} is None")
            else:
                assertions.append(f"    assert {result_var} is not None")
        else:
            # 没有返回类型注解，至少检查调用成功
            assertions.append(f"    # TODO: 添加具体断言")
        
        return assertions
    
    def _build_test_module(
        self,
        test_cases: List[TestInfo],
        source_file: Path,
        include_docstrings: bool
    ) -> str:
        """构建测试模块"""
        lines = []
        
        # 文件头注释
        lines.append(f'"""')
        lines.append(f'自动生成的测试文件')
        lines.append(f'源文件：{source_file.name}')
        lines.append(f'"""')
        lines.append("")
        
        # 导入
        lines.append("import pytest")
        lines.append("import asyncio")
        lines.append("")
        
        # 导入源模块
        module_name = source_file.stem
        lines.append(f"from {module_name} import *")
        lines.append("")
        
        # 添加所有测试
        for test_case in test_cases:
            lines.append("")
            if include_docstrings:
                lines.append(f'# {test_case.description}')
            lines.append(test_case.test_code)
            lines.append("")
        
        return "\n".join(lines)
    
    async def generate_integration_tests(
        self,
        project_path: Path,
        api_base: str = "/api"
    ) -> List[str]:
        """
        生成集成测试
        
        Args:
            project_path: 项目路径
            api_base: API 基础路径
        
        Returns:
            List[str]: 测试文件内容列表
        """
        # 查找 API 定义
        # 这里可以根据具体项目结构调整
        test_files = []
        
        # API 测试模板
        api_test_template = '''
"""API 集成测试"""
import pytest
import httpx

BASE_URL = "http://localhost:8000"

async def test_{endpoint}():
    """测试 {endpoint} 端点"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{{BASE_URL}}{api_base}/{endpoint}")
        assert response.status_code == 200
'''
        
        # 示例：检测 FastAPI 路由
        api_files = list(project_path.rglob("*.py"))
        for api_file in api_files:
            try:
                content = api_file.read_text(encoding='utf-8')
                
                # 简单检测路由装饰器
                route_pattern = r'@(?:get|post|put|delete|patch)\(["\']([^"\']+)["\']'
                matches = re.findall(route_pattern, content)
                
                for endpoint in matches[:5]:  # 限制数量
                    test_code = api_test_template.format(
                        endpoint=endpoint.replace('/', '_').strip('_')
                    )
                    test_files.append(test_code)
                    
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                logger.error(f"处理文件 {api_file} 失败：{e}")
        
        return test_files
    
    def save_test_file(
        self,
        test_code: str,
        output_dir: Path,
        source_file: Path
    ) -> Path:
        """保存测试文件"""
        # 生成测试文件名
        test_filename = f"test_{source_file.stem}.py"
        test_path = output_dir / test_filename
        
        # 写入文件
        test_path.write_text(test_code, encoding='utf-8')
        logger.info(f"测试文件已保存：{test_path}")
        
        return test_path
