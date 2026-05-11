"""
Task Decomposer - 任务分解器

使用 LLM 将自然语言请求分解为任务图 JSON
"""

import logging
import json
import uuid
from typing import Dict, List, Any, Optional

from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.AiCodeUtil import call_siliconflow

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"


class TaskDecomposerError(Exception):
    """任务分解器异常"""
    pass


class TaskDecomposer:
    """
    任务分解器

    使用 LLM 将自然语言请求分解为结构化任务图
    """

    SYSTEM_PROMPT = """你是一个任务规划专家。你的任务是将用户的自然语言请求分解为结构化的任务图。

任务图格式：
{
  "nodes": [
    {
      "id": "node_1",
      "type": "web_search|code_execution|chart_generation|file_processing",
      "params": {...},
      "depends_on": []
    }
  ]
}

支持的节点类型：
1. web_search - 执行网络搜索
   params: query, count, lang, with_summary
2. code_execution - 执行代码
   params: code, language, timeout
3. chart_generation - 生成图表
   params: chart_type, title, data, x_label, y_label
4. file_processing - 处理文件
   params: operation, path, content

注意：
- 每个节点必须有唯一 ID (如 node_1, node_2)
- depends_on 表示依赖关系，空数组表示无依赖
- 必须遵循依赖顺序：A 依赖 B 时，A 的 depends_on 应包含 B
- params 根据节点类型包含相应参数

请直接返回 JSON，不要包含任何解释。"""

    USER_PROMPT_TEMPLATE = """将以下自然语言请求分解为任务图：

"{request}"

请直接返回 JSON 格式的任务图。"""

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        初始化任务分解器

        Args:
            model: 使用的模型
        """
        self.model = model

    async def decompose(self, request: str) -> TaskGraph:
        """
        将自然语言请求分解为任务图

        Args:
            request: 自然语言请求

        Returns:
            TaskGraph: 任务图

        Raises:
            TaskDecomposerError: 分解失败
        """
        try:
            prompt = self._build_prompt(request)
            response = await call_siliconflow(
                prompt=prompt,
                model=self.model,
                stream=False,
                temperature=0.3,
            )

            task_graph = self._parse_response(response, request)
            return task_graph

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            raise TaskDecomposerError(f"无法解析 LLM 响应为 JSON: {e}")
        except Exception as e:
            logger.error(f"任务分解失败: {e}")
            raise TaskDecomposerError(f"任务分解失败: {e}")

    def _build_prompt(self, request: str) -> str:
        """
        构建提示词

        Args:
            request: 自然语言请求

        Returns:
            完整提示词
        """
        return f"{self.SYSTEM_PROMPT}\n\n{self.USER_PROMPT_TEMPLATE.format(request=request)}"

    def _parse_response(self, response: Any, original_request: str) -> TaskGraph:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应
            original_request: 原始请求

        Returns:
            TaskGraph
        """
        if isinstance(response, dict):
            choices = response.get('choices')
            if choices and len(choices) > 0:
                message = choices[0].get('message', {})
                content = message.get('content', '')
            else:
                content = str(response)
        elif hasattr(response, 'choices'):
            content = response.choices[0].message.content
        else:
            content = str(response)

        content = content.strip()

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败，原始内容: {content[:500]}")
            raise TaskDecomposerError(f"无法解析 LLM 响应为 JSON: {e}")

        nodes = []
        for node_data in data.get("nodes", []):
            node_type_str = node_data.get("type", "")
            try:
                node_type = TaskType(node_type_str)
            except ValueError:
                logger.warning(f"未知节点类型: {node_type_str}，跳过")
                continue

            node = TaskNode(
                id=node_data.get("id", f"node_{len(nodes) + 1}"),
                type=node_type,
                params=node_data.get("params", {}),
                depends_on=node_data.get("depends_on", []),
            )
            nodes.append(node)

        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"

        return TaskGraph(
            workflow_id=workflow_id,
            nodes=nodes,
        )

    def validate_result(self, task_graph: TaskGraph) -> List[str]:
        """
        验证分解结果

        Args:
            task_graph: 任务图

        Returns:
            错误列表，空列表表示有效
        """
        errors = []

        if not task_graph.nodes:
            errors.append("任务图中没有节点")

        node_ids = [node.id for node in task_graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("存在重复的节点 ID")

        for node in task_graph.nodes:
            if node.type not in TaskType:
                errors.append(f"节点 {node.id} 有无效类型: {node.type}")

            for dep_id in node.depends_on:
                if dep_id not in node_ids:
                    errors.append(f"节点 {node.id} 依赖不存在的节点: {dep_id}")

        return errors


async def decompose_request(
    request: str,
    model: str = DEFAULT_MODEL
) -> TaskGraph:
    """
    便捷函数：分解自然语言请求

    Args:
        request: 自然语言请求
        model: 使用的模型

    Returns:
        TaskGraph
    """
    decomposer = TaskDecomposer(model=model)
    return await decomposer.decompose(request)
