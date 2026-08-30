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
from pydantic import BaseModel, Field, PrivateAttr, ConfigDict, create_model

from app.schema.codeRequest import ToolDefinition, AgentConfig
from app.utils import call_llm
from app.utils.file_operator import FileOperator
from app.adapter import ModelAdapter

# 提示词加载器
try:
    from app.utils.prompt_loader import load_project_generation_prompt, load_resume_prompt, load_directory_status_prompt
except ImportError:
    load_project_generation_prompt = None
    load_resume_prompt = None
    load_directory_status_prompt = None

logger = logging.getLogger(__name__)


# ==================== 对话历史管理器 ====================

class ConversationHistoryManager:
    """基于 session_id 的对话历史管理器"""
    
    # 最大活跃会话数（防止内存泄漏）
    MAX_ACTIVE_SESSIONS = 100
    # 单个会话最大消息数
    MAX_MESSAGES_PER_SESSION = 200
    
    def __init__(self):
        # 存储格式: {session_id: {"messages": [...], "output_dir": "..."}}
        self._data: Dict[str, Dict] = {}
        # 锁，保证线程安全
        self._lock = asyncio.Lock()
    
    async def get_history(self, session_id: str) -> List[Dict]:
        """获取对话历史"""
        async with self._lock:
            data = self._data.get(session_id, {})
            return data.get("messages", [])
    
    async def add_messages(self, session_id: str, messages: List[Dict]):
        """追加消息到历史"""
        async with self._lock:
            if session_id not in self._data:
                self._data[session_id] = {"messages": [], "output_dir": None}
            self._data[session_id]["messages"].extend(messages)
            # 限制单个会话的消息数
            if len(self._data[session_id]["messages"]) > self.MAX_MESSAGES_PER_SESSION:
                self._data[session_id]["messages"] = self._data[session_id]["messages"][-self.MAX_MESSAGES_PER_SESSION:]
            # 如果会话数超限，清理最旧的
            await self._cleanup_if_needed()
    
    async def set_history(self, session_id: str, messages: List[Dict]):
        """设置完整对话历史（用于恢复）"""
        async with self._lock:
            if session_id not in self._data:
                self._data[session_id] = {"output_dir": None}
            self._data[session_id]["messages"] = messages
            # 限制单个会话的消息数
            if len(messages) > self.MAX_MESSAGES_PER_SESSION:
                self._data[session_id]["messages"] = messages[-self.MAX_MESSAGES_PER_SESSION:]
    
    async def set_output_dir(self, session_id: str, output_dir: str):
        """设置输出目录"""
        async with self._lock:
            if session_id not in self._data:
                self._data[session_id] = {"messages": []}
            self._data[session_id]["output_dir"] = output_dir
    
    async def get_output_dir(self, session_id: str) -> Optional[str]:
        """获取输出目录"""
        async with self._lock:
            data = self._data.get(session_id, {})
            return data.get("output_dir")
    
    async def clear_history(self, session_id: str):
        """清除对话历史"""
        async with self._lock:
            if session_id in self._data:
                del self._data[session_id]
    
    async def has_history(self, session_id: str) -> bool:
        """检查是否有历史"""
        async with self._lock:
            return session_id in self._data and len(self._data[session_id].get("messages", [])) > 0
    
    async def _cleanup_if_needed(self):
        """如果会话数超限，清理最旧的会话（调用时已持有锁）"""
        if len(self._data) > self.MAX_ACTIVE_SESSIONS:
            # 按最后更新时间排序，移除最旧的
            sorted_sessions = sorted(
                self._data.items(),
                key=lambda x: x[1].get("messages", [{}])[-1].get("timestamp", "") if x[1].get("messages") else "",
                reverse=True
            )
            # 保留最新的 MAX_ACTIVE_SESSIONS 个
            to_remove = sorted_sessions[self.MAX_ACTIVE_SESSIONS:]
            for sid, _ in to_remove:
                del self._data[sid]
            if to_remove:
                logger.info(f"ConversationHistoryManager: 清理 {len(to_remove)} 个过期会话")


# 全局单例
conversation_history_manager = ConversationHistoryManager()


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



# ==================== 多模型路由器 ====================

