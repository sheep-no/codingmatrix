"""
ReAct Agent - 基于 ReAct (Reasoning + Acting) 模式的 Agent

核心思想：
1. Thought - 思考当前状态，分析问题
2. Action - 执行动作（工具调用）
3. Observation - 观察结果
4. Reflection - 反思是否需要继续或回退

特点：
- 自我反思能力
- 自动回退和重试
- 状态跟踪
- 流式输出支持
"""

import asyncio
import json
import time
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

from app.agent.memory import AgentMemory
from app.agent.executor import EnhancedExecutor, ToolResult, ToolRegistry
from app.utils import call_llm
from app.agent.multi_model_agent import ModelRegistry, TaskType

logger = logging.getLogger(__name__)


class ReActStepType(Enum):
    """ReAct 步骤类型"""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    FINAL = "final"


@dataclass
class ReActStep:
    """ReAct 步骤"""
    step_type: ReActStepType
    content: str
    tool_name: Optional[str] = None
    tool_result: Optional[Any] = None
    timestamp: float = field(default_factory=time.time)
    success: bool = True


@dataclass
class ReActResult:
    """ReAct 执行结果"""
    success: bool
    final_answer: str
    steps: List[ReActStep]
    total_steps: int
    execution_time: float
    reflection_summary: str = ""


class ReActAgent:
    """
    ReAct Agent - 支持自我反思的 Agent
    """

    def __init__(
        self,
        model_key: str = "deepseek-r1-qwen3-8b",
        max_iterations: int = 10,
        enable_streaming: bool = False
    ):
        self.model = ModelRegistry.get(model_key)
        self.max_iterations = max_iterations
        self.enable_streaming = enable_streaming

        self.memory = AgentMemory()
        self.executor = EnhancedExecutor()

        self._stream_callback: Optional[Callable[[str], None]] = None
        self._steps: List[ReActStep] = []
        self._current_state: Dict[str, Any] = {}

    def set_stream_callback(self, callback: Callable[[str], None]) -> None:
        self._stream_callback = callback
        self.executor.set_stream_callback(callback)

    async def _stream(self, text: str) -> None:
        """流式输出"""
        if self._stream_callback and self.enable_streaming:
            try:
                self._stream_callback(text)
            except Exception as e:
                logger.error(f"流式输出失败: {e}")

    def _add_step(self, step: ReActStep) -> None:
        """添加步骤"""
        self._steps.append(step)
        logger.debug(f"ReAct 步骤: {step.step_type.value} - {step.content[:50]}...")

    async def _think(self, task: str, context: str) -> str:
        """
        Thought 阶段 - 分析问题
        """
        prompt = f"""分析以下任务，决定下一步行动：

任务：{task}

当前状态：
{context}

请分析：
1. 任务的核心目标是什么？
2. 已有哪些信息？
3. 还需要什么？
4. 下一步应该做什么？

请用简洁的语言描述你的思考。"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens // 2,
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            self._add_step(ReActStep(ReActStepType.THOUGHT, content))
            await self._stream(f"[思考] {content}\n\n")

            return content

        except Exception as e:
            logger.error(f"思考阶段失败: {e}")
            return f"分析任务：{task}"

    async def _act(self, thought: str, context: str) -> ToolResult:
        """
        Action 阶段 - 执行动作
        """
        prompt = f"""基于以下思考，决定执行什么动作：

思考：{thought}

当前状态：
{context}

可用工具：
{json.dumps(self.executor.tool_registry.list_tools(), ensure_ascii=False, indent=2)}

请决定：
1. 使用哪个工具？
2. 传递什么参数？

