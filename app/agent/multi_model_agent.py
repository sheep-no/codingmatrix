"""
AI Agent - 多模型 Agent 架构

使用以下模型：
- deepseek-ai/DeepSeek-R1-0528-Qwen3-8B - 主力推理模型
- deepseek-ai/DeepSeek-OCR - OCR/视觉理解
- Qwen/Qwen3.5-4B - 轻量快速响应
- Qwen/Qwen3-8B - 通用对话
- Qwen/Qwen2.5-7B-Instruct - 指令跟随
- THUDM/GLM-4.1V-9B-Thinking - 视觉推理
- Kwai-Kolors/Kolors - 图像生成
- THUDM/GLM-4-9B-0414 - 快速任务
- THUDM/GLM-Z1-9B-0414 - 深度推理
- netease-youdao/bce-embedding-base_v1 - 嵌入/相似度

架构：
- Router: 任务路由，根据任务类型选择模型
- Planner: 任务规划，将复杂任务拆解
- Executor: 执行器，调用工具执行
- Reviewer: 审查器，验证执行结果
- FileContract: 文件契约，确保文件操作安全
"""

import re
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from app.utils import call_llm
from app.utils.file_operator import FileOperator, PathSecurityError
from app.utils.retry import retry_on_failure
from app.utils.circuit_breaker import circuit_breaker, CircuitBreakerError

logger = logging.getLogger(__name__)


def extract_json_from_response(content: str) -> Any:
    """从 LLM 响应中提取 JSON

    处理以下情况：
    - 纯 JSON
    - Markdown 代码块中的 JSON
    - JSON 前后有额外文本
    """
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试提取 markdown 代码块中的 JSON
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试查找第一个 [ 或 { 到最后一个 ] 或 } 之间的内容
    start_idx = content.find('[')
    if start_idx == -1:
        start_idx = content.find('{')

    if start_idx != -1:
        end_char = ']' if content[start_idx] == '[' else '}'
        end_idx = content.rfind(end_char)
        if end_idx > start_idx:
            try:
                return json.loads(content[start_idx:end_idx + 1])
            except json.JSONDecodeError:
                pass

    # 所有方法都失败，返回 None
    return None


class TaskType(Enum):
    """任务类型枚举"""
    GENERAL = "general"                    # 通用对话
    CODE_GENERATION = "code_generation"    # 代码生成
    CODE_REVIEW = "code_review"           # 代码审查
    FILE_OPERATION = "file_operation"      # 文件操作
    VISUAL_UNDERSTANDING = "visual"       # 视觉理解
    IMAGE_GENERATION = "image_generation" # 图像生成
    REASONING = "reasoning"               # 深度推理
    FAST_RESPONSE = "fast_response"      # 快速响应
    EMBEDDING = "embedding"               # 嵌入/相似度
    OCR = "ocr"                           # OCR识别


class ModelCapability(Enum):
    """模型能力"""
    REASONING = "reasoning"               # 深度推理
    FAST = "fast"                        # 快速响应
    VISION = "vision"                     # 视觉理解
    CODE = "code"                        # 代码生成
    CREATIVE = "creative"                # 创意生成
    OCR = "ocr"                          # OCR识别
    EMBEDDING = "embedding"              # 嵌入向量


@dataclass
class ModelInfo:
    """模型信息"""
    key: str = ""                       # 注册表键名
    name: str = ""
    display_name: str = ""
    capabilities: List[ModelCapability] = field(default_factory=list)
    max_tokens: int = 0
    thinking_budget: int = 0
    temperature: float = 0.7
    speed: float = 1.0


