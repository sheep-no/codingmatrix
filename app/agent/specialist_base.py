import re
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import asyncio

import httpx
from app.utils.aicloud import call_llm
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

# 复杂度到 ReAct 模式的映射
# simple/small: 简单模式（1 次 LLM 调用/轮，快速）
# medium/large/enterprise: 完整模式（反思能力，免费模型补偿推理质量）
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


class Specialist:
    """专业角色基类"""

    def __init__(self, role_name: str, model_name: str, task_type: str = "generate",
                 api_key_token: Optional[str] = None, provider_id: Optional[str] = None,
                 semaphore: Optional[asyncio.Semaphore] = None, cost_tracker=None,
                 complexity: str = "medium"):
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
        self._llm_client = LLMClient(
            model_name=model_name,
            task_type=task_type,
            api_key_token=api_key_token,
            provider_id=provider_id,
            cost_tracker=cost_tracker,
            complexity=complexity,
            semaphore=semaphore,
        )

    def get_edited_files(self) -> List[str]:
        """获取本轮通过工具直接编辑过的文件列表"""
        return self._edited_files.copy()

    def clear_edits(self):
        """清空编辑记录（每轮生成前调用）"""
        self._edited_files.clear()

    @traced("specialist.call_llm", attributes={"component": "specialist"})
    async def call_llm(self, prompt: str, system_prompt: str = "", stream: bool = False) -> str:
        """调用 LLM（委托给 LLMClient）"""
        return await self._llm_client.call(prompt, system_prompt, stream)

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
        callback: Optional[Any] = None,
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

        Returns:
            LLM 最终输出的文本（代码）
        """
        if max_rounds is None:
            max_rounds = _REACT_ROUNDS_BY_COMPLEXITY.get(self._complexity, 6)
        if tools is None:
            tools = SPECIALIST_TOOLS

        react_mode = _REACT_MODE_BY_COMPLEXITY.get(self._complexity, "simple")

        engine = ReActEngine(
            tools=tools,
            call_llm_fn=lambda p, s: self.call_llm(p, s),
            project_path=project_path,
            max_rounds=max_rounds,
            mode=react_mode,
            callback=callback,
            emit_event_fn=self._emit_event,
            role_name=self.role_name,
        )

        original_execute_tool = engine._execute_tool
        def tracked_execute_tool(tool_name: str, tool_params: Dict):
            success, result = original_execute_tool(tool_name, tool_params)
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
