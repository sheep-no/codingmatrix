"""
LLM Call Node - LLM 调用节点

调用大语言模型进行文本生成、分析、翻译等任务
"""

import logging
from typing import Any, Dict, List, Optional

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult
from app.utils import call_llm
from app.agent.models import DEFAULT_FAST_MODEL

logger = logging.getLogger(__name__)

# 8C8G 环境推荐模型
DEFAULT_MODEL = DEFAULT_FAST_MODEL
FALLBACK_MODEL = DEFAULT_FAST_MODEL


class LLMCallNode(TaskNodeBase):
    """
    LLM 调用节点

    调用大语言模型处理文本任务

    参数:
        prompt: 提示词（必填）
        model: 模型名称（可选，默认 Qwen3-8B）
        system_prompt: 系统提示词（可选）
        temperature: 温度参数（可选，默认 0.7）
        max_tokens: 最大生成长度（可选，默认 2048）
        input_variable: 从上下文读取的变量名（可选，插入到 prompt 中）
        output_variable: 结果存入上下文的变量名（可选，默认 "llm_result"）
    """

    task_type = TaskType.LLM_CALL

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return ["prompt"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "model": DEFAULT_MODEL,
            "system_prompt": "",
            "temperature": 0.7,
            "max_tokens": 2048,
            "input_variable": None,
            "output_variable": "llm_result",
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "prompt" not in self.params:
            errors.append("Missing required parameter: prompt")
        elif not isinstance(self.params["prompt"], str):
            errors.append("Parameter 'prompt' must be a string")
        elif len(self.params["prompt"].strip()) == 0:
            errors.append("Parameter 'prompt' cannot be empty")

        if "temperature" in self.params:
            temp = self.params["temperature"]
            if not isinstance(temp, (int, float)):
                errors.append("Parameter 'temperature' must be a number")
            elif temp < 0 or temp > 2:
                errors.append("Parameter 'temperature' must be between 0 and 2")

        if "max_tokens" in self.params:
            mt = self.params["max_tokens"]
            if not isinstance(mt, int):
                errors.append("Parameter 'max_tokens' must be an integer")
            elif mt < 1 or mt > 8192:
                errors.append("Parameter 'max_tokens' must be between 1 and 8192")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        调用 LLM

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 执行结果
        """
        prompt = self.params["prompt"]
        model = self.params.get("model", DEFAULT_MODEL)
        system_prompt = self.params.get("system_prompt", "")
        temperature = self.params.get("temperature", 0.7)
        max_tokens = self.params.get("max_tokens", 2048)
        input_variable = self.params.get("input_variable")
        output_variable = self.params.get("output_variable", "llm_result")

        # 从上下文读取变量并插入 prompt
        if input_variable and input_variable in context:
            input_value = context[input_variable]
            if isinstance(input_value, (dict, list)):
                import json
                input_value = json.dumps(input_value, ensure_ascii=False, indent=2)
            prompt = prompt.replace("{{input}}", str(input_value))

        # 构建完整 prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        logger.info(f"[{self.node_id}] LLM 调用 | model={model} | prompt_len={len(full_prompt)}")

        try:
            response = await call_llm(
                model=model,
                prompt=full_prompt,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if response is None:
                return NodeResult.error_result(error="LLM returned empty response")

            # 提取内容
            content = response
            if hasattr(response, "choices"):
                content = response.choices[0].message.content
            elif isinstance(response, dict):
                content = response.get("content", response.get("text", str(response)))

            result_data = {
                "content": str(content),
                "model": model,
                "output_variable": output_variable,
            }

            logger.info(f"[{self.node_id}] LLM 调用完成 | response_len={len(str(content))}")

            return NodeResult.success_result(
                data=result_data,
                metadata={"model": model, "output_variable": output_variable}
            )

        except Exception as e:
            error_msg = f"LLM call failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)
