"""
Agent 执行器 + 分析工具注册表

从 multi_model_agent.py 拆分而来，保持向后兼容。
execute_analysis 使用 ReActEngine（simple 模式），不再维护独立的 ReAct 循环。
"""

import logging
from typing import Dict, Any

from app.utils import call_llm
from app.utils.file_operator import FileOperator
from app.agent.tools import (
    _tool_read_file, _tool_list_files, _tool_read_symbols,
    _tool_read_imports, _tool_summarize_file, _tool_run_command,
)

logger = logging.getLogger(__name__)

# 分析任务可用的只读工具（SPECIALIST_TOOLS 的子集）
ANALYSIS_TOOLS = {
    "read_file": {
        "fn": _tool_read_file,
        "description": "读取文件内容，支持分页。参数: file_path, offset(起始行), limit(行数)",
        "params": {"file_path": "string", "offset": "int(可选)", "limit": "int(可选)"}
    },
    "list_files": {
        "fn": _tool_list_files,
        "description": "列出目录结构。参数: directory(目录路径), max_depth(深度)",
        "params": {"directory": "string(可选)", "max_depth": "int(可选)"}
    },
    "read_symbols": {
        "fn": _tool_read_symbols,
        "description": "提取文件的函数和类签名（不读函数体）。参数: file_path",
        "params": {"file_path": "string"}
    },
    "read_imports": {
        "fn": _tool_read_imports,
        "description": "提取文件的 import 语句，分析依赖关系。参数: file_path",
        "params": {"file_path": "string"}
    },
    "summarize_file": {
        "fn": _tool_summarize_file,
        "description": "返回文件摘要：导出的符号、行数、语言、依赖数。参数: file_path",
        "params": {"file_path": "string"}
    },
    "run_command": {
        "fn": _tool_run_command,
        "description": "执行终端命令（搜索代码、统计行数等）。参数: command, cwd(可选), timeout(可选,默认60)。"
                       "grep 示例: grep -rn --include='*.py' 'pattern' . | head -20  "
                       "find 示例: find . -name '*.py' | xargs wc -l",
        "params": {"command": "string", "cwd": "string(可选)", "timeout": "int(可选,默认60)"}
    },
}

# 分析任务的系统 prompt（ReActEngine 会自动追加工具描述和调用格式）
_ANALYSIS_SYSTEM_PROMPT = (
    "你是一个代码分析专家。使用工具搜索和读取项目文件，然后给出分析结果。\n\n"
    "### 重要规则\n"
    "1. 每次只调用一个工具\n"
    "2. 收到工具结果后，继续调用工具或生成最终分析\n"
    "3. 收集完信息后，直接输出文字分析结果，不要返回 JSON\n"
    "4. 工具调用期间，只返回 {\"tool\": \"...\", \"params\": {...}} 格式\n"
)


class AgentExecutor:
    """执行器 - 执行具体的任务步骤"""

    def __init__(self, file_operator: FileOperator):
        self.file_operator = file_operator

    async def execute_file_operation(self, params: Dict) -> Dict:
        """执行文件操作"""
        operation = params.get("operation")
        path = params.get("path")

        if operation == "read":
            return await self.file_operator.read_async(path)
        elif operation == "write":
            content = params.get("content", "")
            return await self.file_operator.write_async(path, content)
        elif operation == "delete":
            return self.file_operator.delete(path)
        elif operation == "create":
            return self.file_operator.create(
                path,
                is_directory=params.get("is_directory", False),
                content=params.get("content", "")
            )

        return {"error": f"未知操作: {operation}"}

    async def execute(self, step: Dict) -> Dict:
        """执行单个步骤"""
        step_type = step.get("type")
        params = step.get("params", {})

        if step_type == "file_operation":
            return await self.execute_file_operation(params)
        elif step_type == "ai_call":
            return {"status": "pending", "task": params.get("task")}
        else:
            return {"error": f"未知步骤类型: {step_type}"}

    async def execute_analysis(
        self,
        task: str,
        project_path: str,
        model_name: str = "Qwen/Qwen3-8B",
        max_rounds: int = 10,
        api_key_token: str = None,
    ) -> Dict:
        """执行分析任务（ReAct 工具调用循环）

        只读操作，不修改文件。使用 ANALYSIS_TOOLS 搜索和读取项目文件。
        委托给 ReActEngine（simple 模式），不再维护独立的循环。

        Returns:
            {"success": True, "analysis": "分析结果文本", "tool_calls": N}
        """
        from app.agent.react_engine import ReActEngine

        async def call_llm_fn(prompt: str, system_prompt: str) -> str:
            response = await call_llm(
                model=model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                stream=False,
                max_tokens=8192,
                temperature=0.7,
                api_key_token=api_key_token,
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")

        engine = ReActEngine(
            tools=ANALYSIS_TOOLS,
            call_llm_fn=call_llm_fn,
            project_path=project_path,
            max_rounds=max_rounds,
            mode="simple",
            role_name="Analysis",
        )

        try:
            analysis = await engine.run(task, _ANALYSIS_SYSTEM_PROMPT)
            tool_call_count = sum(1 for s in engine.steps if s.step_type == "action")
            if not analysis:
                return {"success": False, "error": "分析任务未产生输出", "tool_calls": tool_call_count}
            return {"success": True, "analysis": analysis, "tool_calls": tool_call_count}
        except Exception as e:
            logger.error(f"分析任务失败: {e}")
            return {"success": False, "error": f"分析失败: {str(e)}", "tool_calls": 0}
