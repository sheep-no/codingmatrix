"""
ReAct Agent - 基于 ReActEngine 的薄封装

保留 ReActAgent 接口以维持向后兼容，
内部委托给 ReActEngine(full 模式) 执行。
"""

import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
import logging

from app.agent.memory import AgentMemory
from app.agent.executor import EnhancedExecutor, ToolResult
from app.agent.react_engine import ReActEngine, ReActStep as EngineStep, ReActResult as EngineResult
from app.utils import call_llm
from app.agent.multi_model_agent import ModelRegistry
from app.agent.specialist_base import SPECIALIST_TOOLS

logger = logging.getLogger(__name__)


# 向后兼容：ReActStepType 枚举
class ReActStepType:
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    FINAL = "final"


@dataclass
class ReActStep:
    """ReAct 步骤（向后兼容）"""
    step_type: str
    content: str
    tool_name: Optional[str] = None
    tool_result: Optional[Any] = None
    timestamp: float = field(default_factory=time.time)
    success: bool = True


@dataclass
class ReActResult:
    """ReAct 执行结果（向后兼容）"""
    success: bool
    final_answer: str
    steps: List[ReActStep]
    total_steps: int
    execution_time: float
    reflection_summary: str = ""


class ReActAgent:
    """
    ReAct Agent - 支持自我反思的 Agent

    内部委托给 ReActEngine(full 模式)，保留原有接口以维持向后兼容。
    """

    DEFAULT_STAGE_MODELS = {
        ReActStepType.THOUGHT: "glm-z1-9b",
        ReActStepType.ACTION: "qwen3-8b",
        ReActStepType.OBSERVATION: "qwen3.5-4b",
        ReActStepType.REFLECTION: "glm-z1-9b",
        ReActStepType.FINAL: "qwen3.5-4b",
    }

    def __init__(
        self,
        model_key: str = "glm-z1-9b",
        max_iterations: int = 10,
        enable_streaming: bool = False,
        stage_models: Optional[Dict[str, str]] = None,
        model_name: Optional[str] = None,
        api_key_token: Optional[str] = None,
    ):
        if model_name:
            from app.agent.models import ModelInfo, ModelCapability
            self.default_model = ModelInfo(
                key="custom",
                name=model_name,
                display_name=model_name,
                capabilities=[ModelCapability.CODE],
                max_tokens=4096,
                thinking_budget=4096,
                temperature=0.7,
                speed=1.0,
            )
        else:
            self.default_model = ModelRegistry.get(model_key)
        self.max_iterations = max_iterations
        self.enable_streaming = enable_streaming
        self.stage_models = stage_models or self.DEFAULT_STAGE_MODELS
        self.api_key_token = api_key_token

        self.memory = AgentMemory()
        self.executor = EnhancedExecutor()

        self._stream_callback: Optional[Callable[[str], None]] = None
        self._steps: List[ReActStep] = []
        self._current_state: Dict[str, Any] = {}

    @property
    def model(self):
        """兼容旧代码，返回默认模型"""
        return self.default_model

    def set_stream_callback(self, callback: Callable[[str], None]) -> None:
        self._stream_callback = callback
        self.executor.set_stream_callback(callback)

    async def process(
        self,
        task: str,
        context: Dict[str, Any] = None
    ) -> ReActResult:
        """
        处理任务 - 委托给 ReActEngine(full 模式)

        Args:
            task: 任务描述
            context: 上下文信息

        Returns:
            ReActResult
        """
        start_time = time.time()

        # 构建工具注册表（兼容 EnhancedExecutor 的工具）
        tools = {}
        for name, tool_info in self.executor.tool_registry._tools.items():
            fn = tool_info.get("func")
            if fn:
                schema = tool_info.get("parameters") or {}
                tools[name] = {
                    "fn": fn,
                    "description": tool_info.get("description", ""),
                    "params": {
                        name: prop.get("type", "string")
                        for name, prop in schema.get("properties", {}).items()
                    },
                }

        # 如果 executor 没有工具，使用 SPECIALIST_TOOLS
        if not tools:
            tools = SPECIALIST_TOOLS

        # 创建 ReActEngine（full 模式）
        engine = ReActEngine(
            tools=tools,
            call_llm_fn=lambda p, s: self._call_llm(p, s),
            project_path=str((context or {}).get("project_path", "")),
            max_rounds=self.max_iterations,
            mode="full",
            role_name="ReActAgent",
            memory=self.memory,
            stream_callback=self._stream_callback if self.enable_streaming else None,
        )

        # 执行
        final_answer = await engine.run(task, "")

        # 转换结果格式（向后兼容）
        steps = []
        for es in engine.steps:
            steps.append(ReActStep(
                step_type=es.step_type,
                content=es.content,
                tool_name=es.tool_name,
                tool_result=es.tool_result,
                timestamp=es.timestamp,
                success=es.success if es.success is not None else True,
            ))

        self._steps = steps
        execution_time = time.time() - start_time

        return ReActResult(
            success=bool(final_answer and final_answer.strip()) or any(
                s.success for s in steps if s.step_type == "action"
            ),
            final_answer=final_answer,
            steps=steps,
            total_steps=len(steps),
            execution_time=execution_time,
            reflection_summary=self.memory.reflection.get_insights()[-1] if self.memory.reflection.get_insights() else ""
        )

    async def _call_llm(self, prompt: str, system_prompt: str) -> str:
        """调用 LLM（使用默认模型）"""
        try:
            response = await call_llm(
                model=self.default_model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.default_model.max_tokens,
                temperature=0.7,
                api_key_token=self.api_key_token,
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"ReActAgent LLM 调用失败: {e}")
            return ""