class FileModelRouter:
    """根据文件类型自动选择最佳模型（从 agent_model_config.yaml 读取配置）。"""

    # 前端文件扩展名
    FRONTEND_EXTENSIONS = {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}
    # 后端文件扩展名
    BACKEND_EXTENSIONS = {'.py', '.go', '.java', '.rs', '.rb', '.php'}
    # 配置文件扩展名
    CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.env', '.xml', '.sql'}
    # 文档文件扩展名
    DOC_EXTENSIONS = {'.md', '.txt', '.rst'}

    # 硬编码兜底（配置文件加载失败时使用）
    from app.agent.models import DEFAULT_FAST_MODEL, DEFAULT_REASONING_MODEL
    _DEFAULT_FRONTEND_MODEL = DEFAULT_FAST_MODEL
    _DEFAULT_BACKEND_MODEL = DEFAULT_REASONING_MODEL

    def __init__(self):
        self._load_config()

    def _load_config(self):
        """从 Agent 运行时 YAML 配置加载角色模型映射"""
        from app.utils.model_config_io import load_model_config
        config_path = Path(__file__).parent.parent.parent / "data" / "agent_model_config.yaml"
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = load_model_config(config_path)
            roles = cfg.get("roles", {})
            models = cfg.get("models", {})

            def _resolve(role_name: str) -> str:
                """把 role ID 解析为完整模型名称（API 用的 name 字段）"""
                role_id = roles.get(role_name, "")
                if not role_id:
                    return ""
                # 先查 models 字典获取 name（API 模型 ID）
                m = models.get(role_id, {})
                return m.get("name") or role_id

            self.frontend_model = _resolve("frontend") or self._DEFAULT_FRONTEND_MODEL
            self.backend_model = _resolve("backend") or self._DEFAULT_BACKEND_MODEL
            self.fallback_model = _resolve("fallback") or self._DEFAULT_FRONTEND_MODEL

            logger.info(f"FileModelRouter 已加载配置: frontend={self.frontend_model}, backend={self.backend_model}, fallback={self.fallback_model}")
        except Exception as e:
            logger.warning(f"FileModelRouter 加载配置失败，使用默认值: {e}")
            self.frontend_model = self._DEFAULT_FRONTEND_MODEL
            self.backend_model = self._DEFAULT_BACKEND_MODEL
            self.fallback_model = self._DEFAULT_FRONTEND_MODEL

    def get_model_for_file(self, file_path: str) -> str:
        """根据文件路径返回最佳模型"""
        ext = Path(file_path).suffix.lower()

        if ext in self.BACKEND_EXTENSIONS:
            return self.backend_model
        elif ext in self.FRONTEND_EXTENSIONS:
            return self.frontend_model
        else:
            # 配置文件、文档、未知类型 → 前端/快速模型
            return self.frontend_model

    def get_model_for_task(self, requirement: str) -> str:
        """根据任务需求返回最佳模型"""
        req_lower = requirement.lower()

        backend_keywords = ['api', '数据库', 'database', '后端', 'backend', 'server', '服务器', 'fastapi', 'django', 'flask']
        frontend_keywords = ['前端', 'frontend', 'ui', '界面', '页面', 'vue', 'react', 'html', 'css', '样式']

        backend_count = sum(1 for kw in backend_keywords if kw in req_lower)
        frontend_count = sum(1 for kw in frontend_keywords if kw in req_lower)

        if backend_count > frontend_count:
            return self.backend_model
        else:
            return self.frontend_model


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
                if param_name == "self":
                    continue
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


