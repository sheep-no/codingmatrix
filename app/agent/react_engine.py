"""
ReActEngine - 统一的 ReAct 引擎基类

提供可配置的 ReAct 循环，支持两种模式：
- 简单模式：Thought→Tool→Result 循环，自然终止（Specialist 使用）
- 完整模式：Thought→Action→Observation→Reflection→Final，反射终止（ReActAgent 使用）
"""

import json
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agent.architect_json_parser import ArchitectJsonParser

logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """ReAct 步骤"""
    step_type: str  # thought, action, observation, reflection, final
    content: str
    tool_name: Optional[str] = None
    tool_params: Optional[Dict] = None
    tool_result: Any = None
    success: Optional[bool] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReActResult:
    """ReAct 执行结果"""
    success: bool
    final_answer: str
    steps: List[ReActStep]
    total_steps: int
    execution_time: float
    reflection_summary: str = ""


class ReActEngine:
    """
    统一的 ReAct 引擎

    支持两种运行模式：
    - simple: 简单 Thought→Tool→Result 循环，自然终止
    - full: 完整 Thought→Action→Observation→Reflection→Final，反射终止

    使用方式：
    1. 创建引擎实例，配置工具和回调
    2. 调用 run() 执行任务
    """

    # 上下文窗口管理常量
    MAX_RECENT_ENTRIES = 3       # 保留最近 N 条工具调用的完整结果
    MAX_HISTORY_CHARS = 6000     # 工具历史总字符上限

    def __init__(
        self,
        tools: Dict[str, Dict],
        call_llm_fn: Callable,
        project_path: str = "",
        max_rounds: int = 6,
        mode: str = "simple",  # "simple" or "full"
        callback: Optional[Any] = None,
        emit_event_fn: Optional[Callable] = None,
        role_name: str = "ReAct",
        memory: Optional[Any] = None,  # AgentMemory 实例（full 模式用）
        stream_callback: Optional[Callable] = None,  # 流式输出回调（full 模式用）
    ):
        """
        初始化 ReAct 引擎

        Args:
            tools: 工具注册表 {name: {"fn": callable, "description": str}}
            call_llm_fn: LLM 调用函数 (prompt, system_prompt) -> str
            project_path: 项目路径（工具搜索用）
            max_rounds: 最大轮次
            mode: 运行模式 ("simple" or "full")
            callback: 进度回调函数
            emit_event_fn: 事件推送函数 (callback, event_type, data) -> None
            role_name: 角色名称（日志用）
            memory: AgentMemory 实例（full 模式用于存储反思和上下文）
            stream_callback: 流式输出回调（full 模式用于实时输出）
        """
        self.tools = tools
        self.call_llm_fn = call_llm_fn
        self.project_path = project_path
        self.max_rounds = max_rounds
        self.mode = mode
        self.callback = callback
        self.emit_event_fn = emit_event_fn
        self.role_name = role_name
        self.memory = memory
        self.stream_callback = stream_callback

        self.tool_names = list(tools.keys())
        self.json_parser = ArchitectJsonParser()
        self.steps: List[ReActStep] = []
        self.tool_history: List[str] = []

    def _build_tools_description(self) -> str:
        """构建工具描述"""
        parts = []
        for name, info in self.tools.items():
            desc = info.get("description", "无描述")
            params = info.get("params", {})
            params_desc = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else "无参数"
            parts.append(f"- {name}: {desc} (参数: {params_desc})")
        return "\n".join(parts)

    def _build_system_prompt(self, base_system: str) -> str:
        """构建增强的系统 prompt"""
        tools_desc = self._build_tools_description()

        if self.mode == "simple":
            return (
                f"{base_system}\n\n"
                f"### 可用工具\n"
                f"你可以调用以下工具来搜索、读取、编辑项目文件：\n\n"
                f"{tools_desc}\n\n"
                f"### 工具调用格式\n"
                f"如果需要使用工具，请且仅返回一个 JSON 对象：\n"
                f'{{"tool": "工具名", "params": {{"参数名": "值"}}}}\n\n'
                f"示例：\n"
                f'{{"tool": "list_files", "params": {{"directory": "."}}}}\n'
                f'{{"tool": "read_file", "params": {{"file_path": "src/main.py"}}}}\n'
                f'{{"tool": "run_command", "params": {{"command": "grep -rn --include=*.py def src/"}}}}\n\n'
                f"### 重要规则\n"
                f"1. 每次只调用一个工具，格式为：{{\"tool\": \"...\", \"params\": {{...}}}}\n"
                f"2. 收到工具结果后，继续调用工具或生成最终代码\n"
                f"3. 对于新文件：准备生成代码时，直接返回完整代码，不要包裹 JSON\n"
                f"4. 对于已有文件：使用 partial_update/insert_content/regex_replace 进行精准编辑\n"
                f"5. 可用工具: {', '.join(self.tool_names)}\n"
                f"6. 当你已收集足够上下文时，直接生成代码或文字答案，无需再调用工具\n"
                f"7. 在生成或修改代码之前，你必须先使用工具了解项目现有代码结构。不要凭猜测生成代码\n"
                f"8. 如果任务需要分析项目（如查找函数、统计代码、理解结构），请使用 run_command 工具执行 grep/find/wc 等命令\n"
                f"9. 工具调用期间，只返回 {{\"tool\": \"...\", \"params\": {{...}}}} 格式，不要返回其他 JSON 格式\n"
            )
        else:  # full mode
            return (
                f"{base_system}\n\n"
                f"### 可用工具\n"
                f"{tools_desc}\n\n"
                f"### 工具调用格式\n"
                f'{{"tool": "工具名", "params": {{"参数名": "值"}}}}\n\n'
                f"### 重要规则\n"
                f"1. 每次只调用一个工具\n"
                f"2. 收到工具结果后，继续调用工具或生成最终答案\n"
                f"3. 当你已收集足够信息时，直接生成最终答案\n"
            )

    def _parse_tool_call(self, text: str) -> Optional[Dict]:
        """解析工具调用 JSON"""
        if not text:
            return None

        # 尝试直接解析
        try:
            result = json.loads(text.strip())
            if isinstance(result, dict) and "tool" in result:
                return result
        except json.JSONDecodeError:
            pass

        # 使用 JSON 解析器
        try:
            result = self.json_parser.safe_parse_json(text)
            if isinstance(result, dict) and "tool" in result:
                return result
        except (ValueError, Exception):
            pass

        return None

    async def _execute_tool(self, tool_name: str, tool_params: Dict) -> Tuple[bool, Any]:
        """执行工具（同步和异步函数统一处理）"""
        if tool_name not in self.tools:
            return False, {"error": f"工具不存在: {tool_name}"}

        try:
            fn = self.tools[tool_name]["fn"]
            result = fn(project_path=self.project_path, **tool_params)

            # 异步函数返回 coroutine，需要 await
            if asyncio.iscoroutine(result):
                result = await result

            return True, result
        except asyncio.CancelledError:
            raise  # 取消信号必须向上透传，不能被吞掉
        except Exception as e:
            return False, {"error": str(e)}

    def _add_step(self, step: ReActStep):
        """添加步骤"""
        self.steps.append(step)
        logger.debug(f"{self.role_name} ReAct 步骤: {step.step_type} - {step.content[:50]}...")

    async def _emit_event(self, event_type: str, data: Dict):
        """推送事件"""
        if self.callback and self.emit_event_fn:
            try:
                self.emit_event_fn(self.callback, event_type, data)
            except Exception as e:
                logger.debug(f"事件推送失败（非致命）: {e}")

    async def _stream(self, text: str):
        """流式输出（full 模式用）"""
        if self.stream_callback:
            try:
                self.stream_callback(text)
            except Exception as e:
                logger.debug(f"流式输出回调失败（非致命）: {e}")

    async def _reflect(self, task: str, steps: List[ReActStep]) -> Dict[str, Any]:
        """Reflection 阶段 - 反思是否继续（full 模式用）

        Returns:
            {"continue": bool, "task_complete": bool, "reflection": str, ...}
        """
        steps_summary = "\n".join([
            f"{i+1}. [{s.step_type}] {s.content[:100]}"
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
            response = await self.call_llm_fn(prompt, "你是一个反思分析器。分析当前执行进度，判断是否需要继续。")
            result = self.json_parser.safe_parse_json(response)
            if not isinstance(result, dict):
                # JSON 解析失败或返回非 dict，继续执行而非终止
                logger.warning(f"反思阶段 JSON 解析失败，继续执行")
                result = {"continue": True, "task_complete": False, "reflection": response}
        except Exception as e:
            logger.error(f"反思阶段失败: {e}")
            result = {"continue": True, "task_complete": False, "reflection": f"反思失败: {e}"}

        return result

    async def _generate_final_answer(self, task: str, steps: List[ReActStep]) -> str:
        """生成最终答案（full 模式用）"""
        steps_summary = "\n".join([
            f"- [{s.step_type}] {s.content}"
            for s in steps if s.step_type in ("thought", "observation")
        ])

        prompt = f"""基于以下执行过程，给出最终答案：

任务：{task}

执行过程：
{steps_summary}

请生成最终答案，总结整个任务的执行结果。"""

        try:
            response = await self.call_llm_fn(prompt, "你是一个总结器。基于执行过程生成最终答案。")
            return response
        except Exception as e:
            logger.error(f"生成最终答案失败: {e}")
            return f"任务执行完成。执行了 {len(steps)} 个步骤。"

    async def run(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """
        执行 ReAct 循环

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt

        Returns:
            LLM 最终输出的文本
        """
        if not self.project_path or not self.tools:
            logger.info(f"{self.role_name} ReAct: 无项目路径或无工具，直接调用 LLM")
            return await self.call_llm_fn(prompt, system_prompt)

        logger.info(f"{self.role_name} ReAct: 使用 {self.mode} 模式 (project_path={self.project_path}, tools={self.tool_names})")

        enhanced_system = self._build_system_prompt(system_prompt)
        self.steps = []
        self.tool_history = []

        if self.mode == "full":
            return await self._run_full(prompt, enhanced_system)
        else:
            return await self._run_simple(prompt, enhanced_system)

    def _build_history_text(self) -> str:
        """构建工具历史文本（滑动窗口：最近 N 条完整，更早的摘要）

        避免工具历史无限增长占用上下文窗口。
        免费模型上下文窗口有限（32K-128K），每轮 1500 字符的工具结果
        5 轮后就占 7500+ token，挤压生成空间。
        """
        if len(self.tool_history) <= self.MAX_RECENT_ENTRIES:
            text = "\n\n".join(self.tool_history)
            # 即使条目少，也可能单条很大（如读取大文件）
            if len(text) > self.MAX_HISTORY_CHARS:
                return text[:self.MAX_HISTORY_CHARS] + "\n[...结果已截断]"
            return text

        # 更早的条目：每条压缩为一行摘要
        early = self.tool_history[:-self.MAX_RECENT_ENTRIES]
        recent = self.tool_history[-self.MAX_RECENT_ENTRIES:]

        summary_lines = []
        for entry in early:
            first_line = entry.split('\n')[0]
            summary_lines.append(first_line)

        summary = "[更早的工具调用]\n" + "\n".join(summary_lines)
        recent_text = "\n\n".join(recent)

        full_text = f"{summary}\n\n{recent_text}"
        # 最终兜底：总字符数超限时截断早期摘要
        if len(full_text) > self.MAX_HISTORY_CHARS:
            overflow = len(full_text) - self.MAX_HISTORY_CHARS
            summary = summary[:max(0, len(summary) - overflow)]
            full_text = f"{summary}\n\n{recent_text}"

        return full_text

    async def _run_simple(self, prompt: str, enhanced_system: str) -> str:
        """简单模式：Thought→Tool→Result 循环，自然终止"""
        for round_num in range(1, self.max_rounds + 1):
            current_prompt = prompt
            if self.tool_history:
                history_text = self._build_history_text()
                current_prompt = (
                    f"{prompt}\n\n"
                    f"### 工具调用记录\n"
                    f"{history_text}\n\n"
                    f"请根据以上工具返回的信息，继续调用工具或直接生成最终代码。"
                )

            # 安全阀：最后一轮强制生成，不执行工具
            if round_num >= self.max_rounds:
                logger.warning(f"{self.role_name} ReAct 达到安全阀上限 ({self.max_rounds} 轮), 强制生成")
                await self._emit_event("react_generating", {
                    "message": "基于搜索结果生成代码",
                    "round": round_num,
                    "tool_history_count": len(self.tool_history)
                })
                final_response = await self.call_llm_fn(
                    f"{current_prompt}\n\n### 注意：已达到工具调用上限，请直接生成最终代码。",
                    enhanced_system
                )
                self._add_step(ReActStep("final", final_response))
                return final_response

            try:
                response = await self.call_llm_fn(current_prompt, enhanced_system)
            except Exception as e:
                logger.error(f"{self.role_name} ReAct LLM 调用失败: {e}")
                return ""
            if not response:
                return ""

            tool_call = self._parse_tool_call(response)
            if not tool_call:
                logger.info(f"{self.role_name} ReAct 自然终止: 第 {round_num} 轮, 工具调用 {len(self.tool_history)} 次")
                self._add_step(ReActStep("final", response))
                return response

            tool_name = tool_call.get("tool", "")
            tool_params = tool_call.get("params", {})

            self._add_step(ReActStep(
                "action",
                f"执行工具: {tool_name}",
                tool_name=tool_name,
                tool_params=tool_params
            ))

            await self._emit_event("react_tool_call", {
                "message": f"正在搜索: {tool_name}",
                "tool": tool_name,
                "params": {k: str(v)[:100] for k, v in tool_params.items()},
                "round": round_num,
                "max_rounds": self.max_rounds
            })

            success, tool_result = await self._execute_tool(tool_name, tool_params)

            self.steps[-1].tool_result = tool_result
            self.steps[-1].success = success

            result_str = json.dumps(tool_result, ensure_ascii=False)[:1500]
            self.tool_history.append(
                f"第 {round_num} 轮工具调用: {tool_name}({json.dumps(tool_params, ensure_ascii=False)})\n"
                f"返回结果: {result_str}"
            )

            result_count = len(tool_result.get("results", [])) if isinstance(tool_result, dict) and success else 0
            await self._emit_event("react_tool_result", {
                "message": f"找到 {result_count} 条结果" if result_count else f"工具返回 {len(result_str)} 字符",
                "tool": tool_name,
                "result_count": result_count,
                "result_size": len(result_str),
                "round": round_num
            })

            logger.info(
                f"{self.role_name} ReAct 第 {round_num} 轮: 调用 {tool_name}, "
                f"成功={success}, 结果 {len(result_str)} 字符"
            )

        return ""

    async def _run_full(self, prompt: str, enhanced_system: str) -> str:
        """完整模式：Thought→Action→Observation→Reflection→Final，反射终止

        与 ReActAgent.process() 等价，使用 ReActEngine 的工具和 LLM 调用能力。
        """
        task = prompt
        if self.memory:
            self.memory.add_user_message(task)

        await self._stream(f"[ReAct Agent] 开始处理任务: {task[:50]}...\n\n")

        for iteration in range(self.max_rounds):
            logger.info(f"{self.role_name} ReAct 全模式 迭代 {iteration + 1}/{self.max_rounds}")

            # Thought
            thought_prompt = f"""分析以下任务，决定下一步行动：

任务：{task}

当前状态：
{self._build_context()}

请分析：
1. 任务的核心目标是什么？
2. 已有哪些信息？
3. 还需要什么？
4. 下一步应该做什么？

请用简洁的语言描述你的思考。"""

            try:
                thought = await self.call_llm_fn(thought_prompt, enhanced_system)
            except Exception as e:
                logger.error(f"{self.role_name} ReAct 全模式 LLM 调用失败: {e}")
                return ""
            self._add_step(ReActStep("thought", thought))
            await self._stream(f"[思考] {thought}\n\n")

            # Action - 决定并执行工具
            action_prompt = f"""基于以下思考，决定执行什么动作：

思考：{thought}

当前状态：
{self._build_context()}

请决定使用哪个工具，以 JSON 格式返回：
{{"tool": "工具名", "params": {{"参数名": "值"}}}}"""

            try:
                action_response = await self.call_llm_fn(action_prompt, enhanced_system)
            except Exception as e:
                logger.error(f"{self.role_name} ReAct 全模式 Action LLM 调用失败: {e}")
                return ""
            tool_call = self._parse_tool_call(action_response)

            if not tool_call:
                # LLM 没有调用工具 → 直接作为最终答案
                self._add_step(ReActStep("final", action_response))
                if self.memory:
                    self.memory.add_assistant_message(action_response)
                return action_response

            tool_name = tool_call.get("tool", "")
            tool_params = tool_call.get("params", {})

            self._add_step(ReActStep(
                "action", f"执行工具: {tool_name}",
                tool_name=tool_name, tool_params=tool_params
            ))
            await self._stream(f"[动作] {tool_name}({tool_params})\n")

            await self._emit_event("react_tool_call", {
                "message": f"正在搜索: {tool_name}",
                "tool": tool_name,
                "params": {k: str(v)[:100] for k, v in tool_params.items()},
                "round": iteration + 1,
                "max_rounds": self.max_rounds
            })

            success, tool_result = await self._execute_tool(tool_name, tool_params)
            self.steps[-1].tool_result = tool_result
            self.steps[-1].success = success

            result_str = json.dumps(tool_result, ensure_ascii=False)[:1500]
            self.tool_history.append(
                f"工具调用: {tool_name}({json.dumps(tool_params, ensure_ascii=False)})\n"
                f"返回结果: {result_str}"
            )

            # Observation
            status = "SUCCESS" if success else "FAILED"
            observe_prompt = f"""分析以下执行结果：

状态：{status}
结果：{result_str}

请分析：
1. 这个结果说明了什么？
2. 任务是否完成？
3. 是否需要继续？

请用简洁的语言描述观察结果。"""

            try:
                observation = await self.call_llm_fn(observe_prompt, enhanced_system)
            except Exception as e:
                logger.error(f"{self.role_name} ReAct 全模式 Observation LLM 调用失败: {e}")
                observation = f"观察失败: {e}"
            self._add_step(ReActStep("observation", observation))
            await self._stream(f"[观察] {observation}\n\n")

            if self.memory:
                self.memory.add_tool_result(tool_name, result_str, success)

            # Reflection
            reflection = await self._reflect(task, self.steps)
            ref_text = reflection.get("reflection", "")
            self._add_step(ReActStep("reflection", ref_text))
            await self._stream(f"[反思] {ref_text}\n\n")

            if self.memory:
                self.memory.add_reflection(
                    f"任务: {task[:50]}... | 反思: {ref_text}",
                    {"task": task, "steps": len(self.steps)}
                )

            should_stop = (
                not reflection.get("continue", False)
                or reflection.get("task_complete", False)
            )
            if should_stop:
                break

        # 生成最终答案
        final_answer = await self._generate_final_answer(task, self.steps)
        self._add_step(ReActStep("final", final_answer))
        await self._stream(f"[最终答案]\n{final_answer}\n")

        if self.memory:
            self.memory.add_assistant_message(final_answer)

        return final_answer

    def _build_context(self) -> str:
        """构建上下文（full 模式用）"""
        parts = []

        if self.tool_history:
            parts.append("工具调用记录：")
            for h in self.tool_history[-3:]:
                parts.append(f"- {h[:200]}")

        if self.memory:
            memory_context = self.memory.get_context_for_prompt(max_tokens=1000)
            if memory_context:
                parts.append(f"记忆：{memory_context}")

        return "\n".join(parts) if parts else "无"