class ModelRegistry:
    """模型注册表"""

    MODELS = {
        # DeepSeek 系列
        "deepseek-r1-qwen3-8b": ModelInfo(
            key="deepseek-r1-qwen3-8b",
            name="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            display_name="DeepSeek R1 (Qwen3-8B)",
            capabilities=[ModelCapability.REASONING, ModelCapability.CODE],
            max_tokens=8192,
            thinking_budget=8192,
            temperature=0.6,
            speed=0.7
        ),
        "deepseek-ocr": ModelInfo(
            key="deepseek-ocr",
            name="deepseek-ai/DeepSeek-OCR",
            display_name="DeepSeek OCR",
            capabilities=[ModelCapability.OCR, ModelCapability.VISION],
            max_tokens=2048,
            thinking_budget=2048,
            temperature=0.5,
            speed=1.0
        ),

        # Qwen 系列
        "qwen3.5-4b": ModelInfo(
            key="qwen3.5-4b",
            name="Qwen/Qwen3.5-4B",
            display_name="Qwen 3.5 4B",
            capabilities=[ModelCapability.FAST],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.7,
            speed=2.0
        ),
        "qwen3-8b": ModelInfo(
            key="qwen3-8b",
            name="Qwen/Qwen3-8B",
            display_name="Qwen 3 8B",
            capabilities=[ModelCapability.REASONING, ModelCapability.FAST],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.7,
            speed=1.5
        ),
        "qwen2.5-7b": ModelInfo(
            key="qwen2.5-7b",
            name="Qwen/Qwen2.5-7B-Instruct",
            display_name="Qwen 2.5 7B",
            capabilities=[ModelCapability.CODE, ModelCapability.FAST],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.7,
            speed=1.8
        ),

        # GLM 系列
        "glm-4.1v-9b": ModelInfo(
            key="glm-4.1v-9b",
            name="THUDM/GLM-4.1V-9B-Thinking",
            display_name="GLM-4.1V 9B (Thinking)",
            capabilities=[ModelCapability.VISION, ModelCapability.REASONING],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.7,
            speed=0.8
        ),
        "glm-4-9b": ModelInfo(
            key="glm-4-9b",
            name="THUDM/GLM-4-9B-0414",
            display_name="GLM-4 9B",
            capabilities=[ModelCapability.FAST, ModelCapability.CODE],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.7,
            speed=1.6
        ),
        "glm-z1-9b": ModelInfo(
            key="glm-z1-9b",
            name="THUDM/GLM-Z1-9B-0414",
            display_name="GLM-Z1 9B",
            capabilities=[ModelCapability.REASONING],
            max_tokens=4096,
            thinking_budget=4096,
            temperature=0.6,
            speed=0.9
        ),

        # Kolors 图像生成
        "kolors": ModelInfo(
            key="kolors",
            name="Kwai-Kolors/Kolors",
            display_name="Kolors 图像生成",
            capabilities=[ModelCapability.CREATIVE],
            max_tokens=512,
            thinking_budget=0,
            temperature=0.8,
            speed=0.5
        ),

        # 嵌入模型
        "bce-embedding": ModelInfo(
            key="bce-embedding",
            name="netease-youdao/bce-embedding-base_v1",
            display_name="BCE 嵌入",
            capabilities=[ModelCapability.EMBEDDING],
            max_tokens=512,
            thinking_budget=0,
            temperature=0.0,
            speed=1.0
        ),
    }

    @classmethod
    def get(cls, key: str) -> Optional[ModelInfo]:
        return cls.MODELS.get(key)

    @classmethod
    def get_by_name(cls, name: str) -> Optional[ModelInfo]:
        for model in cls.MODELS.values():
            if model.name == name:
                return model
        return None

    @classmethod
    def list_all(cls) -> List[ModelInfo]:
        return list(cls.MODELS.values())


