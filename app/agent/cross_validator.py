"""
CrossValidator - 交叉验证器

核心理念：对于关键文件（认证、核心业务逻辑），
使用两个不同的模型独立生成，然后用第三个模型作为裁判进行对比验证。

工作流程：
1. 使用 Model A 生成代码
2. 使用 Model B 生成代码
3. 使用 Model C（裁判）对比两份代码，选择更好的那个
4. 如果两份代码都有问题，要求裁判生成最终版本
"""

import json
import re
import logging
from typing import Optional, Dict, Any, List, Tuple, Set
from pathlib import Path
from dataclasses import dataclass

from app.utils import call_llm
from app.agent.json_parser import safe_parse_json
from app.agent.shared_context import SharedContext
from app.agent.refinement_loop import RefinementLoop, RefinementResult

logger = logging.getLogger(__name__)


def _load_cross_validation_config() -> Dict[str, Any]:
    """加载交叉验证配置"""
    try:
        config_path = Path(__file__).parent.parent.parent / "data" / "agent_model_config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("cross_validation", {})
    except Exception as e:
        logger.warning(f"加载交叉验证配置失败: {e}")
    return {}


@dataclass
class SymbolInfo:
    """符号信息（函数/类/变量）"""
    name: str
    symbol_type: str  # function, class, variable, constant
    file_path: str
    line_number: int
    signature: Optional[str] = None  # 函数签名
    docstring: Optional[str] = None
    is_exported: bool = True  # 是否被导出


@dataclass
class SymbolUsage:
    """符号使用信息"""
    name: str
    file_path: str
    line_number: int
    context: str  # 使用上下文


