"""
Human Approval Node - 人工审批节点

暂停工作流执行，等待用户确认/拒绝
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional, Callable

from app.schema.workflow import TaskType, TaskStatus
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)


class HumanApprovalNode(TaskNodeBase):
    """
    人工审批节点

    暂停工作流执行，等待用户确认或拒绝

    参数:
        prompt: 审批提示信息（必填）
        options: 审批选项列表（可选，默认 ["approve", "reject"]）
        default_option: 默认选项（可选，默认 "reject"）
        timeout: 超时时间（秒，可选，默认 300）
        input_variable: 从上下文读取的变量名（可选，展示给用户参考）
        output_variable: 审批结果存入上下文的变量名（可选，默认 "approval_result"）
    """

    task_type = TaskType.HUMAN_APPROVAL

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)
        self._approval_callback: Optional[Callable] = None

    def set_approval_callback(self, callback: Callable):
        """设置审批回调函数"""
        self._approval_callback = callback

    def get_required_params(self) -> List[str]:
        return ["prompt"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "options": ["approve", "reject"],
            "default_option": "reject",
            "timeout": 300,
            "input_variable": None,
            "output_variable": "approval_result",
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "prompt" not in self.params:
            errors.append("Missing required parameter: prompt")
        elif not isinstance(self.params["prompt"], str):
            errors.append("Parameter 'prompt' must be a string")

        if "timeout" in self.params:
            timeout = self.params["timeout"]
            if not isinstance(timeout, (int, float)):
                errors.append("Parameter 'timeout' must be a number")
            elif timeout < 1 or timeout > 3600:
                errors.append("Parameter 'timeout' must be between 1 and 3600")

        if "options" in self.params:
            opts = self.params["options"]
            if not isinstance(opts, list) or len(opts) < 2:
                errors.append("Parameter 'options' must be a list with at least 2 items")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行审批流程

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 审批结果
        """
        prompt = self.params["prompt"]
        options = self.params.get("options", ["approve", "reject"])
        default_option = self.params.get("default_option", "reject")
        timeout = self.params.get("timeout", 300)
        input_variable = self.params.get("input_variable")
        output_variable = self.params.get("output_variable", "approval_result")

        # 构建审批信息
        approval_info = {
            "prompt": prompt,
            "options": options,
            "node_id": self.node_id,
        }

        if input_variable and input_variable in context:
            approval_info["context_data"] = context[input_variable]

        logger.info(f"[{self.node_id}] 等待人工审批 | timeout={timeout}s")

        if self._approval_callback:
            try:
                result = await asyncio.wait_for(
                    self._approval_callback(approval_info),
                    timeout=timeout
                )

                if result is None:
                    result = default_option

                approved = result.get("approved", False) if isinstance(result, dict) else result == "approve"
                selected_option = result.get("option", result) if isinstance(result, dict) else result

                logger.info(f"[{self.node_id}] 审批完成 | option={selected_option} | approved={approved}")

                return NodeResult.success_result(
                    data={
                        "approved": approved,
                        "option": selected_option,
                        "output_variable": output_variable,
                    },
                    metadata={"approved": approved, "option": selected_option}
                )

            except asyncio.TimeoutError:
                logger.warning(f"[{self.node_id}] 审批超时，使用默认选项: {default_option}")
                return NodeResult.success_result(
                    data={
                        "approved": default_option == "approve",
                        "option": default_option,
                        "timeout": True,
                        "output_variable": output_variable,
                    },
                    metadata={"approved": default_option == "approve", "timeout": True}
                )
        else:
            # 无回调时自动批准（用于测试或无人值守模式）
            logger.warning(f"[{self.node_id}] 无审批回调，自动批准")
            return NodeResult.success_result(
                data={
                    "approved": True,
                    "option": "auto_approve",
                    "output_variable": output_variable,
                },
                metadata={"approved": True, "auto": True}
            )