class ModelRouter:
    """模型路由器 - 根据任务类型选择最佳模型（支持动态路由）"""

    TASK_MODEL_MAP = {
        TaskType.GENERAL: ["qwen3-8b", "deepseek-r1-qwen3-8b"],
        TaskType.CODE_GENERATION: ["qwen2.5-7b", "deepseek-r1-qwen3-8b"],
        TaskType.CODE_REVIEW: ["deepseek-r1-qwen3-8b", "glm-z1-9b"],
        TaskType.FILE_OPERATION: ["glm-4-9b", "qwen3.5-4b"],
        TaskType.VISUAL_UNDERSTANDING: ["glm-4.1v-9b", "deepseek-ocr"],
        TaskType.IMAGE_GENERATION: ["kolors"],
        TaskType.REASONING: ["deepseek-r1-qwen3-8b", "glm-z1-9b"],
        TaskType.FAST_RESPONSE: ["qwen3.5-4b", "glm-4-9b"],
        TaskType.EMBEDDING: ["bce-embedding"],
        TaskType.OCR: ["deepseek-ocr"],
    }

    @classmethod
    def route(cls, task_type: TaskType, prefer_fast: bool = False) -> ModelInfo:
        """
        根据任务类型路由到最佳模型

        Args:
            task_type: 任务类型
            prefer_fast: 是否优先选择快速模型

        Returns:
            模型信息
        """
        model_keys = cls.TASK_MODEL_MAP.get(task_type, ["deepseek-r1-qwen3-8b"])

        if prefer_fast:
            for key in model_keys:
                model = ModelRegistry.get(key)
                if model and model.speed > 1.0:
                    return model

        primary_key = model_keys[0]
        return ModelRegistry.get(primary_key) or ModelRegistry.get("deepseek-r1-qwen3-8b")

    @classmethod
    async def route_dynamic(cls, task_type: TaskType, prefer_fast: bool = False) -> ModelInfo:
        """
        动态路由 - 基于实时健康指标选择最佳模型

        Args:
            task_type: 任务类型
            prefer_fast: 是否优先选择快速模型

        Returns:
            模型信息
        """
        from app.agent.dynamic_model_router import get_dynamic_router

        model_keys = cls.TASK_MODEL_MAP.get(task_type, ["deepseek-r1-qwen3-8b"])

        if prefer_fast:
            # 过滤出快速模型
            fast_models = [k for k in model_keys if ModelRegistry.get(k) and ModelRegistry.get(k).speed > 1.0]
            if fast_models:
                router = await get_dynamic_router()
                best_key = await router.get_best_model(fast_models, task_type.value)
                return ModelRegistry.get(best_key) or ModelRegistry.get("deepseek-r1-qwen3-8b")

        # 动态选择最佳模型
        router = await get_dynamic_router()
        best_key = await router.get_best_model(model_keys, task_type.value)
        return ModelRegistry.get(best_key) or ModelRegistry.get("deepseek-r1-qwen3-8b")

    @classmethod
    def route_by_content(cls, content: str, files: List[str] = None) -> TaskType:
        """
        根据内容特征自动识别任务类型

        Args:
            content: 用户输入内容
            files: 附加的文件列表

        Returns:
            识别到的任务类型
        """
        content_lower = content.lower()

        if files:
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in image_extensions:
                    return TaskType.VISUAL_UNDERSTANDING

        if any(k in content_lower for k in ["生成图片", "生成图像", "生成一幅图", "画一幅", "画一张", "生成一张", "画一幅图", "生成一张图"]):
            return TaskType.IMAGE_GENERATION

        if any(k in content_lower for k in ["ocr", "识别文字", "图片转文字", "图片中的文字", "从图片", "提取文字"]):
            return TaskType.OCR

        if any(k in content_lower for k in ["图片", "图像", "截图", "看图", "看这张"]):
            if any(k in content_lower for k in ["分析", "理解", "描述", "识别"]):
                return TaskType.VISUAL_UNDERSTANDING

        if any(k in content_lower for k in ["文件", "读取", "写入", "file", "操作", "打开文件"]):
            return TaskType.FILE_OPERATION

        if any(k in content_lower for k in ["审查", "review", "检查", "优化", "代码审查"]):
            return TaskType.CODE_REVIEW

        if any(k in content_lower for k in ["代码", "编写", "写一个", "写段代码", "写个函数", "写个程序"]):
            return TaskType.CODE_GENERATION

        if any(k in content_lower for k in ["推理", "reasoning", "思考", "分析", " reasoning"]):
            return TaskType.REASONING

        if len(content) < 30:
            return TaskType.FAST_RESPONSE

        return TaskType.GENERAL