请以 JSON 格式返回：
{{
    "tool": "工具名称",
    "params": {{"参数名": "参数值"}}
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=1024,
                temperature=0.3
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            try:
                action = json.loads(content)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    action = json.loads(json_match.group())
                else:
                    raise ValueError("无法解析动作")

            tool_name = action.get("tool")
            params = action.get("params", {})

            self._add_step(ReActStep(
                ReActStepType.ACTION,
                f"执行工具: {tool_name}",
                tool_name=tool_name
            ))
            await self._stream(f"[动作] {tool_name}({params})\n")

            result = await self.executor.execute_tool(tool_name, params)

            self._steps[-1].tool_result = result.result
            self._steps[-1].success = result.success

            if result.success:
                await self._stream(f"[结果] {str(result.result)[:200]}...\n\n")
            else:
                await self._stream(f"[错误] {result.error}\n\n")

            return result

        except Exception as e:
            logger.error(f"动作执行失败: {e}")
            error_result = ToolResult(False, None, str(e), 0, "unknown")
            self._add_step(ReActStep(
                ReActStepType.ACTION,
                f"动作执行失败: {e}",
                tool_result=None,
                success=False
            ))
            return error_result

    async def _observe(self, action_result: ToolResult) -> str:
        """
        Observation 阶段 - 观察结果
        """
        result_str = json.dumps(action_result.result, ensure_ascii=False) if action_result.result else action_result.error

        prompt = f"""分析以下执行结果：

结果：{result_str}
成功：{action_result.success}

请分析：
1. 这个结果说明了什么？
2. 任务是否完成？
3. 是否需要继续？

请用简洁的语言描述观察结果。"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=512,
                temperature=0.5
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            self._add_step(ReActStep(ReActStepType.OBSERVATION, content))
            await self._stream(f"[观察] {content}\n\n")

            return content

        except Exception as e:
            logger.error(f"观察阶段失败: {e}")
            return str(action_result.result or action_result.error)

    async def _reflect(self, task: str, steps: List[ReActStep]) -> Dict[str, Any]:
        """
        Reflection 阶段 - 反思是否继续
        """
        steps_summary = "\n".join([
            f"{i+1}. [{s.step_type.value}] {s.content[:100]}"
            for i, s in enumerate(steps[-5:])
        ])

        prompt = f"""反思当前进度：

任务：{task}

最近步骤：
{steps_summary}

请判断：
1. 任务是否已完成？
2. 是否需要更多步骤？
3. 是否有错误需要回退？

请以 JSON 格式返回：
{{
    "continue": true/false,
    "task_complete": true/false,
    "issues": ["问题列表（如果有）"],
    "next_action": "下一步建议",
    "reflection": "反思总结"
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=1024,
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = {"continue": False, "task_complete": True, "reflection": content}

            reflection = result.get("reflection", "")
            self._add_step(ReActStep(ReActStepType.REFLECTION, reflection))
            await self._stream(f"[反思] {reflection}\n\n")

            self.memory.add_reflection(
                f"任务: {task[:50]}... | 反思: {reflection}",
                {"task": task, "steps": len(steps)}
            )

            return result

        except Exception as e:
            logger.error(f"反思阶段失败: {e}")
            return {
                "continue": False,
                "task_complete": True,
                "issues": [str(e)],
                "next_action": "结束",
                "reflection": f"反思失败: {e}"
            }

    async def _generate_final_answer(self, task: str, steps: List[ReActStep]) -> str:
        """
        生成最终答案
        """
        steps_summary = "\n".join([
            f"- [{s.step_type.value}] {s.content}"
            for s in steps if s.step_type in [ReActStepType.THOUGHT, ReActStepType.OBSERVATION]
        ])

        prompt = f"""基于以下执行过程，给出最终答案：

任务：{task}

执行过程：
{steps_summary}

请生成最终答案，总结整个任务的执行结果。"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=0.7
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            self._add_step(ReActStep(ReActStepType.FINAL, content))
            await self._stream(f"[最终答案]\n{content}\n")

            return content

        except Exception as e:
            logger.error(f"生成最终答案失败: {e}")
            return f"任务执行完成。执行了 {len(steps)} 个步骤。"

    async def process(
        self,
        task: str,
        context: Dict[str, Any] = None
    ) -> ReActResult:
        """
        处理任务 - ReAct 循环

        Args:
            task: 任务描述
            context: 上下文信息

        Returns:
            ReActResult
        """
        start_time = time.time()
        self._steps = []
        self._current_state = {"task": task, "context": context or {}}

        self.memory.add_user_message(task)

        await self._stream(f"[ReAct Agent] 开始处理任务: {task[:50]}...\n\n")

        for iteration in range(self.max_iterations):
            logger.info(f"ReAct 迭代 {iteration + 1}/{self.max_iterations}")

            context_str = self._build_context()

            thought = await self._think(task, context_str)

            action_result = await self._act(thought, context_str)

            self._current_state["last_result"] = action_result.result
            self._current_state["last_error"] = action_result.error

            observe = await self._observe(action_result)
            self._current_state["observation"] = observe

            reflection = await self._reflect(task, self._steps)

            if not reflection.get("continue", False) or reflection.get("task_complete", False):
                if reflection.get("task_complete", False):
                    logger.info("任务已完成")
                break

            self._current_state["next_action"] = reflection.get("next_action")

        final_answer = await self._generate_final_answer(task, self._steps)

        self.memory.add_assistant_message(final_answer)

        execution_time = time.time() - start_time

        return ReActResult(
            success=any(s.success for s in self._steps if s.step_type == ReActStepType.ACTION),
            final_answer=final_answer,
            steps=self._steps,
            total_steps=len(self._steps),
            execution_time=execution_time,
            reflection_summary=self.memory.reflection.get_insights()[-1] if self.memory.reflection.get_insights() else ""
        )

    def _build_context(self) -> str:
        """构建上下文"""
        parts = []

        if self._current_state.get("task"):
            parts.append(f"任务：{self._current_state['task']}")

        if self._current_state.get("context"):
            parts.append(f"上下文：{json.dumps(self._current_state['context'], ensure_ascii=False)}")

        recent_results = [
            s for s in self._steps[-3:]
            if s.step_type == ReActStepType.ACTION and s.tool_result
        ]
        if recent_results:
            parts.append("最近结果：")
            for r in recent_results:
                parts.append(f"- {r.tool_name}: {str(r.tool_result)[:100]}")

        if self._current_state.get("observation"):
            parts.append(f"观察：{self._current_state['observation']}")

        if self._current_state.get("next_action"):
            parts.append(f"建议：{self._current_state['next_action']}")

        memory_context = self.memory.get_context_for_prompt(max_tokens=1000)
        if memory_context:
            parts.append(f"记忆：{memory_context}")

        return "\n".join(parts)


class ReActWithFallback:
    """带降级策略的 ReAct Agent"""

    def __init__(self):
        self.primary_agent = ReActAgent(model_key="deepseek-r1-qwen3-8b")
        self.fallback_agent = ReActAgent(model_key="qwen3.5-4b")
        self.max_retries = 2

    async def process(self, task: str, context: Dict = None) -> ReActResult:
        """处理任务，失败时降级"""
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
                    except:
                        continue

        return ReActResult(
            success=False,
            final_answer="任务执行失败，请稍后重试",
            steps=[],
            total_steps=0,
            execution_time=0,
            reflection_summary=""
        )
