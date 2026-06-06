"""
模型注册表与路由器

从 multi_model_agent.py 拆分而来，保持向后兼容。
"""

import logging
from typing import Optional, List, Dict
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型枚举"""
    GENERAL = "general"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    FILE_OPERATION = "file_operation"
    VISUAL_UNDERSTANDING = "visual_understanding"
    IMAGE_GENERATION = "image_generation"
    REASONING = "reasoning"
    FAST_RESPONSE = "fast_response"
    EMBEDDING = "embedding"
    OCR = "ocr"
    REACT = "react"
    PLANNING = "planning"


class AgentRole(Enum):
    """Agent 角色枚举（5×5 矩阵维度）"""
    ARCHITECT = "architect"
    FRONTEND = "frontend"
    BACKEND = "backend"
    REVIEWER = "reviewer"
    FALLBACK = "fallback"


class ModelCapability(Enum):
    """模型能力枚举"""
    CODE = "code"
    VISION = "vision"
    REASONING = "reasoning"
    FAST = "fast"
    CREATIVE = "creative"
    EMBEDDING = "embedding"
    OCR = "ocr"


@dataclass
class ModelInfo:
    """模型信息"""
    key: str
    name: str
    display_name: str
    capabilities: List[ModelCapability]
    max_tokens: int
    thinking_budget: int
    temperature: float
    speed: float


# 默认模型常量 — 避免业务代码硬编码模型名称
# 与 ModelRegistry 中的 key 对应，用于 model_assignment 缺失时的 fallback
DEFAULT_CODE_MODEL = "Qwen/Qwen3-8B"                    # 通用代码任务
DEFAULT_REASONING_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"  # 推理/后端任务
DEFAULT_ARCHITECT_MODEL = "THUDM/GLM-Z1-9B-0414"        # 架构设计/评审
DEFAULT_FAST_MODEL = "Qwen/Qwen3.5-4B"                  # 简单/快速任务

# COMPLEXITY_LEVELS 供 ModelRouter.get_role_model 校验复杂度参数
COMPLEXITY_LEVELS = ("SIMPLE", "SMALL", "MEDIUM", "LARGE")


class ModelRegistry:
    """模型注册表 - 管理所有可用模型"""

    MODELS: Dict[str, ModelInfo] = {
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
    async def get_role_model(
        cls,
        role: AgentRole,
        complexity: str = "MEDIUM"
    ) -> ModelInfo:
        """
        基于 5×5 模型分配矩阵的角色路由（v5.12.x 新增）

        优先使用 DynamicModelRouter.get_assignment_with_learning 获取角色模型，
        在没有足够学习数据时回退到静态 5×5 矩阵。

        Args:
            role: Agent 角色（architect/frontend/backend/reviewer/fallback）
            complexity: 项目复杂度（SIMPLE/SMALL/MEDIUM/LARGE/ENTERPRISE）

        Returns:
            角色对应的 ModelInfo
        """
        if complexity not in COMPLEXITY_LEVELS:
            complexity = "MEDIUM"

        try:
            from app.agent.dynamic_model_router import get_dynamic_router
            router = await get_dynamic_router()
            assignment = await router.get_assignment_with_learning(complexity)
            role_to_attr = {
                AgentRole.ARCHITECT: "architect_model",
                AgentRole.FRONTEND: "frontend_model",
                AgentRole.BACKEND: "backend_model",
                AgentRole.REVIEWER: "reviewer_model",
                AgentRole.FALLBACK: "fallback_model",
            }
            model_key = getattr(assignment, role_to_attr[role], None)
            if model_key:
                return ModelRegistry.get(model_key) or ModelRegistry.get("deepseek-r1-qwen3-8b")
        except Exception as e:
            logger.warning(f"5×5 矩阵角色路由失败，回退到默认: {e}")

        role_fallbacks = {
            AgentRole.ARCHITECT: "glm-z1-9b",
            AgentRole.FRONTEND: "qwen3-8b",
            AgentRole.BACKEND: "deepseek-r1-qwen3-8b",
            AgentRole.REVIEWER: "deepseek-r1-qwen3-8b",
            AgentRole.FALLBACK: "qwen3-8b",
        }
        fallback_key = role_fallbacks.get(role, "deepseek-r1-qwen3-8b")
        return ModelRegistry.get(fallback_key) or ModelRegistry.get("deepseek-r1-qwen3-8b")

    @classmethod
    def route_by_content(cls, content: str, files: Optional[List[str]] = None) -> TaskType:
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

        if any(k in content_lower for k in ["审查", "review", "检查", "优化", "代码审查"]):
            return TaskType.CODE_REVIEW

        if any(k in content_lower for k in ["推理", "reasoning", "思考", "分析", "解释", "说明", "describe", "explain", "analyze"]):
            return TaskType.REASONING

        if any(k in content_lower for k in ["文件", "读取", "写入", "file", "操作", "打开文件"]):
            return TaskType.FILE_OPERATION

        if any(k in content_lower for k in ["代码", "编写", "写一个", "写段代码", "写个函数", "写个程序"]):
            return TaskType.CODE_GENERATION

        if any(k in content_lower for k in ["推理", "reasoning", "思考", "分析", " reasoning"]):
            return TaskType.REASONING

        if len(content) < 30:
            return TaskType.FAST_RESPONSE

        return TaskType.GENERAL