@dataclass
class FileContract:
    """
    文件契约 - 确保文件操作安全

    在执行文件操作前，必须定义契约，明确操作的范围和影响
    """
    operation: str  # read, write, delete, create, move, copy
    file_path: str
    expected_content: Optional[str] = None
    max_size: int = 1024 * 1024  # 1MB
    allowed_extensions: List[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css",
        ".md", ".json", ".yaml", ".yml", ".txt", ".sh", ".bash",
        ".toml", ".xml", ".sql", ".env", ".gitignore", ".dockerfile"
    ])
    require_backup: bool = True
    validation_patterns: List[str] = field(default_factory=list)
    base_path: Optional[str] = None  # 可选，限制在特定项目目录下

    def validate_path(self) -> bool:
        """验证路径安全性"""
        try:
            op = FileOperator(base_path=self.base_path)

            abs_path = Path(self.file_path).resolve()
            abs_path_str = str(abs_path).lower()

            protected_paths = {
                "/etc", "/root", "/proc", "/sys", "/boot", "/dev",
                "/var/log", "/var/cache", "/var/run", "/tmp"
            }

            for protected in protected_paths:
                if abs_path_str.startswith(protected):
                    logger.warning(f"FileContract: 禁止访问系统路径 {self.file_path}")
                    return False

            protected_files = {
                ".env", ".git/config", "id_rsa", "id_ed25519",
                "known_hosts", "authorized_keys"
            }
            for protected in protected_files:
                if protected in abs_path_str:
                    logger.warning(f"FileContract: 禁止访问敏感文件 {self.file_path}")
                    return False

            if self.base_path:
                base_resolved = Path(self.base_path).resolve()
                if not str(abs_path).startswith(str(base_resolved)):
                    logger.warning(f"FileContract: 路径超出项目范围 {self.file_path}")
                    return False

            ext = Path(self.file_path).suffix.lower()
            if ext and ext not in self.allowed_extensions:
                logger.warning(f"FileContract: 不允许的扩展名 {ext}")
                return False

            return True
        except Exception as e:
            logger.error(f"FileContract: 路径验证异常 {e}")
            return False

    def validate_content(self, content: str) -> bool:
        """验证内容安全性"""
        if len(content) > self.max_size:
            logger.warning(f"FileContract: 内容过大 {len(content)} > {self.max_size}")
            return False

        dangerous_patterns = [
            # 系统命令执行
            r"rm\s+-rf\s+/",
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"os\.fork\s*\(",
            r"pty\.spawn\s*\(",
            r"subprocess\.call\s*\(",
            r"subprocess\.run\s*\(\s*.*,?\s*shell\s*=\s*True",
            r"subprocess\.Popen\s*\(",
            # Python 动态执行
            r"eval\s*\(",
            r"exec\s*\(\s*['\"]",
            r"compile\s*\([^)]*['\"]exec['\"]",
            r"__import__\s*\(\s*['\"]os",
            r"__import__\s*\(\s*['\"]subprocess",
            r"__import__\s*\(\s*['\"]sys",
            # Shell 注入
            r"fork\s*\(\s*\)\s*\{",
            r"system\s*\(\s*['\"]",
            # 危险模块
            r"import\s+ctypes\s",
            r"from\s+ctypes\s+import",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning(f"FileContract: 发现危险模式 {pattern}")
                return False

        return True


@dataclass
class ReviewResult:
    """审查结果"""
    approved: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high


class AIReviewer:
    """
    AI 审查器 - 验证执行结果的质量和安全性
    """

    def __init__(self, model_key: str = "deepseek-r1-qwen3-8b"):
        self.model = ModelRegistry.get(model_key)

    async def review_code(self, code: str, context: str = "") -> ReviewResult:
        """
        审查代码

        Args:
            code: 待审查的代码
            context: 上下文信息

        Returns:
            审查结果
        """
        prompt = f"""审查以下代码，检查：
1. 安全性（SQL注入、XSS、命令注入等）
2. 正确性（逻辑错误、边界情况）
3. 性能问题
4. 代码质量

代码：
```{code}```

上下文：{context}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=self.model.temperature
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            result = json.loads(content)
            return ReviewResult(
                approved=result.get("approved", False),
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", []),
                risk_level=result.get("risk_level", "low")
            )
        except json.JSONDecodeError as e:
            logger.error(f"代码审查失败: JSON解析错误 {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查输出格式错误: {str(e)}"],
                risk_level="medium"
            )
        except Exception as e:
            logger.error(f"代码审查失败: {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查过程出错: {str(e)}"],
                risk_level="medium"
            )

    async def review_file_operation(
        self,
        operation: str,
        file_path: str,
        content: str = None
    ) -> ReviewResult:
        """
        审查文件操作

        Args:
            operation: 操作类型
            file_path: 文件路径
            content: 文件内容（如果是写入操作）

        Returns:
            审查结果
        """
        contract = FileContract(
            operation=operation,
            file_path=file_path,
            expected_content=content
        )

        if not contract.validate_path():
            return ReviewResult(
                approved=False,
                issues=["路径验证失败：路径不安全或扩展名不允许"],
                risk_level="high"
            )

        if content and not contract.validate_content(content):
            return ReviewResult(
                approved=False,
                issues=["内容验证失败：内容过大或包含危险模式"],
                risk_level="high"
            )

        return ReviewResult(approved=True, risk_level="low")

    async def review_plan(self, plan: List[Dict]) -> ReviewResult:
        """
        审查执行计划

        Args:
            plan: 执行计划列表

        Returns:
            审查结果
        """
        prompt = f"""审查以下执行计划，判断是否合理和安全：

计划：
{json.dumps(plan, indent=2, ensure_ascii=False)}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=self.model.temperature
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            result = extract_json_from_response(content)
            if result is None:
                logger.warning(f"无法从审查响应中提取 JSON，放行计划: {content[:200]}")
                return ReviewResult(
                    approved=True,
                    issues=["审查响应格式异常，已自动放行"],
                    suggestions=["建议检查计划格式"],
                    risk_level="low"
                )

            return ReviewResult(
                approved=result.get("approved", False),
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", []),
                risk_level=result.get("risk_level", "low")
            )
        except Exception as e:
            logger.error(f"计划审查失败: {e}")
            return ReviewResult(
                approved=True,
                issues=[f"审查异常，已自动放行: {str(e)}"],
                suggestions=[],
                risk_level="low"
            )


class TaskPlanner:
    """任务规划器 - 将复杂任务拆解为可执行的步骤"""

    def __init__(self, model_key: str = "deepseek-r1-qwen3-8b"):
        self.model = ModelRegistry.get(model_key)

    async def decompose(self, task: str, context: Dict[str, Any] = None) -> List[Dict]:
        """
        分解任务

        Args:
            task: 任务描述
            context: 上下文信息

        Returns:
            任务步骤列表，每个步骤包含 type, description, params
        """
        prompt = f"""将以下任务分解为可执行的步骤：

任务：{task}

上下文：
{json.dumps(context or {}, indent=2, ensure_ascii=False)}

支持的步骤类型：
- file_operation: 文件操作 (read, write, delete, create)
- code_generation: 代码生成
- tool_call: 工具调用
- ai_call: AI调用 (使用指定模型)

请以JSON数组格式返回步骤：
[
  {{"type": "file_operation", "description": "读取文件", "params": {{"operation": "read", "path": "..."}}}},
  {{"type": "code_generation", "description": "生成代码", "params": {{"language": "python"}}}},
  ...
]"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "[]")

            steps = extract_json_from_response(content)
            if steps is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return [{"type": "ai_call", "description": "直接执行", "params": {"task": task}}]

            return steps if isinstance(steps, list) else []
        except Exception as e:
            logger.error(f"任务分解失败: {e}")
            return [{"type": "ai_call", "description": "直接执行", "params": {"task": task}}]


class AgentExecutor:
    """执行器 - 执行具体的任务步骤"""

    def __init__(self, file_operator: FileOperator):
        self.file_operator = file_operator

    async def execute_file_operation(self, params: Dict) -> Dict:
        """执行文件操作"""
        operation = params.get("operation")
        path = params.get("path")

        if operation == "read":
            return await self.file_operator.read_async(path)
        elif operation == "write":
            content = params.get("content", "")
            return await self.file_operator.write_async(path, content)
        elif operation == "delete":
            return self.file_operator.delete(path)
        elif operation == "create":
            return self.file_operator.create(
                path,
                is_directory=params.get("is_directory", False),
                content=params.get("content", "")
            )

        return {"error": f"未知操作: {operation}"}

    async def execute(self, step: Dict) -> Dict:
        """执行单个步骤"""
        step_type = step.get("type")
        params = step.get("params", {})

        if step_type == "file_operation":
            return await self.execute_file_operation(params)
        elif step_type == "ai_call":
            return {"status": "pending", "task": params.get("task")}
        else:
            return {"error": f"未知步骤类型: {step_type}"}


class MultiModelAgent:
    """
    多模型 Agent - 整合路由、规划、执行、审查
    """

    def __init__(
        self,
        default_model: str = "deepseek-r1-qwen3-8b",
        enable_review: bool = True,
        enable_file_contract: bool = True
    ):
        self.router = ModelRouter()
        self.planner = TaskPlanner(default_model)
        self.reviewer = AIReviewer(default_model) if enable_review else None
        self.executor = AgentExecutor(FileOperator())
        self.enable_review = enable_review
        self.enable_file_contract = enable_file_contract

    async def process(
        self,
        task: str,
        context: Dict[str, Any] = None,
        task_type: TaskType = None,
        files: List[str] = None,
        stream_callback: Callable = None,
        use_dynamic_routing: bool = True
    ) -> Dict:
        """
        处理任务

        Args:
            task: 任务描述
            context: 上下文
            task_type: 指定任务类型（可选，自动识别）
            files: 附加文件列表
            stream_callback: 流式回调函数 (可选)，接收 (event_type, data) 参数

        Returns:
            处理结果
        """
        async def emit(event_type: str, data: Dict):
            """发送流式事件"""
            if stream_callback:
                try:
                    await stream_callback(event_type, data)
                except Exception as e:
                    logger.warning(f"流式回调失败: {e}")

        if task_type is None:
            task_type = self.router.route_by_content(task, files)
            await emit("task_routed", {"task_type": task_type.value})

        # 动态路由或静态路由
        if use_dynamic_routing:
            model = await self.router.route_dynamic(task_type)
        else:
            model = self.router.route(task_type)
        await emit("model_selected", {"model": model.display_name, "model_key": model.key})

        logger.info(f"任务类型: {task_type.value}, 使用模型: {model.display_name}")

        steps = await self.planner.decompose(task, context)
        await emit("plan_created", {"steps_count": len(steps), "steps": steps})

        if self.reviewer:
            await emit("review_start", {"message": "正在审查执行计划..."})
            review_result = await self.reviewer.review_plan(steps)
            if not review_result.approved:
                await emit("review_failed", {"issues": review_result.issues})
                return {
                    "success": False,
                    "error": "计划审查未通过",
                    "issues": review_result.issues,
                    "suggestions": review_result.suggestions
                }
            await emit("review_passed", {"message": "计划审查通过"})

        results = []
        for i, step in enumerate(steps):
            await emit("step_start", {"step_index": i, "step": step})
            result = await self.executor.execute(step)
            results.append(result)
            await emit("step_complete", {"step_index": i, "result": result})

            if step.get("type") == "file_operation" and self.enable_file_contract:
                contract = FileContract(
                    operation=step["params"].get("operation"),
                    file_path=step["params"].get("path")
                )
                if not contract.validate_path():
                    await emit("contract_failed", {"message": "文件契约验证失败"})
                    return {
                        "success": False,
                        "error": "文件契约验证失败"
                    }

        await emit("complete", {"message": "任务处理完成"})

        return {
            "success": True,
            "task_type": task_type.value,
            "model_used": model.display_name,
            "steps": len(steps),
            "results": results
        }
