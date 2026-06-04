"""
任务规划器

从 multi_model_agent.py 拆分而来，保持向后兼容。
支持 ReAct 工具调用：在拆解前先用工具了解项目结构。
"""

import json
import logging
from typing import Optional, Dict, Any, List

from pydantic import ValidationError

from app.utils import call_llm
from app.agent.json_parser import safe_parse_json
from app.agent.models import ModelRegistry
from app.agent.file_contract import TaskStep, _degrade_step

logger = logging.getLogger(__name__)


class TaskPlanner:
    """任务规划器 - 将复杂任务拆解为可执行的步骤

    支持两种模式：
    - 盲拆：无 project_path，直接 LLM 拆解（原有行为）
    - ReAct 探索：有 project_path + tools 时，先用工具了解项目再拆解
    """

    def __init__(self, model_key: str = "deepseek-r1-qwen3-8b"):
        self.model = ModelRegistry.get(model_key)

    async def decompose(
        self,
        task: str,
        context: Dict[str, Any] = None,
        dependency_hints: Optional[str] = None,
        project_path: Optional[str] = None,
        tools: Optional[Dict[str, Dict]] = None,
    ) -> List[Dict]:
        """
        分解任务

        Args:
            task: 任务描述
            context: 上下文信息
            dependency_hints: 依赖图提示
            project_path: 项目路径（传入后启用 ReAct 探索）
            tools: 可用工具（传入后启用 ReAct 探索）

        Returns:
            任务步骤列表，每个步骤包含 type, description, params
        """
        # ReAct 探索：先用工具了解项目结构
        project_info = ""
        if project_path and tools:
            project_info = await self._explore_project(task, project_path, tools)

        hint_block = ""
        if dependency_hints:
            hint_block = f"""

项目依赖图信息（来自 DependencyGraph）：
{dependency_hints}

要求：
- 严格遵守文件生成顺序：先生成无依赖的底层文件（models/config），再生成依赖上层文件（services/apis）
- 受影响的下游文件必须在源文件之后处理
- 同一层级的文件可并行生成（在 params 中标记 `parallel: true`）
"""

        context_block = json.dumps(context or {}, indent=2, ensure_ascii=False)
        if project_info:
            context_block += f"\n\n项目探索结果：\n{project_info}"

        prompt = f"""将以下任务分解为可执行的步骤：

任务：{task}

上下文：
{context_block}
{hint_block}
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

            parsed = safe_parse_json(content)
            if not isinstance(parsed, (list, dict)):
                logger.warning(f"任务分解响应无法解析，降级执行: {content[:200]}")
                return [_degrade_step(task, "解析失败")]

            if not isinstance(parsed, list):
                parsed = [parsed]

            try:
                return [TaskStep.model_validate(s).model_dump() for s in parsed]
            except ValidationError as e:
                logger.warning(f"任务分解 schema 校验失败，降级执行: {e}")
                err_msg = e.errors()[0]["msg"] if e.errors() else str(e)
                return [_degrade_step(task, f"schema 错误: {err_msg}")]
        except Exception as e:
            logger.error(f"任务分解失败: {e}")
            return [_degrade_step(task, f"异常: {str(e)}")]

    async def _explore_project(
        self,
        task: str,
        project_path: str,
        tools: Dict[str, Dict],
    ) -> str:
        """用 ReAct 工具探索项目结构，返回项目信息摘要

        只做 2 轮探索（list_files + 1 个针对性工具），不消耗太多 token。
        """
        from app.agent.react_engine import ReActEngine

        async def call_llm_fn(prompt: str, system_prompt: str) -> str:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                system_prompt=system_prompt,
                stream=False,
                max_tokens=2048,
                temperature=0.3,
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 只用只读工具
        read_only_tools = {
            k: v for k, v in tools.items()
            if k in ("list_files", "read_file", "read_symbols", "summarize_file", "run_command")
        }

        if not read_only_tools:
            return ""

        engine = ReActEngine(
            tools=read_only_tools,
            call_llm_fn=call_llm_fn,
            project_path=project_path,
            max_rounds=3,
            mode="simple",
            role_name="TaskPlanner",
        )

        explore_prompt = (
            f"快速了解项目结构，为以下任务做准备：{task}\n\n"
            "请先列出项目目录结构，然后查看关键文件。只需要了解项目概况，不需要深入分析。"
        )

        try:
            result = await engine.run(explore_prompt, "你是项目探索助手。快速了解项目结构。")
            logger.info(f"TaskPlanner 项目探索完成: {len(result)} 字符, {len(engine.steps)} 步骤")
            return result[:3000]
        except Exception as e:
            logger.warning(f"TaskPlanner 项目探索失败（降级为盲拆）: {e}")
            return ""
