import re
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import asyncio

from app.utils import call_llm
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter
from app.agent.tracing import traced
from app.agent.react_engine import ReActEngine
from app.agent.llm_client import LLMClient, LLMClientError, MAX_CONCURRENT_LLM_CALLS, get_global_semaphore as get_global_llm_semaphore
from app.agent.json_parser import parse_tool_call

# 工具注册表（从 tools.py 导入）
from app.agent.tools import SPECIALIST_TOOLS

logger = logging.getLogger(__name__)


# Re-export for backward compatibility
SpecialistCallError = LLMClientError

# ReAct 模式配置
_REACT_MODE_BY_COMPLEXITY = {
    "simple": "simple",
    "small": "simple",
    "medium": "full",
    "large": "full",
    "enterprise": "full",
}
_REACT_ROUNDS_BY_COMPLEXITY = {
    "simple": 3,
    "small": 4,
    "medium": 6,
    "large": 8,
    "enterprise": 10,
}
_REACT_MODE = "full"
_REACT_MAX_ROUNDS = 3


class Specialist:
    """专业角色基类"""

    def __init__(self, role_name: str, model_name: str, task_type: str = "generate",
                 api_key_token: Optional[str] = None, provider_id: Optional[str] = None,
                 semaphore: Optional[asyncio.Semaphore] = None, cost_tracker=None,
                 complexity: str = "medium", cancel_event: Optional[asyncio.Event] = None):
        self.role_name = role_name
        self.model_name = model_name
        self.task_type = task_type
        self.api_key_token = api_key_token
        self.model_config = LayeredModelRouter.get_model_config(model_name, task_type=task_type, api_key_token=api_key_token)
        self.provider_id = provider_id
        self._cost_tracker = cost_tracker
        self._edited_files: List[str] = []
        self._write_tools = {"partial_update", "insert_content", "regex_replace"}
        self._complexity = complexity
        self.cancel_event = cancel_event
        self._llm_client = LLMClient(
            model_name=model_name,
            task_type=task_type,
            api_key_token=api_key_token,
            provider_id=provider_id,
            cost_tracker=cost_tracker,
            complexity=complexity,
            semaphore=semaphore,
            cancel_event=cancel_event,
        )

    def get_edited_files(self) -> List[str]:
        """获取本轮通过工具直接编辑过的文件列表"""
        return self._edited_files.copy()

    def clear_edits(self):
        """清空编辑记录（每轮生成前调用）"""
        self._edited_files.clear()

    def update_edited_file_path(self, old_path: str, new_path: str):
        """更新编辑记录中的文件路径（文件移动时调用）

        Args:
            old_path: 旧的文件路径
            new_path: 新的文件路径
        """
        for i, f in enumerate(self._edited_files):
            if f == old_path:
                self._edited_files[i] = new_path
                logger.info(f"更新编辑记录: {old_path} -> {new_path}")
                return
        # 如果没找到精确匹配，尝试路径末尾匹配
        old_suffix = old_path.replace('\\', '/').lstrip('/')
        for i, f in enumerate(self._edited_files):
            if f.replace('\\', '/').endswith(old_suffix):
                self._edited_files[i] = new_path
                logger.info(f"更新编辑记录(后缀匹配): {f} -> {new_path}")
                return

    @traced("specialist.call_llm", attributes={"component": "specialist"})
    async def call_llm(self, prompt: str, system_prompt: str = "", stream: bool = False, thinking_budget: Optional[int] = None) -> str:
        """调用 LLM（委托给 LLMClient）

        Args:
            thinking_budget: 覆盖模型默认的 thinking budget（None=使用默认，0=禁用思考）
        """
        if thinking_budget is None:
            return await self._llm_client.call(prompt, system_prompt, stream)
        return await self._llm_client.call(
            prompt, system_prompt, stream, thinking_budget=thinking_budget
        )

    @staticmethod
    def _build_tools_description(tools: Dict[str, Dict]) -> str:
        """构建工具描述文本，注入 system prompt"""
        lines = []
        for name, info in tools.items():
            params_desc = ", ".join(f"{k}: {v}" for k, v in info["params"].items())
            lines.append(f"- {name}({params_desc}): {info['description']}")
        return "\n".join(lines)

    @staticmethod
    def _parse_tool_call(content: str) -> Optional[Dict]:
        """从 LLM 回复中解析单个工具调用（委托给 json_parser）"""
        return parse_tool_call(content)

    @traced("specialist.call_llm_with_tools", attributes={"component": "specialist"})
    async def call_llm_with_tools(
        self,
        prompt: str,
        system_prompt: str = "",
        tools: Optional[Dict[str, Dict]] = None,
        project_path: str = "",
        max_rounds: int = None,
        react_mode: Optional[str] = None,
        callback: Optional[Any] = None,
        heartbeat_tracker=None,
        enable_streaming_thinking: bool = False,
        thinking_budget: Optional[int] = None,
        required_tool_names: Optional[set[str]] = None,
        preverified_tool_names: Optional[set[str]] = None,
    ) -> str:
        """调用 LLM，支持 ReAct 工具调用循环

        LLM 可以在生成最终代码前，调用工具搜索/读取项目文件以获取上下文。
        采用自然终止：LLM 不再调用工具时自动结束，max_rounds 仅作安全阀。

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt
            tools: 可用工具注册表（默认使用 SPECIALIST_TOOLS）
            project_path: 项目路径（工具搜索用）
            max_rounds: 安全阀上限（防止无限循环，默认按复杂度分级）
            callback: 进度回调函数
            heartbeat_tracker: 心跳活动跟踪器
            enable_streaming_thinking: 启用真正的 LLM 流式 thinking 推送。
                启用后，LLM 每个 token 的 reasoning_content 都会通过 callback
                以 type='thinking' 流式推送到前端，前端按 agent+phase 聚合实现打字机效果。
            thinking_budget: 覆盖模型默认的 thinking budget（None=使用默认，0=禁用思考）

        Returns:
            LLM 最终输出的文本（代码）
        """
        if max_rounds is None:
            max_rounds = _REACT_ROUNDS_BY_COMPLEXITY.get(
                self._complexity, _REACT_MAX_ROUNDS
            )
        if tools is None:
            tools = SPECIALIST_TOOLS
            # 合并 MCP 工具（如果 MCPClientManager 已初始化）
            try:
                from app.agent.mcp_client import MCPClientManager
                mcp_manager = MCPClientManager.get_instance()
                if mcp_manager:
                    mcp_tools = mcp_manager.get_all_tools()
                    if mcp_tools:
                        tools = {**SPECIALIST_TOOLS, **mcp_tools}
            except Exception as e:
                logger.debug(f"MCP 工具合并失败（非致命，使用默认工具集）: {e}")

        selected_react_mode = react_mode or _REACT_MODE_BY_COMPLEXITY.get(
            self._complexity, _REACT_MODE
        )
        if selected_react_mode not in {"simple", "full"}:
            raise ValueError(f"不支持的 ReAct 模式: {selected_react_mode}")

        # 选择 LLM 调用函数：流式 thinking 或普通调用
        if enable_streaming_thinking and callback is not None:
            # 流式合并窗口（毫秒）：将 50ms 内的多个 chunk 合并为一次推送，
            # 避免 1 秒 30 个 token 时产生 30 个并发 queue.put 任务
            _merge_window_ms = 50
            # 每个 thinking session 一个合并缓冲区
            _merge_buffers: Dict[str, Dict[str, Any]] = {}
            _merge_tasks: Dict[str, asyncio.Task] = {}

            def _flush_buffer(key: str) -> None:
                """推送缓冲区的累积内容并清空"""
                buf = _merge_buffers.get(key)
                if not buf or not buf.get("message"):
                    return
                try:
                    self._emit_event(callback, "thinking", {
                        "agent": buf["agent"],
                        "model": buf["model"],
                        "message": buf["message"],
                        "accumulated": buf["accumulated"],
                        "streaming": True,
                        "phase": buf["phase"],
                    })
                finally:
                    buf["message"] = ""
                    _merge_tasks.pop(key, None)

            async def streaming_call_llm(p: str, s: str) -> str:
                """流式调用 LLM，每个 chunk 推送 thinking 事件

                合并窗口策略：50ms 内的多个 chunk 累积为一次 SSE 推送，
                大幅减少后端 queue.put 次数和前端 DOM 更新频率。
                """
                if heartbeat_tracker:
                    heartbeat_tracker.touch()

                # 本次调用的累积 reasoning_content（用于显示完整思考过程）
                accumulated_reasoning = ""
                # 本次调用的合并 key
                merge_key = f"{self.role_name}:{id(p)}"
                _merge_buffers[merge_key] = {
                    "agent": self.role_name,
                    "model": self.model_name,
                    "message": "",
                    "accumulated": "",
                    "phase": "llm_reasoning",
                }

                async def on_chunk(content_delta: str, reasoning_delta: str) -> None:
                    nonlocal accumulated_reasoning
                    # 在每个 chunk 中检查取消信号，及时终止 LLM 调用
                    if self.cancel_event and self.cancel_event.is_set():
                        raise asyncio.CancelledError("检测到取消信号，终止 LLM 流式调用")
                    if heartbeat_tracker:
                        heartbeat_tracker.touch()
                    if not reasoning_delta:
                        return
                    accumulated_reasoning += reasoning_delta
                    buf = _merge_buffers.get(merge_key)
                    if not buf:
                        return
                    buf["message"] += reasoning_delta
                    buf["accumulated"] = accumulated_reasoning

                    # 50ms 合并窗口：如果当前没有 flush 任务在跑，启动一个
                    if merge_key not in _merge_tasks or _merge_tasks[merge_key].done():
                        async def _delayed_flush():
                            await asyncio.sleep(_merge_window_ms / 1000.0)
                            _flush_buffer(merge_key)
                        _merge_tasks[merge_key] = asyncio.create_task(_delayed_flush())

                try:
                    result = await self._llm_client.call_stream(p, s, on_chunk=on_chunk, thinking_budget=thinking_budget)
                finally:
                    # 清理缓冲区
                    _merge_buffers.pop(merge_key, None)
                    task = _merge_tasks.pop(merge_key, None)
                    if task and not task.done():
                        task.cancel()
                if heartbeat_tracker:
                    heartbeat_tracker.touch()
                return result

            call_llm_fn = streaming_call_llm
        else:
            # 包装 call_llm_fn，在每次 LLM 调用前后更新 tracker
            original_call_llm = lambda p, s: self.call_llm(p, s, thinking_budget=thinking_budget)
            if heartbeat_tracker:
                async def tracked_call_llm(p, s):
                    heartbeat_tracker.touch()
                    result = await original_call_llm(p, s)
                    heartbeat_tracker.touch()
                    return result
                call_llm_fn = tracked_call_llm
            else:
                call_llm_fn = original_call_llm

        engine = ReActEngine(
            tools=tools,
            call_llm_fn=call_llm_fn,
            project_path=project_path,
            max_rounds=max_rounds,
            mode=selected_react_mode,
            callback=callback,
            emit_event_fn=self._emit_event,
            role_name=self.role_name,
            cancel_event=self.cancel_event,
            heartbeat_timeout=(
                heartbeat_tracker.timeout if heartbeat_tracker else 600.0
            ),
            heartbeat_tracker=heartbeat_tracker,
            required_tool_names=required_tool_names,
            preverified_tool_names=preverified_tool_names,
        )

        original_execute_tool = engine._execute_tool
        async def tracked_execute_tool(tool_name: str, tool_params: Dict):
            success, result = await original_execute_tool(tool_name, tool_params)
            if tool_name in self._write_tools and success and isinstance(result, dict) and result.get("success"):
                edited_path = tool_params.get("path", "")
                if edited_path:
                    full = str(Path(project_path) / edited_path) if not Path(edited_path).is_absolute() else edited_path
                    if full not in self._edited_files:
                        self._edited_files.append(full)
                    logger.info(f"{self.role_name} 工具编辑: {tool_name} -> {edited_path}")
            return success, result
        engine._execute_tool = tracked_execute_tool

        return await engine.run(prompt, system_prompt)

    @staticmethod
    def _emit_event(callback: Any, event_type: str, data: Dict):
        """推送事件到前端"""
        try:
            event = {"type": event_type, **data}
            result = callback(json.dumps(event, ensure_ascii=False))
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception as e:
            logger.debug(f"事件推送失败 ({event_type}): {e}")