def extract_markdown_code_block(content: str) -> str:
    """从 markdown 内容中提取代码块"""
    pattern = r'```(?:\w+)?\n?(.*?)```'
    matches = re.findall(pattern, content, re.DOTALL)
    if matches:
        extracted = matches[0].strip()
        logger.debug(f"从 markdown 提取代码块，长度: {len(extracted)} 字符")
        return extracted
    return content


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

                # 复制文件到临时目录（非阻塞）
                await asyncio.to_thread(shutil.copy2, file_path, temp_file)

                # 执行Python文件（带有超时，非阻塞）
                cmd = [sys.executable, "-c", f"import ast; exec(open(r'{temp_file}').read())"]

                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=temp_dir
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

                    issues = []
                    warnings = []

                    if proc.returncode != 0:
                        error_msg = stderr.decode().strip()[:500]
                        issues.append(f"运行时错误: {error_msg}")

                    # 检查标准输出中的警告
                    if stdout:
                        stdout_str = stdout.decode().strip()[:200]
                        warnings.append(f"运行时输出: {stdout_str}")

                    return ValidationResult(
                        file_path=str(file_path),
                        validation_type=ValidationType.RUNTIME_CHECK,
                        success=proc.returncode == 0,
                        issues=issues,
                        warnings=warnings,
                        details={
                            "returncode": proc.returncode,
                            "stderr": stderr.decode().strip()[:200],
                            "stdout": stdout.decode().strip()[:200]
                        }
                    )

                except asyncio.TimeoutError:
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
    
    extracted_content = extract_markdown_code_block(content)
    logger.debug(f"提取后内容长度: {len(extracted_content)} 字符")

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
                await f.write(extracted_content)

            logger.info(f"文件创建成功: {file_path}, 大小: {len(extracted_content)} 字符")

            # 验证文件是否真的创建成功
            if path.exists():
                actual_size = path.stat().st_size
                logger.debug(f"文件实际大小: {actual_size} 字节")
                if actual_size == len(extracted_content):
                    logger.debug("文件大小验证成功")
                else:
                    logger.warning(f"文件大小不匹配，预期: {len(extracted_content)}, 实际: {actual_size}")

            return {"status": "success", "file_path": str(path.resolve())}
        except Exception as e:
            logger.error(f"创建文件失败: {file_path}, 错误: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}
        finally:
            # 清理不再使用的锁，防止内存泄漏
            if lock_key in _file_locks and not _file_locks[lock_key].locked():
                del _file_locks[lock_key]


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
    """项目生成Agent核心（适配call_llm + 动态工具注入）"""
    config: AgentConfig = Field(default_factory=AgentConfig)
    _encoder: Any = PrivateAttr(default=None)
    _callback_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        logger.info("初始化ProjectGeneratorAgent")
        super().__init__(**data)
        self._encoder = TokenEncoder(self.config.model)
        self._model_router = FileModelRouter()
        self._current_model = self.config.model
        logger.debug(f"Agent配置: model={self.config.model}, timeout={self.config.timeout}, 多模型路由: 启用")


    def _select_model_for_file(self, file_path: str) -> str:
        """根据文件路径选择最佳模型"""
        model = self._model_router.get_model_for_file(file_path)
        if model != self._current_model:
            logger.info(f"模型切换: {self._current_model} -> {model} (文件: {file_path})")
            self._current_model = model
        return model

    def _select_model_for_task(self, requirement: str) -> str:
        """根据任务需求选择最佳模型"""
        model = self._model_router.get_model_for_task(requirement)
        if model != self._current_model:
            logger.info(f"模型切换: {self._current_model} -> {model} (任务: {requirement[:50]}...)")
            self._current_model = model
        return model

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

    def _get_fallback_system_prompt(self, output_dir: str, tools_description: str) -> str:
        """内联备用系统提示词（当文件加载失败时使用）"""
        return f"""你是一位资深Python软件工程师，擅长全栈开发、游戏、CLI工具、数据处理等多领域项目构建。

**核心任务**：在 `{output_dir}` 生成**工程规范、可直接运行**的Python项目。

### 可用工具列表
{tools_description}

### 强制返回格式
工具调用格式：
```json
{{"tool_calls": [{{"id": "call_001", "function": {{"name": "create_project_file", "arguments": {{"file_path": "path", "content": "content", "overwrite": false}}}}}}]}}
```

完成信号格式：
```json
{{"status": "completed", "message": "项目生成完成", "files_created": ["file1", "file2"]}}
```

### 操作流程
1. 每次只创建一个文件
2. 创建顺序：main.py → requirements.txt → README.md → 其他配置
3. 文件内容必须完整可运行
4. 禁止一次性创建多个文件
"""

    def _get_fallback_resume_prompt(self, requirement: str, current_files: list) -> str:
        """内联备用继续生成提示词"""
        files_list = "\n".join(["- " + f for f in current_files[:30]]) if current_files else "(暂无文件)"
        return f"""
【继续生成 - 需求变更】
用户修改了需求，需要在之前的基础上进行调整。

当前目录已存在的文件：
{files_list}

【重要】冲突处理规则：
1. 检查冲突：仔细分析新需求与已有文件的功能是否冲突
2. 强制覆盖：如果已有文件的功能与新需求矛盾，必须使用 overwrite=true 覆盖该文件
3. 不要盲目保留：不要因为文件已存在就跳过修改，要根据需求判断

请按以下步骤执行：
1. 逐个检查已有文件的内容
2. 判断该文件的功能是否与新需求冲突
3. 如果冲突，使用 overwrite=true 重新创建该文件
4. 如果不冲突，保留该文件，继续下一步

用户的新需求：
{requirement}
"""

    def _get_fallback_directory_status(self, current_files: list) -> str:
        """内联备用目录状态提示词"""
        files_list = "\n".join(current_files[:20]) if current_files else ""
        return f"""【系统提示】
当前目录已有文件：
{files_list}

请根据新需求检查每个文件：
- 如果文件功能与新需求冲突 → 使用 overwrite=true 覆盖
- 如果文件功能与新需求兼容 → 保留不修改
- 如果需要创建新文件 → 正常创建"""

    async def _compress_context(self, messages: List[Dict], callback: Optional[Callable] = None) -> List[Dict]:
        """智能上下文压缩：保留关键信息，压缩冗余内容"""
        if len(messages) <= 3:
            return messages

        logger.info(f"开始压缩上下文，当前消息数: {len(messages)}")

        compressed = [messages[0]]  # 保留 system prompt

        # 保留最近的 2 轮对话（4 条消息）
        recent_messages = messages[-4:] if len(messages) > 4 else messages[1:]

        # 对中间消息进行摘要
        middle_messages = messages[1:-4] if len(messages) > 5 else []
        if middle_messages:
            # 提取关键信息：文件创建结果、工具执行状态、目录快照
            key_events = []
            file_created = []
            directory_snapshots = []
            error_info = []
            for msg in middle_messages:
                content = msg.get("content", "")
                if msg.get("role") == "tool":
                    try:
                        result = json.loads(content) if isinstance(content, str) else content
                        if isinstance(result, dict):
                            if result.get("status") == "success" and result.get("file_path"):
                                file_created.append(result["file_path"])
                            elif result.get("status") == "error":
                                error_info.append(result.get("message", str(result))[:80])
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif msg.get("role") == "system" and isinstance(content, str):
                    # 保留目录快照信息
                    if "目录状态" in content or "snapshot" in content.lower():
                        directory_snapshots.append(content[:200])
                elif msg.get("role") == "assistant" and content:
                    # 保留 AI 的关键决策说明
                    if len(content) > 50:
                        key_events.append(content[:100])

            # 构建压缩摘要消息
            summary_parts = ["【历史对话摘要】"]
            if file_created:
                summary_parts.append(f"已创建文件 ({len(file_created)} 个): {', '.join(file_created[:15])}")
            if directory_snapshots:
                # 保留最新的目录快照
                summary_parts.append(f"最新目录快照:\n{directory_snapshots[-1]}")
            if error_info:
                summary_parts.append(f"错误记录: {'; '.join(error_info[:3])}")
            if key_events:
                summary_parts.append(f"关键决策: {'; '.join(key_events[:3])}")
            summary_parts.append(f"(已压缩 {len(middle_messages)} 条消息)")

            compressed.append({
                "role": "system",
                "content": "\n".join(summary_parts)
            })

        compressed.extend(recent_messages)

        await self._progress_callback(ProgressType.STATUS, {
            "message": f"上下文已压缩，保留 {len(compressed)} 条关键消息",
            "original_count": len(messages),
            "compressed_count": len(compressed)
        }, callback)

        logger.info(f"上下文压缩完成: {len(messages)} -> {len(compressed)} 条消息")
        return compressed

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
            callback: Optional[Callable[[str], None]] = None,
            cancel_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """生成完整项目主入口（动态工具注入，支持多模型路由）

        Args:
            cancel_event: 取消事件，前端断开连接时设置以终止生成循环
        """
        logger.info(f"开始生成项目，需求: {requirement[:100]}...")
        logger.info(f"输出目录: {output_dir}, 会话ID: {session_id}")

        # 校验需求非空
        if not requirement or not requirement.strip():
            error_msg = "需求不能为空"
            logger.error(error_msg)
            await self._progress_callback(ProgressType.ERROR, {
                "message": error_msg,
                "step": 0
            }, callback)
            return {"success": False, "error": error_msg, "total_files_created": 0, "steps": [], "validation": {"runnable": False}}

        # 校验需求长度（防止 token 溢出）
        MAX_REQUIREMENT_LEN = 100_000
        if len(requirement) > MAX_REQUIREMENT_LEN:
            error_msg = f"需求过长（{len(requirement)} 字符），最大支持 {MAX_REQUIREMENT_LEN} 字符"
            logger.error(error_msg)
            await self._progress_callback(ProgressType.ERROR, {
                "message": error_msg,
                "step": 0
            }, callback)
            return {"success": False, "error": error_msg, "total_files_created": 0, "steps": [], "validation": {"runnable": False}}

        # 根据需求选择初始模型
        initial_model = self._select_model_for_task(requirement)
        await self._progress_callback(ProgressType.STATUS, {
            "message": f"开始项目生成，使用模型: {initial_model}",
            "requirement": requirement[:100],
            "model": initial_model
        }, callback)
        from pathlib import Path
        
        # 检查是否有历史输出目录（继续生成时使用相同的目录）
        existing_output_dir = None
        if session_id:
            existing_output_dir = await conversation_history_manager.get_output_dir(session_id)
        
        if existing_output_dir:
            # 继续生成：使用之前的目录
            output_path = Path(existing_output_dir)
            logger.info(f"继续生成，使用已有目录: {output_path}")
            await self._progress_callback(ProgressType.STATUS, {
                "message": f"继续生成，使用已有目录: {output_path.name}",
                "output_dir": str(output_path)
            }, callback)
        else:
            # 新生成：创建新目录并保存
            output_path = Path(output_dir)
            if session_id:
                await conversation_history_manager.set_output_dir(session_id, str(output_path))
            logger.info(f"新生成，创建输出目录: {output_path}")
        
        output_path.mkdir(parents=True, exist_ok=True)

        # 获取工具列表并生成描述
        tools_schema = ToolRegistry.get_schema()
        tools_description = self._generate_tools_prompt(tools_schema)

        # 系统提示词（从文件加载或使用内联备用）
        if load_project_generation_prompt:
            system_prompt = load_project_generation_prompt(
                output_dir=output_dir,
                tools_description=tools_description
            )
            if system_prompt is None:
                logger.warning("提示词加载失败，使用内联备用版本")
                system_prompt = self._get_fallback_system_prompt(output_dir, tools_description)
        else:
            system_prompt = self._get_fallback_system_prompt(output_dir, tools_description)

        # 检查是否有历史对话
        has_history = await conversation_history_manager.has_history(session_id) if session_id else False
        
        # 获取当前目录状态（用于告诉 AI 继续时的情况）
        current_files = []
        if existing_output_dir and Path(existing_output_dir).exists():
            for f in Path(existing_output_dir).rglob('*'):
                if f.is_file():
                    rel_path = f.relative_to(existing_output_dir)
                    current_files.append(str(rel_path))
        
        if has_history:
            # 继续生成：加载历史并追加新需求
            logger.info(f"继续生成，加载历史对话 | session_id: {session_id} | 已创建文件: {len(current_files)}")
            await self._progress_callback(ProgressType.STATUS, {
                "message": f"继续之前的生成，已创建 {len(current_files)} 个文件",
                "session_id": session_id,
                "existing_files": current_files[:20]  # 只传前20个
            }, callback)
            messages = await conversation_history_manager.get_history(session_id)
            
            # 构建继续生成的提示（追加到之前的对话）
            if load_resume_prompt:
                resume_prompt = load_resume_prompt(
                    requirement=requirement,
                    current_files=current_files[:30]
                )
                if resume_prompt is None:
                    resume_prompt = self._get_fallback_resume_prompt(requirement, current_files)
            else:
                resume_prompt = self._get_fallback_resume_prompt(requirement, current_files)
            
            messages.append({"role": "user", "content": resume_prompt})
            # 追加目录状态提示
            if current_files:
                if load_directory_status_prompt:
                    dir_status = load_directory_status_prompt(current_files[:20])
                    if dir_status is None:
                        dir_status = self._get_fallback_directory_status(current_files)
                else:
                    dir_status = self._get_fallback_directory_status(current_files)
                
                messages.append({
                    "role": "system",
                    "content": dir_status
                })
        else:
            # 新生成：创建新的消息列表
            new_user_prompt = f"需求：{requirement}\n输出目录：{output_dir}"
            if current_files:
                new_user_prompt += f"\n\n注意：该目录已存在以下文件，请不要重复创建：\n{chr(10).join(['- ' + f for f in current_files[:20]])}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": new_user_prompt}
            ]
            # 保存到历史
            if session_id:
                await conversation_history_manager.set_history(session_id, messages.copy())
            logger.info(f"新生成对话 | session_id: {session_id} | 目录已有文件: {len(current_files)}")

        steps = []
        total_tools_executed = 0
        logger.info(f"开始生成流程，最大步数: 40 | 历史消息数: {len(messages)}")

        # 发送总步数信息
        await self._progress_callback(ProgressType.STATUS, {
            "message": "准备开始生成",
            "total_steps": 40
        }, callback)

        while len(steps) < 40:
            current_step = len(steps) + 1
            max_steps = 40

            # 检查取消事件：用户断开连接时立即终止
            if cancel_event is not None and cancel_event.is_set():
                logger.info(f"用户取消请求，终止生成 | session_id: {session_id} | 已完成 {len(steps)} 步")
                await self._progress_callback(ProgressType.STATUS, {
                    "message": "用户取消请求，生成已终止",
                    "cancelled": True,
                    "completed_steps": len(steps)
                }, callback)
                return {
                    "success": False,
                    "cancelled": True,
                    "error": "用户取消请求",
                    "total_files_created": sum(1 for s in steps if s.get("status") == "completed"),
                    "steps": steps,
                    "validation": {"runnable": False}
                }

            # 步骤开始回调
            await self._progress_callback(ProgressType.STEP_START, {
                "message": f"第 {current_step} 步开始",
                "step": current_step,
                "max_steps": max_steps
            }, callback)

            # Token守卫 - 智能上下文压缩
            token_usage = self._estimate_tokens(messages)
            logger.debug(f"当前Token使用量: {token_usage}")
            
            if token_usage > self.config.max_thinking_tokens * 0.8:
                logger.warning(f"Token使用量达到阈值({self.config.max_thinking_tokens * 0.8})，进行智能压缩")
                await self._progress_callback(ProgressType.STATUS, {
                    "message": f"Token使用量达到阈值 ({token_usage}/{self.config.max_thinking_tokens})，正在压缩上下文",
                    "token_usage": token_usage,
                    "threshold": self.config.max_thinking_tokens * 0.8
                }, callback)
                
                # 使用智能压缩而非简单截断
                messages = await self._compress_context(messages, callback)
                
                # 验证压缩后的 Token 使用量
                new_token_usage = self._estimate_tokens(messages)
                logger.info(f"压缩后Token使用量: {new_token_usage} (减少 {token_usage - new_token_usage})")

            # 调用LLM
            logger.info(f"调用LLM API")
            await self._progress_callback(ProgressType.STATUS, {
                "message": "正在分析需求并规划文件结构",
                "step": current_step
            }, callback)

            response = await self._call_llm(messages, stream=self.config.stream, callback=callback, cancel_event=cancel_event)

            if not response.get("choices"):
                logger.error("LLM返回无选择结果")
                await self._progress_callback(ProgressType.ERROR, {
                    "message": "LLM返回无选择结果",
                    "step": current_step
                }, callback)
                break

            choice = response["choices"][0]
            assistant_content = choice.get("message", {}).get("content") or ""
            logger.info(f"LLM响应内容长度: {len(assistant_content)} 字符")

            # 校验 LLM 响应内容非空
            if not assistant_content.strip():
                logger.warning("LLM返回空内容")
                await self._progress_callback(ProgressType.STATUS, {
                    "message": "LLM返回空内容，重试中...",
                    "step": current_step
                }, callback)
                continue  # 跳过本轮，让 LLM 重新生成

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
                                        "file_path": file_obj.name,
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
                        "output_dir": str(output_path.name)
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
            validation_report = {"runnable": True, "errors": [], "warnings": [], "status": "skipped"}
            await self._progress_callback(ProgressType.VALIDATION, {
                "message": "验证已禁用",
                "status": "skipped"
            }, callback)

        # 保存对话历史（用于继续生成）
        if session_id:
            await conversation_history_manager.set_history(session_id, messages.copy())
            logger.info(f"已保存对话历史 | session_id: {session_id} | 消息数: {len(messages)}")
        
        result = {
            "success": len([s for s in steps if s.get("type") == "final"]) > 0,
            "steps": steps,
            "output_dir": str(output_path.name),
            "total_files_created": total_tools_executed,
            "validation": validation_report,
            "session_id": session_id  # 返回 session_id，方便前端继续
        }

        logger.info(f"项目生成完成，结果: {result['success']}, 累计工具调用: {total_tools_executed}")
        return result

    async def _call_llm(
            self,
            messages: List[Dict],
            callback: Optional[Callable[[str], None]] = None,
            stream: bool = False,
            target_model: str = None,
            cancel_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """调用LLM，支持流式和非流式，支持动态模型切换"""
        logger.debug("准备调用LLM API")

        # 支持动态模型切换
        model_to_use = target_model or self._current_model or self.config.model

        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            prompt_parts.append(f"【{role.upper()}】\n{content}")

        prompt = "\n\n".join(prompt_parts)
        logger.debug(f"构建的prompt长度: {len(prompt)} 字符")

        try:
            # 使用 ModelAdapter 获取模型最佳配置
            adapter = ModelAdapter(model_to_use)
            thinking_budget = adapter.get_config('thinking_budget', self.config.max_thinking_tokens)
            max_tokens = adapter.get_config('max_tokens', self.config.max_output_tokens)
            temperature = adapter.get_config('temperature', self.config.temperature)

            logger.info(f"调用SiliconFlow API，模型: {model_to_use}, 流式: {stream}, "
                        f"thinking_budget: {thinking_budget}, max_tokens: {max_tokens}")

            response_obj = await call_llm(
                model=model_to_use,
                prompt=prompt,
                stream=stream,
                timeout=float(self.config.timeout),
                max_tokens=max_tokens,
                thinking_budget=thinking_budget,
                temperature=temperature,
                cancel_event=cancel_event
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

            # call_llm 返回的是异步生成器，每次yield的是JSON字符串
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

    def _fix_json_strings(self, json_str: str) -> str:
        """修复 JSON 字符串值中的非法控制字符（如裸换行符、制表符等）"""
        import re as _re
        
        # 逐字符解析 JSON，只在字符串值内部进行修复
        result = []
        in_string = False
        escape_next = False
        i = 0
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\' and in_string:
                result.append(char)
                escape_next = True
                i += 1
                continue
            
            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            
            if in_string:
                # 在字符串内部，替换非法控制字符为转义序列
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                elif ord(char) < 0x20:  # 其他控制字符
                    result.append(f'\\u{ord(char):04x}')
                else:
                    result.append(char)
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)

    def _parse_tool_calls(self, content: str) -> tuple[List[Dict], str]:
        """从LLM回复中提取工具调用，支持多种格式"""
        logger.debug("开始解析工具调用")
        logger.debug(f"原始内容前500字符: {content[:500]}")
        import re
        content_clean = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
        if content_clean != content:
            logger.debug(f"移除了 <think> 标签，清理后长度: {len(content_clean)}")
        
        # 尝试1: 从 JSON 代码块中提取
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

        # 尝试2: 使用平衡括号匹配提取完整 JSON 对象
        tool_calls_start = content_clean.find('"tool_calls"')
        if tool_calls_start != -1:
            # 向前找 {
            json_start = content_clean.rfind('{', 0, tool_calls_start)
            if json_start != -1:
                # 从 { 开始，平衡匹配括号
                brace_count = 0
                bracket_count = 0
                in_string = False
                escape_next = False
                
                for i in range(json_start, len(content_clean)):
                    char = content_clean[i]
                    
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if char == '\\' and in_string:
                        escape_next = True
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        continue
                    
                    if in_string:
                        continue
                    
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # 找到完整的 JSON 对象
                            json_str = content_clean[json_start:i+1]
                            try:
                                data = json.loads(json_str)
                                tool_calls = data.get("tool_calls", [])
                                if tool_calls:
                                    logger.info(f"从平衡括号解析到 {len(tool_calls)} 个工具调用")
                                    pure_text = content_clean[:json_start].strip() + content_clean[i+1:].strip()
                                    return tool_calls, pure_text
                            except json.JSONDecodeError as e:
                                logger.debug(f"平衡括号JSON解析失败: {e}")
                            break
                    elif char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1

        # 尝试2.5: 如果上面失败，尝试直接解析 ```json 和 ``` 之间的内容
        json_code_block = re.search(r'```json\s*\n([\s\S]*?)\n\s*```', content_clean)
        if json_code_block:
            try:
                json_str = json_code_block.group(1).strip()
                data = json.loads(json_str)
                tool_calls = data.get("tool_calls", [])
                if tool_calls:
                    logger.info(f"从JSON代码块直接解析到 {len(tool_calls)} 个工具调用")
                    pure_text = re.sub(r'```json\s*\n[\s\S]*?\n\s*```', '', content_clean, flags=re.DOTALL).strip()
                    return tool_calls, pure_text
            except json.JSONDecodeError as e:
                logger.debug(f"JSON代码块直接解析失败: {e}")
                # 尝试修复 JSON：将字符串值中的裸换行符转义
                try:
                    import re as _re
                    json_str = json_code_block.group(1).strip()
                    # 在 JSON 字符串值中，将实际的换行符替换为 \n
                    # 这需要小心处理，不能替换键名或结构中的换行
                    fixed_json = self._fix_json_strings(json_str)
                    if fixed_json != json_str:
                        data = json.loads(fixed_json)
                        tool_calls = data.get("tool_calls", [])
                        if tool_calls:
                            logger.info(f"从修复的JSON代码块解析到 {len(tool_calls)} 个工具调用")
                            pure_text = re.sub(r'```json\s*\n[\s\S]*?\n\s*```', '', content_clean, flags=re.DOTALL).strip()
                            return tool_calls, pure_text
                except Exception as fix_err:
                    logger.debug(f"JSON修复后解析仍失败: {fix_err}")

        # 尝试3: 提取纯 JSON 对象（无代码块包裹，简单正则）
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

        # 尝试4: 如果LLM直接输出了代码块，尝试提取
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
        logger.debug(f"内容前200字符: {content_clean[:200]}")
        return [], content_clean

    async def _execute_tools(
            self,
            tool_calls: List[Dict],
            session_id: Optional[str],
            callback: Optional[Callable] = None
    ) -> List[Any]:
        """并发执行工具，支持根据文件类型动态切换模型"""
        logger.info(f"并发执行 {len(tool_calls)} 个工具")
        logger.debug(f"工具调用详情: {json.dumps(tool_calls, ensure_ascii=False, indent=2)}")

        tasks = []

        for call in tool_calls:
            try:
                tool_name = call["function"]["name"]
                tool_id = call["id"]
            except (KeyError, TypeError) as e:
                logger.error(f"畸形 tool_call 结构: {call} | 错误: {e}")
                tasks.append(self._create_error_message(
                    str(call.get("id", "unknown")),
                    f"工具调用结构畸形，缺少必要字段: {e}"
                ))
                continue
            
            # 如果是创建文件工具，根据文件类型切换模型
            if tool_name == "create_project_file":
                args = call["function"].get("arguments", {})
                file_path = args.get("file_path", "")
                if file_path:
                    selected_model = self._select_model_for_file(file_path)
                    await self._progress_callback(ProgressType.STATUS, {
                        "message": f"创建文件: {file_path}, 使用模型: {selected_model}",
                        "file_path": file_path,
                        "model": selected_model
                    }, callback)

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
        """执行单个工具，支持同步和异步工具"""
        import inspect
        logger.info(f"执行工具: {tool_def.name}, 参数: {json.dumps(args, ensure_ascii=False)[:200]}...")
        try:
            # 判断工具函数是否为异步
            if inspect.iscoroutinefunction(tool_def.func):
                result = await tool_def.func(**args)
            else:
                # 同步工具，在线程池中执行以避免阻塞事件循环
                result = await asyncio.to_thread(tool_def.func, **args)
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


@ToolRegistry.register(name="search_files", description="使用正则表达式搜索项目文件内容，返回匹配的行")
def search_files(project_path: str, pattern: str, file_pattern: str = ".*", case_sensitive: bool = True, max_results: int = 100) -> dict:
    """正则搜索项目文件"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.search(pattern=pattern, path=".", file_pattern=file_pattern, case_sensitive=case_sensitive, max_results=max_results)
    except (ValueError, PathSecurityError, FileNotFoundError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="read_file", description="读取项目文件内容，支持分页")
def read_file(project_path: str, file_path: str, offset: int = 0, limit: int = 100) -> dict:
    """读取文件内容"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.read(path=file_path, offset=offset, limit=limit)
    except (FileNotFoundError, PathSecurityError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="edit_file", description="编辑项目文件内容，支持创建备份")
def edit_file(project_path: str, file_path: str, content: str, create_backup: bool = True) -> dict:
    """编辑文件"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.write(path=file_path, content=content, create_backup=create_backup)
    except (PathSecurityError, FileExistsError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="grep_files", description="快速全文搜索文件内容")
def grep_files(project_path: str, keyword: str, file_types: str = None, case_sensitive: bool = True) -> dict:
    """快速全文搜索"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.grep(keyword=keyword, path=".", file_types=file_types, case_sensitive=case_sensitive)
    except (ValueError, PathSecurityError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="delete_file", description="删除项目文件或目录")
def delete_file(project_path: str, path: str) -> dict:
    """删除文件或目录"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.delete(path=path)
    except (FileNotFoundError, PathSecurityError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="rename_file", description="重命名或移动文件/目录")
def rename_file(project_path: str, old_path: str, new_path: str) -> dict:
    """重命名/移动文件或目录"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.move(source=old_path, destination=new_path)
    except (FileNotFoundError, PathSecurityError, FileExistsError) as e:
        return {"error": str(e)}


# ==================== 项目文件管理器 ====================

# 工具函数（独立函数，不依赖类实例）

@ToolRegistry.register(name="create_file", description="创建新文件或目录")
def create_file(project_path: str, path: str, is_directory: bool = False, content: str = "") -> dict:
    """创建文件或目录"""
    op = ProjectFileManager(project_path)
    try:
        return op._operator.create(path=path, is_directory=is_directory, content=content)
    except (PathSecurityError, FileExistsError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="list_files", description="列出项目中的所有文件")
def list_files(project_path: str, pattern: str = ".*") -> dict:
    """列出项目文件"""
    op = ProjectFileManager(project_path)
    try:
        result = op._operator.list_dir(path=".", recursive=True)
        result["project"] = project_path
        return result
    except (NotADirectoryError, PathSecurityError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="project_tree", description="获取项目的目录结构树")
def project_tree(project_path: str, max_depth: int = 5) -> dict:
    """获取项目结构树"""
    op = ProjectFileManager(project_path)
    try:
        result = op._operator.tree(path=".", max_depth=max_depth)
        result["project"] = project_path
        return result
    except (FileNotFoundError, PathSecurityError) as e:
        return {"error": str(e)}


@ToolRegistry.register(name="project_stats", description="获取项目的统计信息")
def project_stats(project_path: str) -> dict:
    """获取项目统计"""
    op = ProjectFileManager(project_path)
    try:
        result = op._operator.stats(path=".")
        result["project"] = project_path
        return result
    except (FileNotFoundError, PathSecurityError) as e:
        return {"error": str(e)}


class ProjectFileManager:
    """
    项目文件管理器

    封装 FileOperator，提供项目场景的文件操作
    作为 Agent 的工具被调用
    """

    PROJECT_BASE_DIR = "./projects"

    def __init__(self, project_path: str = None):
        """
        初始化项目文件管理器

        Args:
            project_path: 项目路径（相对于 PROJECT_BASE_DIR）
        """
        base_dir = Path(self.PROJECT_BASE_DIR).resolve()
        if project_path:
            base_dir = base_dir / project_path
            project_dir = base_dir.resolve()
            if not str(project_dir).startswith(str(Path(self.PROJECT_BASE_DIR).resolve())):
                raise PermissionError("无权访问该路径")
            if not project_dir.exists():
                raise FileNotFoundError("项目不存在")

        self._operator = FileOperator(base_path=str(base_dir))
        self.project_path = project_path

    def _resolve_path(self, file_path: str = None) -> Tuple[Path, Optional[Path]]:
        """解析路径"""
        return self._operator._validate_path(file_path, must_exist=False, check_extension=False)