class CrossValidator:
    """
    交叉验证器 - 对关键文件进行双模型生成 + 裁判选择

    适用于：
    - 认证/授权逻辑（auth, permission, middleware）
    - 核心业务逻辑（payment, order, user_management）
    - 安全相关代码（crypto, encryption, token）
    """

    # 默认关键文件模式（硬编码兜底）
    DEFAULT_CRITICAL_PATTERNS = [
        "auth", "permission", "middleware", "guard",
        "payment", "order", "billing", "subscription",
        "crypto", "encrypt", "token", "jwt", "oauth",
        "security", "validation", "sanitizer",
        "admin", "role", "access",
    ]

    JUDGE_SYSTEM_PROMPT = """你是一位资深技术评审专家，擅长代码审查和质量评估。

你的任务：
1. 对比同一文件的两份独立实现
2. 从以下维度评估：
   - 安全性：是否有安全漏洞（SQL注入、XSS、命令注入等）
   - 正确性：逻辑是否正确，边界情况是否处理
   - 可读性：命名是否清晰，结构是否合理
   - 完整性：是否实现了所有必要功能
   - 最佳实践：是否遵循框架约定和设计模式
3. 选择更好的一份，或生成改进后的最终版本

输出格式（JSON）：
{
  "winner": "A" / "B" / "merged",
  "reason": "选择理由",
  "issues_A": ["版本A的问题"],
  "issues_B": ["版本B的问题"],
  "final_code": "最终选用的代码（仅当winner为merged时提供）"
}"""

    def __init__(self, context: SharedContext, language_adapter=None, api_key_token: Optional[str] = None):
        self.context = context
        self.language_adapter = language_adapter
        self.api_key_token = api_key_token

        # 从配置加载关键文件模式
        config = _load_cross_validation_config()
        self.enabled = config.get("enabled", True)
        self.auto_priority_1 = config.get("auto_priority_1", True)
        self.critical_patterns = config.get("critical_patterns", self.DEFAULT_CRITICAL_PATTERNS)

    def is_critical_file(self, file_path: str, file_type: str, priority: int = 5) -> bool:
        """判断文件是否需要交叉验证
        
        Args:
            file_path: 文件路径
            file_type: 文件类型
            priority: 文件优先级（1-5，1为最高）
        """
        if not self.enabled:
            return False
        
        # priority=1 自动加入交叉验证
        if self.auto_priority_1 and priority == 1:
            return True
        
        # priority<=2 且命中关键模式才触发交叉验证
        # priority>2 的文件走单模型 + refinement，不做双模型对抗
        if priority <= 2:
            path_lower = file_path.lower()
            type_lower = file_type.lower()

            for pattern in self.critical_patterns:
                if pattern in path_lower or pattern in type_lower:
                    return True

        return False

    async def validate_and_select(
        self,
        file_path: str,
        file_type: str,
        description: str,
        version_a: str,
        model_a: str,
        version_b: str,
        model_b: str,
        judge_model: str,
        project_context: Optional[Dict] = None,
        callback=None
    ) -> Tuple[str, str]:
        """
        交叉验证并选择最佳版本

        Returns:
            (最终代码, 获胜模型)
        """
        prompt = f"""请对比以下两份代码实现，选择更好的版本。

文件路径: {file_path}
文件描述: {description}

## 版本 A (由 {model_a} 生成)
```
{version_a}
```

## 版本 B (由 {model_b} 生成)
```
{version_b}
```

请从安全性、正确性、可读性、完整性、最佳实践五个维度评估，
并选择更好的版本或生成改进后的最终版本。"""

        try:
            response = await call_llm(
                model=judge_model,
                prompt=f"【SYSTEM】\n{self.JUDGE_SYSTEM_PROMPT}\n\n【USER】\n{prompt}",
                stream=False,
                max_tokens=8192,
                thinking_budget=4096,
                temperature=0.3,  # 裁判需要确定性输出
                api_key_token=self.api_key_token
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("交叉验证裁判返回空内容，默认使用版本 A")
                return version_a, model_a

            result = self._extract_json(content)
            if not result:
                logger.warning("交叉验证结果解析失败，默认使用版本 A")
                return version_a, model_a

            winner = result.get("winner", "A")
            reason = result.get("reason", "")

            if winner == "A":
                logger.info(f"交叉验证选择版本 A ({model_a}): {reason}")
                return version_a, model_a
            elif winner == "B":
                logger.info(f"交叉验证选择版本 B ({model_b}): {reason}")
                return version_b, model_b
            elif winner == "merged":
                final_code = result.get("final_code", version_a)
                logger.info(f"交叉验证选择合并版本: {reason}")
                return final_code, f"{model_a}+{model_b}"
            else:
                return version_a, model_a

        except Exception as e:
            logger.error(f"交叉验证失败: {e}，默认使用版本 A")
            return version_a, model_a

    async def cross_validate_with_refinement(
        self,
        file_path: str,
        file_type: str,
        description: str,
        content_a: str,
        model_a: str,
        content_b: str,
        model_b: str,
        judge_model: str,
        refinement_loop: RefinementLoop,
        project_context: Optional[Dict] = None,
        callback=None
    ) -> RefinementResult:
        """
        完整的交叉验证流程：生成 -> 对比 -> 修复

        Returns:
            RefinementResult
        """
        # Step 1: 裁判选择最佳版本
        selected_code, winner_model = await self.validate_and_select(
            file_path=file_path,
            file_type=file_type,
            description=description,
            version_a=content_a,
            model_a=model_a,
            version_b=content_b,
            model_b=model_b,
            judge_model=judge_model,
            project_context=project_context,
            callback=callback
        )

        # Step 2: 对选中版本进行迭代修复
        result = await refinement_loop.refine(
            file_path=file_path,
            file_type=file_type,
            description=description,
            initial_content=selected_code,
            model_name=winner_model,
            project_context=project_context,
            callback=callback
        )

        return result

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON"""
        try:
            return safe_parse_json(text)
        except ValueError:
            return None

    async def validate_cross_file_consistency(
        self,
        generated_files: Dict[str, str],
        architecture: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        跨文件一致性验证

        验证内容：
        1. 导入验证：所有导入的模块都存在
        2. 符号验证：所有引用的函数/类都存在
        3. API 契约：前端请求与后端响应一致
        4. 数据模型：模型定义与使用一致
        5. 函数签名：调用与定义一致

        Args:
            generated_files: {文件路径: 文件内容}
            architecture: 架构设计

        Returns:
            问题列表
        """
        issues = []

        # 1. 导入验证
        import_issues = self._validate_imports(generated_files)
        issues.extend(import_issues)

        # 2. 符号验证（函数/类名一致性）
        symbol_issues = self._validate_symbols(generated_files)
        issues.extend(symbol_issues)

        # 3. API 契约验证
        api_issues = self._validate_api_contracts(generated_files, architecture)
        issues.extend(api_issues)

        # 4. 数据模型一致性
        model_issues = self._validate_model_consistency(generated_files)
        issues.extend(model_issues)

        # 5. 函数签名验证
        signature_issues = self._validate_function_signatures(generated_files)
        issues.extend(signature_issues)

        return issues

    def _validate_symbols(self, files: Dict[str, str]) -> List[Dict[str, str]]:
        """
        验证符号（函数/类/变量）的一致性

        检查：
        1. 导入的符号是否在目标模块中定义
        2. 调用的函数是否在某处定义
        3. 实例化的类是否在某处定义
        """
        issues = []

        # 提取所有符号定义
        all_definitions = self._extract_all_definitions(files)

        # 提取所有符号使用
        all_usages = self._extract_all_usages(files)

        # 检查每个使用是否对应一个定义
        for usage in all_usages:
            symbol_name = usage.name

            # 跳过内置函数和常见第三方库符号
            if self._is_builtin_symbol(symbol_name):
                continue

            # 检查是否有对应的定义
            if symbol_name not in all_definitions:
                # 尝试从导入中查找
                source_file = self._find_symbol_source(symbol_name, usage.file_path, files)
                if source_file:
                    # 符号来自导入的模块，检查该模块是否有定义
                    if symbol_name not in self._extract_file_definitions(files.get(source_file, '')):
                        issues.append({
                            "type": "symbol_not_defined",
                            "file": usage.file_path,
                            "message": f"引用的符号 '{symbol_name}' 在源模块 {source_file} 中未定义",
                            "suggestion": f"在 {source_file} 中添加 '{symbol_name}' 的定义"
                        })
                else:
                    # 符号可能来自当前文件的其他位置
                    if not self._symbol_defined_in_file(symbol_name, usage.file_path, files):
                        issues.append({
                            "type": "symbol_not_found",
                            "file": usage.file_path,
                            "message": f"引用的符号 '{symbol_name}' 未在任何模块中找到定义",
                            "suggestion": f"确保 '{symbol_name}' 已定义或正确导入"
                        })

        return issues

    def _extract_all_definitions(self, files: Dict[str, str]) -> Dict[str, List[SymbolInfo]]:
        """提取所有文件中的符号定义"""
        definitions = {}
        supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}

        for file_path, content in files.items():
            if Path(file_path).suffix not in supported_extensions:
                continue

            file_defs = self._extract_file_definitions(content, file_path)
            for name, info in file_defs.items():
                if name not in definitions:
                    definitions[name] = []
                definitions[name].append(info)

        return definitions

    def _extract_file_definitions(self, content: str, file_path: str = "") -> Dict[str, SymbolInfo]:
        """提取单个文件中的符号定义"""
        definitions = {}
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('#'):
                continue

            # 匹配函数定义
            func_match = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)', stripped)
            if func_match:
                func_name = func_match.group(1)
                signature = func_match.group(2)
                definitions[func_name] = SymbolInfo(
                    name=func_name,
                    symbol_type="function",
                    file_path=file_path,
                    line_number=i,
                    signature=signature,
                    is_exported=not func_name.startswith('_')
                )
                continue

            # 匹配类定义
            class_match = re.match(r'^class\s+(\w+)(?:\s*\([^)]*\))?\s*:', stripped)
            if class_match:
                class_name = class_match.group(1)
                definitions[class_name] = SymbolInfo(
                    name=class_name,
                    symbol_type="class",
                    file_path=file_path,
                    line_number=i,
                    is_exported=not class_name.startswith('_')
                )
                continue

            # 匹配变量定义（模块级别）
            if not line.startswith(' ') and not line.startswith('\t'):
                var_match = re.match(r'^(\w+)\s*=', stripped)
                if var_match:
                    var_name = var_match.group(1)
                    # 跳过导入的模块名
                    if var_name not in ('import', 'from'):
                        definitions[var_name] = SymbolInfo(
                            name=var_name,
                            symbol_type="variable",
                            file_path=file_path,
                            line_number=i,
                            is_exported=not var_name.startswith('_')
                        )

        return definitions

    def _extract_all_usages(self, files: Dict[str, str]) -> List[SymbolUsage]:
        """提取所有文件中的符号使用"""
        usages = []
        supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}

        for file_path, content in files.items():
            if Path(file_path).suffix not in supported_extensions:
                continue

            file_usages = self._extract_file_usages(content, file_path)
            usages.extend(file_usages)

        return usages

    def _extract_file_usages(self, content: str, file_path: str) -> List[SymbolUsage]:
        """提取单个文件中的符号使用"""
        usages = []
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 跳过注释和定义
            if stripped.startswith('#') or stripped.startswith('def ') or stripped.startswith('class '):
                continue

            # 匹配函数调用
            func_calls = re.findall(r'(\w+)\s*\(', stripped)
            for func_name in func_calls:
                if not self._is_builtin_symbol(func_name):
                    usages.append(SymbolUsage(
                        name=func_name,
                        file_path=file_path,
                        line_number=i,
                        context=stripped[:100]
                    ))

            # 匹配类实例化
            class_instantiations = re.findall(r'(\w+)\s*\(', stripped)
            for class_name in class_instantiations:
                if class_name[0].isupper():  # 类名通常大写开头
                    usages.append(SymbolUsage(
                        name=class_name,
                        file_path=file_path,
                        line_number=i,
                        context=stripped[:100]
                    ))

            # 匹配属性访问（obj.attr）
            attr_accesses = re.findall(r'\.(\w+)', stripped)
            for attr_name in attr_accesses:
                if not attr_name.startswith('_'):
                    usages.append(SymbolUsage(
                        name=attr_name,
                        file_path=file_path,
                        line_number=i,
                        context=stripped[:100]
                    ))

        return usages

    def _is_builtin_symbol(self, name: str) -> bool:
        """判断是否是内置符号或常见第三方库符号"""
        builtins = {
            # Python 内置函数
            'print', 'len', 'range', 'int', 'str', 'float', 'list', 'dict', 'set',
            'tuple', 'bool', 'type', 'isinstance', 'issubclass', 'hasattr', 'getattr',
            'setattr', 'delattr', 'super', 'property', 'staticmethod', 'classmethod',
            'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'any', 'all',
            'min', 'max', 'sum', 'abs', 'round', 'pow', 'divmod', 'hex', 'oct', 'bin',
            'chr', 'ord', 'ascii', 'repr', 'format', 'input', 'open', 'id', 'hash',
            'callable', 'iter', 'next', 'slice', 'object', 'None', 'True', 'False',
            'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
            'AttributeError', 'ImportError', 'RuntimeError', 'StopIteration',
            # FastAPI/Pydantic
            'FastAPI', 'APIRouter', 'Depends', 'HTTPException', 'Query', 'Path', 'Body',
            'Header', 'UploadFile', 'File', 'Form', 'BackgroundTasks', 'Request', 'Response',
            'BaseModel', 'Field', 'validator', 'root_validator',
            # SQLAlchemy
            'Column', 'Integer', 'String', 'Boolean', 'DateTime', 'Float', 'Text', 'LargeBinary',
            'ForeignKey', 'relationship', 'backref', 'create_engine', 'sessionmaker',
            'declarative_base', 'Session', 'Base',
            # SQLAlchemy 模块路径
            'ext', 'orm', 'sql', 'types', 'engine', 'pool', 'dialects', 'declarative',
            # 常见方法
            'append', 'extend', 'insert', 'remove', 'pop', 'clear', 'sort',
            'update', 'keys', 'values', 'items', 'get', 'setdefault',
            'join', 'split', 'strip', 'replace', 'find', 'startswith', 'endswith',
            'upper', 'lower', 'title', 'capitalize',
            'read', 'write', 'close', 'flush', 'include_router',
            # 常见属性（模块别名或实例属性）
            'router', 'app', 'db', 'session', 'request', 'response',
            # 模块别名（通常在 import 时定义）
            'models', 'database', 'schemas', 'crud', 'routers',
            # 前端常见符号（Vue/React/JS）
            'ref', 'reactive', 'computed', 'watch', 'onMounted', 'onUnmounted',
            'defineComponent', 'defineProps', 'defineEmits', 'toRef', 'toRefs',
            'provide', 'inject', 'nextTick', 'useRoute', 'useRouter',
            'useState', 'useEffect', 'useContext', 'useCallback', 'useMemo',
            'createElement', 'createApp', 'createVNode', 'h', 'Fragment',
            'PropTypes', 'Component', 'PureComponent', 'memo', 'forwardRef',
            # CSS/HTML 常见属性
            'className', 'style', 'id', 'innerHTML', 'textContent',
            'addEventListener', 'removeEventListener', 'querySelector',
            'querySelectorAll', 'getElementById', 'getElementsByClassName',
            # 常见常量和配置
            'DEBUG', 'SECRET_KEY', 'DATABASE_URL', 'ALLOWED_HOSTS',
            'CORS_ORIGINS', 'API_PREFIX', 'PROJECT_NAME', 'VERSION',
            # 常见装饰器和函数
            'app', 'router', 'get', 'post', 'put', 'delete', 'patch',
            'on', 'emit', 'watch', 'unwatch', 'set', 'delete',
            # 测试相关
            'pytest', 'unittest', 'mock', 'patch', 'fixture',
            'assert', 'assertEqual', 'assertRaises', 'assertIn',
            # 日志相关
            'logger', 'logging', 'getLogger', 'info', 'debug', 'warning', 'error',
            # 异步相关
            'async', 'await', 'asyncio', 'aiohttp', 'async_session',
            # 类型注解
            'Optional', 'List', 'Dict', 'Tuple', 'Set', 'Union', 'Any',
            'Literal', 'Type', 'ClassVar', 'Final', 'Annotated',
            # 其他常见符号
            'json', 'os', 'sys', 'path', 'datetime', 'timedelta',
            'uuid', 'hashlib', 'base64', 'secrets', 'time',
            'Path', 'PurePath', 'PosixPath', 'WindowsPath',
        }
        return name in builtins

    def _find_symbol_source(self, symbol_name: str, usage_file: str, files: Dict[str, str]) -> Optional[str]:
        """查找符号的源文件"""
        content = files.get(usage_file, '')
        if not content:
            return None

        # 使用语言适配器解析导入
        if self.language_adapter:
            imports = self.language_adapter.parse_imports(content, usage_file)

            for imp in imports:
                # 检查是否导入了目标符号
                if symbol_name in imp.symbols or '*' in imp.symbols or not imp.symbols:
                    # 解析导入路径为文件路径
                    candidates = self.language_adapter.resolve_import_to_file(imp, usage_file)
                    for candidate in candidates:
                        if candidate in files:
                            return candidate

        # Fallback: 硬编码 Python 规则
        for line in content.split('\n'):
            line = line.strip()

            # from xxx import yyy
            match = re.match(r'^from\s+([\w.]+)\s+import\s+(.+)', line)
            if match:
                module = match.group(1)
                imports = [s.strip() for s in match.group(2).split(',')]

                # 检查是否导入了目标符号
                for imp in imports:
                    # 处理 from xxx import yyy as zzz
                    parts = imp.split(' as ')
                    imported_name = parts[-1].strip()
                    if imported_name == symbol_name or imported_name == '*':
                        # 使用语言适配器转换模块路径为文件路径
                        if self.language_adapter:
                            from app.agent.adapters.language_adapter import ImportInfo
                            imp_info = ImportInfo(module=module, is_relative=False)
                            candidates = self.language_adapter.resolve_import_to_file(imp_info, "")
                            for candidate in candidates:
                                if candidate in files:
                                    return candidate
                        else:
                            # Fallback: 通用检查
                            source_path = module.replace('.', '/') + '.py'
                            if source_path in files:
                                return source_path
                            init_path = module.replace('.', '/') + '/__init__.py'
                            if init_path in files:
                                return init_path

        return None

    def _symbol_defined_in_file(self, symbol_name: str, file_path: str, files: Dict[str, str]) -> bool:
        """检查符号是否在指定文件中定义"""
        content = files.get(file_path, '')
        if not content:
            return False

        definitions = self._extract_file_definitions(content)
        return symbol_name in definitions

    def _validate_function_signatures(self, files: Dict[str, str]) -> List[Dict[str, str]]:
        """
        验证函数签名一致性

        检查：
        1. 函数调用的参数是否与定义匹配
        2. 必需参数是否都已提供
        """
        issues = []

        # 提取所有函数定义
        func_definitions = {}
        for file_path, content in files.items():
            if self.language_adapter:
                defs = self.language_adapter.extract_definitions(content)
                for name, info in defs.items():
                    if info.symbol_type == "function":
                        func_definitions[name] = info
            else:
                # Fallback: 通用规则
                supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
                if Path(file_path).suffix not in supported_extensions:
                    continue
                defs = self._extract_file_definitions(content, file_path)
                for name, info in defs.items():
                    if info.symbol_type == "function":
                        func_definitions[name] = info

        # 检查函数调用
        for file_path, content in files.items():
            # 匹配函数调用
            for match in re.finditer(r'(\w+)\s*\((.*?)\)', content, re.DOTALL):
                func_name = match.group(1)
                call_args = match.group(2)

                if func_name not in func_definitions:
                    continue

                func_info = func_definitions[func_name]
                if not func_info.signature:
                    continue

                # 提取定义中的参数
                defined_params = self._extract_function_params(func_info.signature)
                # 提取调用中的参数
                call_params = self._extract_call_params(call_args)

                # 检查必需参数是否都已提供
                for param_name, param_default in defined_params.items():
                    if param_default is None and param_name not in call_params and param_name != 'self':
                        # 检查是否有 **kwargs 或 *args
                        if 'kwargs' not in ''.join(defined_params.keys()) and 'args' not in ''.join(defined_params.keys()):
                            issues.append({
                                "type": "missing_argument",
                                "file": file_path,
                                "message": f"函数 '{func_name}' 缺少必需参数: {param_name}",
                                "suggestion": f"在调用 {func_name}() 时提供参数 '{param_name}'"
                            })

        return issues

    def _extract_function_params(self, signature: str) -> Dict[str, Optional[str]]:
        """提取函数参数"""
        params = {}

        # 分割参数
        for param in signature.split(','):
            param = param.strip()
            if not param or param in ('self', 'cls'):
                continue

            # 处理默认值
            if '=' in param:
                name, default = param.split('=', 1)
                params[name.strip()] = default.strip()
            else:
                # 处理类型注解
                name = param.split(':')[0].strip()
                if name.startswith('*'):
                    name = name[1:]
                params[name] = None

        return params

    def _extract_call_params(self, call_args: str) -> Set[str]:
        """提取调用参数"""
        params = set()

        # 简单分割（不处理嵌套括号）
        for arg in call_args.split(','):
            arg = arg.strip()
            if not arg:
                continue

            # 处理关键字参数
            if '=' in arg:
                name = arg.split('=')[0].strip()
                params.add(name)
            else:
                # 位置参数（无法确定名称）
                pass

        return params

    def _validate_imports(self, files: Dict[str, str]) -> List[Dict[str, str]]:
        """验证导入语句"""
        issues = []

        for file_path, content in files.items():
            # 使用语言适配器
            if self.language_adapter:
                imports = self.language_adapter.parse_imports(content, file_path)

                for imp in imports:
                    # 跳过相对导入和第三方库
                    if imp.is_relative or not self.language_adapter.is_project_module(imp.module):
                        continue

                    # 检查导入的模块是否存在
                    candidates = self.language_adapter.resolve_import_to_file(imp, file_path)
                    exists = any(c in files for c in candidates)

                    if not exists:
                        issues.append({
                            "type": "import_error",
                            "file": file_path,
                            "message": f"导入的模块不存在: {imp.module}",
                            "suggestion": f"确保 {imp.module} 已在 file_plan 中定义"
                        })
            else:
                # Fallback: 通用导入检查
                supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
                if Path(file_path).suffix not in supported_extensions:
                    continue

                imports = self._extract_python_imports(content)

                for imp in imports:
                    # 跳过相对导入和第三方库
                    if imp.startswith('.') or self._is_third_party(imp):
                        continue

                    # 检查导入的模块是否存在
                    if not self._module_exists_in_files(imp, files):
                        issues.append({
                            "type": "import_error",
                            "file": file_path,
                            "message": f"导入的模块不存在: {imp}",
                            "suggestion": f"确保 {imp} 已在 file_plan 中定义"
                        })

        return issues

    def _extract_python_imports(self, content: str) -> List[str]:
        """提取 Python 文件中的导入"""
        imports = []

        # 匹配 import xxx 和 from xxx import yyy
        patterns = [
            r'^import\s+([\w.]+)',
            r'^from\s+([\w.]+)\s+import',
        ]

        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                continue

            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    module = match.group(1)
                    imports.append(module)

        return imports

    def _is_third_party(self, module: str) -> bool:
        """判断是否是第三方库"""
        third_party = {
            'fastapi', 'flask', 'django', 'sqlalchemy', 'pydantic',
            'uvicorn', 'gunicorn', 'requests', 'httpx', 'aiohttp',
            'numpy', 'pandas', 'torch', 'pytest', 'celery',
            'redis', 'pymongo', 'jwt', 'jose', 'passlib',
            'starlette', 'httpx', 'orjson', 'alembic',
        }
        top_level = module.split('.')[0]
        return top_level in third_party

    def _module_exists_in_files(self, module: str, files: Dict[str, str]) -> bool:
        """检查模块是否在文件中存在"""
        # 使用语言适配器
        if self.language_adapter:
            from app.agent.adapters.language_adapter import ImportInfo
            imp = ImportInfo(module=module, is_relative=False)
            candidates = self.language_adapter.resolve_import_to_file(imp, "")
            return any(c in files for c in candidates)

        # Fallback: 通用检查
        extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        pkg_path = module.replace('.', '/')

        for ext in extensions:
            file_path = f"{pkg_path}{ext}"
            if file_path in files:
                return True

        # 检查是否是包
        if self.language_adapter:
            init_file = self.language_adapter.get_package_init_file(pkg_path)
            if init_file in files:
                return True

        # 检查是否是包内的模块
        for f in files:
            if f.startswith(pkg_path + '/'):
                return True

        return False

    def _validate_api_contracts(
        self,
        files: Dict[str, str],
        architecture: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """验证 API 契约一致性"""
        issues = []

        # 提取后端 API 定义
        backend_apis = self._extract_backend_api_specs(files)

        # 提取前端 API 调用
        frontend_calls = self._extract_frontend_api_calls(files)

        # 检查前端调用的字段与后端响应是否一致
        for call in frontend_calls:
            endpoint = call['endpoint']
            file_path = call['file']
            used_fields = call.get('fields', [])

            # 查找对应的后端 API
            backend_api = self._find_matching_api(endpoint, backend_apis)
            if backend_api:
                response_fields = backend_api.get('response_fields', [])
                # 检查前端使用的字段是否在后端响应中
                for field in used_fields:
                    if field not in response_fields and response_fields:
                        issues.append({
                            "type": "api_mismatch",
                            "file": file_path,
                            "message": f"前端使用了后端未返回的字段: {field}",
                            "suggestion": f"确保后端 API {endpoint} 返回 {field} 字段"
                        })

        return issues

    def _extract_backend_api_specs(self, files: Dict[str, str]) -> List[Dict]:
        """提取后端 API 规范"""
        apis = []
        backend_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}

        for file_path, content in files.items():
            if Path(file_path).suffix not in backend_extensions:
                continue

            # 匹配 Pydantic 响应模型
            response_models = {}
            model_pattern = r'class\s+(\w+)\s*\(BaseModel\):([\s\S]*?)(?=class|\Z)'
            for match in re.finditer(model_pattern, content):
                model_name = match.group(1)
                model_body = match.group(2)
                fields = re.findall(r'(\w+)\s*:', model_body)
                response_models[model_name] = fields

            # 匹配路由定义
            route_pattern = r'@(?:app|router)\.(get|post|put|delete)\s*\(\s*["\']([^"\']+)["\'].*?response_model\s*=\s*(\w+)'
            for match in re.finditer(route_pattern, content):
                method = match.group(1).upper()
                path = match.group(2)
                model_name = match.group(3)

                apis.append({
                    'method': method,
                    'path': path,
                    'response_model': model_name,
                    'response_fields': response_models.get(model_name, []),
                    'file': file_path
                })

        return apis

    def _extract_frontend_api_calls(self, files: Dict[str, str]) -> List[Dict]:
        """提取前端 API 调用"""
        calls = []

        for file_path, content in files.items():
            if not file_path.endswith(('.js', '.ts', '.vue', '.jsx', '.tsx')):
                continue

            # 匹配 fetch/axios 调用和后续的字段访问
            patterns = [
                (r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']', 'fetch'),
                (r'axios\.\w+\s*\(\s*[`"\']([^`"\']+)[`"\']', 'axios'),
            ]

            for pattern, source in patterns:
                for match in re.finditer(pattern, content):
                    endpoint = match.group(1)
                    if '${' in endpoint:
                        continue

                    # 查找该调用附近的字段访问
                    start_pos = match.end()
                    surrounding = content[start_pos:start_pos + 500]
                    # 匹配 data.xxx 或 response.data.xxx
                    field_patterns = [
                        r'\.(\w+)\s*[,;\)\}\]]',
                        r'\["(\w+)"\]',
                    ]
                    fields = []
                    for fp in field_patterns:
                        fields.extend(re.findall(fp, surrounding))

                    calls.append({
                        'endpoint': endpoint,
                        'file': file_path,
                        'fields': list(set(fields))
                    })

        return calls

    def _find_matching_api(self, endpoint: str, apis: List[Dict]) -> Optional[Dict]:
        """查找匹配的后端 API"""

        for api in apis:
            api_path = api['path']
            # 处理路径参数
            api_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', api_path)
            if re.match(f'^{api_pattern}$', endpoint):
                return api
            # 前缀匹配
            if endpoint.startswith(api_path) or api_path.startswith(endpoint):
                return api
        return None

    def _validate_model_consistency(self, files: Dict[str, str]) -> List[Dict[str, str]]:
        """验证数据模型一致性"""
        issues = []

        # 提取所有模型定义
        model_defs = self._extract_model_definitions(files)

        # 检查模型使用是否与定义一致
        supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        for file_path, content in files.items():
            if Path(file_path).suffix not in supported_extensions:
                continue

            # 检查模型实例化的字段是否与定义一致
            for model_name, model_info in model_defs.items():
                if model_name in content:
                    defined_fields = model_info['fields']
                    # 查找模型实例化
                    init_pattern = rf'{model_name}\s*\(([\s\S]*?)\)'
                    for match in re.finditer(init_pattern, content):
                        init_body = match.group(1)
                        # 提取使用的字段
                        used_fields = re.findall(r'(\w+)\s*=', init_body)
                        for field in used_fields:
                            if field not in defined_fields and field != 'self':
                                issues.append({
                                    "type": "model_mismatch",
                                    "file": file_path,
                                    "message": f"模型 {model_name} 未定义字段: {field}",
                                    "suggestion": f"在 {model_info['file']} 中添加 {field} 字段定义"
                                })

        return issues

    def _extract_model_definitions(self, files: Dict[str, str]) -> Dict[str, Dict]:
        """提取模型定义"""
        models = {}
        supported_extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}

        for file_path, content in files.items():
            if Path(file_path).suffix not in supported_extensions:
                continue

            # Pydantic 模型
            pattern = r'class\s+(\w+)\s*\(BaseModel\):([\s\S]*?)(?=class|\Z)'
            for match in re.finditer(pattern, content):
                model_name = match.group(1)
                model_body = match.group(2)
                fields = re.findall(r'(\w+)\s*:', model_body)
                models[model_name] = {
                    'fields': fields,
                    'file': file_path,
                    'type': 'pydantic'
                }

            # SQLAlchemy 模型
            pattern = r'class\s+(\w+)\s*\([^)]*Base[^)]*\):([\s\S]*?)(?=class|\Z)'
            for match in re.finditer(pattern, content):
                model_name = match.group(1)
                model_body = match.group(2)
                fields = re.findall(r'(\w+)\s*=\s*Column', model_body)
                models[model_name] = {
                    'fields': fields,
                    'file': file_path,
                    'type': 'sqlalchemy'
                }

        return models

    async def validate_and_fix(
        self,
        generated_files: Dict[str, str],
        architecture: Dict[str, Any],
        fix_model: Optional[str] = None
    ) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
        """
        验证并修复跨文件一致性问题

        Args:
            generated_files: {文件路径: 文件内容}
            architecture: 架构设计
            fix_model: 用于修复的模型（可选）

        Returns:
            (修复后的文件, 问题列表)
        """
        # 验证
        issues = await self.validate_cross_file_consistency(generated_files, architecture)

        if not issues:
            return generated_files, []

        logger.info(f"发现 {len(issues)} 个跨文件一致性问题")

        # 自动生成缺失的模块文件
        missing_modules = self._find_missing_modules(issues)
        if missing_modules:
            generated_files = await self._generate_missing_modules(
                generated_files, missing_modules, architecture, fix_model
            )
            # 重新验证
            issues = await self.validate_cross_file_consistency(generated_files, architecture)

        # 如果没有指定修复模型，只返回问题
        if not fix_model:
            return generated_files, issues

        # 尝试使用 LLM 修复
        fixed_files = await self._fix_with_llm(generated_files, issues, fix_model)

        return fixed_files, issues

    def _find_missing_modules(self, issues: List[Dict[str, str]]) -> List[str]:
        """从问题列表中找出缺失的模块"""
        missing = set()

        for issue in issues:
            issue_type = issue.get("type", "")
            message = issue.get("message", "")

            # 查找导入错误
            if issue_type == "import_error":
                match = re.search(r"导入的模块不存在:\s*(\S+)", message)
                if match:
                    module = match.group(1)
                    missing.add(module)

            # 查找缺失的模块定义
            if issue_type == "symbol_not_defined":
                match = re.search(r"在源模块\s+(\S+)\s+中未定义", message)
                if match:
                    module = match.group(1)
                    # 转换文件路径为模块路径（移除扩展名）
                    if self.language_adapter:
                        for ext in self.language_adapter.extensions:
                            module = module.replace(ext, '')
                    else:
                        module = module.replace('.py', '')
                    module = module.replace('/', '.')
                    missing.add(module)

        return list(missing)

    async def _generate_missing_modules(
        self,
        files: Dict[str, str],
        missing_modules: List[str],
        architecture: Dict[str, Any],
        model: Optional[str] = None
    ) -> Dict[str, str]:
        """生成缺失的模块文件"""
        if not model:
            # 如果没有指定模型，使用默认内容
            extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
            default_ext = list(extensions)[0] if extensions else '.py'
            for module in missing_modules:
                file_path = module.replace('.', '/') + default_ext
                if file_path not in files:
                    files[file_path] = f'"""Module: {module}"""\n\n# TODO: Implement this module\n'
                    logger.info(f"生成缺失模块（默认内容）: {file_path}")
            return files

        # 使用 LLM 生成模块内容
        extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        default_ext = list(extensions)[0] if extensions else '.py'
        language_name = self.language_adapter.language if self.language_adapter else "Python"

        for module in missing_modules:
            file_path = module.replace('.', '/') + default_ext
            if file_path in files:
                continue

            # 收集引用该模块的文件
            referencing_files = []
            for f_path, content in files.items():
                if module in content:
                    referencing_files.append(f_path)

            # 构建提示词
            prompt = f"""请为以下 {language_name} 模块生成代码：

模块路径: {module}
项目架构: {json.dumps(architecture.get('tech_stack', []), ensure_ascii=False)}

引用该模块的文件:
{self._format_referencing_files(files, referencing_files)}

要求：
1. 生成完整的模块代码
2. 确保导出被引用的函数/类/变量
3. 遵循 {language_name} 最佳实践
4. 添加必要的类型注解（如果语言支持）

只输出代码，不要解释。"""

            try:
                response = await call_llm(
                    model=model,
                    prompt=prompt,
                    stream=False,
                    max_tokens=4096,
                    api_key_token=self.api_key_token
                )

                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    content = self._clean_code_block(content)
                    files[file_path] = content
                    logger.info(f"生成缺失模块（LLM）: {file_path}")
            except Exception as e:
                logger.error(f"生成模块 {module} 失败: {e}")
                # 使用默认内容
                files[file_path] = f'"""Module: {module}"""\n\n# TODO: Implement this module\n'

        return files

    def _format_referencing_files(self, files: Dict[str, str], referencing_files: List[str]) -> str:
        """格式化引用文件的内容"""
        parts = []
        for file_path in referencing_files:
            content = files.get(file_path, '')
            # 只取前 20 行
            lines = content.split('\n')[:20]
            parts.append(f"--- {file_path} ---\n" + '\n'.join(lines))
        return '\n\n'.join(parts)

    async def _fix_with_llm(
        self,
        files: Dict[str, str],
        issues: List[Dict[str, str]],
        model: str,
        batch_size: int = 5
    ) -> Dict[str, str]:
        """
        使用 LLM 修复问题（批量修复）

        Args:
            files: {文件路径: 文件内容}
            issues: 问题列表
            model: 修复模型
            batch_size: 每批修复的文件数量
        """

        # 按文件分组问题
        issues_by_file = {}
        for issue in issues:
            file_path = issue['file']
            if file_path not in issues_by_file:
                issues_by_file[file_path] = []
            issues_by_file[file_path].append(issue)

        fixed_files = dict(files)

        # 批量修复文件
        file_paths = list(issues_by_file.keys())
        for i in range(0, len(file_paths), batch_size):
            batch_paths = file_paths[i:i+batch_size]
            batch_files = {}

            for file_path in batch_paths:
                if file_path not in fixed_files:
                    continue
                batch_files[file_path] = {
                    "content": fixed_files[file_path],
                    "issues": issues_by_file[file_path]
                }

            if not batch_files:
                continue

            # 构建批量修复提示
            files_desc = []
            for file_path, info in batch_files.items():
                files_desc.append(f"""文件: {file_path}
问题: {json.dumps(info['issues'], ensure_ascii=False)}
代码:
```
{info['content']}
```""")

            prompt = f"""请修复以下文件中的问题。每个文件独立修复，输出格式为：
===文件路径===
修复后的完整代码
===END===

{chr(10).join(files_desc)}

请按上述格式输出所有修复后的文件代码。"""

            try:
                response = await call_llm(
                    model=model,
                    prompt=prompt,
                    stream=False,
                    max_tokens=16384,  # 增加 token 限制以支持批量修复
                    api_key_token=self.api_key_token
                )

                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    # 解析批量修复结果
                    fixed_batch = self._parse_batch_fix_result(content, batch_paths)
                    for file_path, fixed_content in fixed_batch.items():
                        if fixed_content:
                            fixed_files[file_path] = fixed_content
                            logger.info(f"已修复文件: {file_path}")
            except Exception as e:
                logger.error(f"批量修复失败: {e}")
                # 回退到单文件修复
                for file_path in batch_paths:
                    if file_path not in fixed_files:
                        continue
                    try:
                        current_content = fixed_files[file_path]
                        file_issues = issues_by_file[file_path]
                        prompt = f"""请修复以下代码中的问题：

文件路径: {file_path}

当前代码:
```
{current_content}
```

问题列表:
{json.dumps(file_issues, ensure_ascii=False, indent=2)}

请输出修复后的完整代码，只输出代码，不要解释。"""

                        response = await call_llm(
                            model=model,
                            prompt=prompt,
                            stream=False,
                            max_tokens=8192,
                            api_key_token=self.api_key_token
                        )

                        fixed_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if fixed_content:
                            fixed_content = self._clean_code_block(fixed_content)
                            fixed_files[file_path] = fixed_content
                            logger.info(f"已修复文件（单文件回退）: {file_path}")
                    except Exception as e2:
                        logger.error(f"修复文件 {file_path} 失败: {e2}")

        return fixed_files

    def _parse_batch_fix_result(self, content: str, expected_files: List[str]) -> Dict[str, str]:
        """解析批量修复结果"""

        result = {}
        # 匹配 ===文件路径=== ... ===END=== 格式
        pattern = r'===([\w./]+)===\s*\n(.*?)(?====END===|$)'
        matches = re.findall(pattern, content, re.DOTALL)

        for file_path, code in matches:
            file_path = file_path.strip()
            if file_path in expected_files:
                # 清理代码块标记
                code = self._clean_code_block(code)
                result[file_path] = code

        # 如果没有匹配到格式，尝试解析整个内容作为单个文件
        if not result and len(expected_files) == 1:
            code = self._clean_code_block(content)
            result[expected_files[0]] = code

        return result

    def _clean_code_block(self, content: str) -> str:
        """清理代码块标记"""
        # 移除 ```python ... ``` 包裹
        content = re.sub(r'^```\w*\n?', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n?```$', '', content, flags=re.MULTILINE)
        return content.strip()
