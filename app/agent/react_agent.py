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
        stage_models: Optional[Dict[str, str]] = None
    ):
        self.default_model = ModelRegistry.get(model_key)
        self.max_iterations = max_iterations
        self.enable_streaming = enable_streaming
        self.stage_models = stage_models or self.DEFAULT_STAGE_MODELS

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
                tools[name] = {
                    "fn": fn,
                    "description": tool_info.get("description", ""),
                    "params": {p: "string" for p in (tool_info.get("parameters") or {}).get("properties", {}).keys()},
                }

        # 如果 executor 没有工具，使用 SPECIALIST_TOOLS
        if not tools:
            tools = SPECIALIST_TOOLS

        # 创建 ReActEngine（full 模式）
        engine = ReActEngine(
            tools=tools,
            call_llm_fn=lambda p, s: self._call_llm(p, s),
            project_path="",
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
            success=any(s.success for s in steps if s.step_type == "action"),
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
                temperature=0.7
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"ReActAgent LLM 调用失败: {e}")
            return ""


class ReActWithFallback:
    """带降级策略的 ReAct Agent"""

    def __init__(self):
        self.primary_agent = ReActAgent(model_key="glm-z1-9b")
        self.fallback_agent = ReActAgent(model_key="qwen3.5-4b")
        self.max_retries = 2

    async def process(self, task: str, context: Dict = None) -> ReActResult:
        """处理任务，失败时降级"""
        import asyncio

        for attempt in range(self.max_retries):
            try:
                result = await self.primary_agent.process(task, context)

                if result.success:
                    return result

                if attempt < self.max_retries - 1:
                    logger.warning(f"主模型失败，尝试降级 (尝试 {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"ReAct 执行异常: {e}")

                if attempt < self.max_retries - 1:
                    logger.info("切换到备用模型")
                    try:
                        return await self.fallback_agent.process(task, context)
                    except Exception as fb_e:
                        logger.warning(f"备用模型也失败: {fb_e}")
                        continue

        return ReActResult(
            success=False,
            final_answer="任务执行失败，请稍后重试",
            steps=[],
            total_steps=0,
            execution_time=0,
            reflection_summary=""
        )
