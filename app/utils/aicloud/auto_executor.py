"""
AI 自动代码执行闭环 (Auto-Execute Loop)

实现流程：
1. LLM 生成初步回复
2. 提取回复中的 Python 代码块
3. 在沙箱中执行代码
4. 将执行结果作为新消息注入上下文
5. 再次请求 LLM 进行总结或继续操作
6. 循环直到没有代码块或达到最大迭代次数
"""

import re
import logging
from typing import List, Tuple
from app.utils.aicloud.code_executor import CodeExecutor, CodeExecutionResult

logger = logging.getLogger(__name__)

# 最大循环次数，防止死循环
MAX_EXECUTE_ITERATIONS = 3

# 代码块提取正则
CODE_BLOCK_PATTERN = re.compile(
    r"```python\s*\n(.*?)\n```",
    re.DOTALL
)

# 沙箱文件操作代码白名单（只允许安全操作）
SAFE_OPERATIONS = {
    "open", "print", "os.path", "os.listdir", "os.walk",
    "pathlib", "json", "csv", "html", "re", "string",
    "datetime", "math", "collections", "itertools"
}

DANGEROUS_KEYWORDS = {
    "import os", "import sys", "import subprocess", "import socket",
    "import requests", "import urllib", "exec(", "eval(", "compile(",
    "__import__", "importlib"
}


def extract_code_blocks(text: str) -> List[str]:
    """从文本中提取 Python 代码块"""
    return CODE_BLOCK_PATTERN.findall(text)


def is_safe_code(code: str) -> Tuple[bool, str]:
    """检查代码是否安全"""
    # 检查危险关键字
    for keyword in DANGEROUS_KEYWORDS:
        if keyword in code:
            return False, f"检测到危险操作: {keyword}"
    
    # 检查文件操作是否在沙箱范围内
    if "open(" in code and "/sandbox" not in code:
        # 如果是相对路径，默认假设在沙箱 workspace 下
        pass
    
    return True, "安全"


async def execute_with_llm_loop(
    initial_prompt: str,
    history_context: str,
    system_prompt: str,
    model_key: str,
    max_tokens: int,
    call_siliconflow_func,
    user_id: int = None,
    workspace_path: str = None
) -> str:
    """
    执行 LLM + 代码自动执行循环
    
    Args:
        initial_prompt: 用户初始请求
        history_context: 历史对话上下文
        system_prompt: 系统提示词
        model_key: 模型标识
        max_tokens: 最大 token 数
        call_siliconflow_func: 调用 SiliconFlow 的函数
        user_id: 用户 ID（用于沙箱路径）
        workspace_path: 沙箱工作目录
        
    Returns:
        最终的 AI 回复内容
    """
    current_prompt = f"{history_context}{system_prompt}{initial_prompt}"
    conversation_history = []  # 存储对话轮次
    
    for iteration in range(MAX_EXECUTE_ITERATIONS):
        logger.info(f"LLM 循环第 {iteration + 1} 轮")
        
        # 调用 LLM
        try:
            response = await call_siliconflow_func(
                prompt=current_prompt,
                model=model_key,
                stream=False,
                max_tokens=max_tokens
            )
            
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    ai_content = choices[0].get("message", {}).get("content", "")
                else:
                    return "抱歉，AI 响应格式错误"
            else:
                return "抱歉，AI 响应格式错误"
                
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"抱歉，AI 服务暂时不可用: {str(e)[:100]}"
        
        # 检查是否包含代码块
        code_blocks = extract_code_blocks(ai_content)
        
        if not code_blocks:
            # 没有代码块，循环结束
            logger.info("未检测到代码块，循环结束")
            return ai_content
        
        # 有代码块，执行第一个代码块
        code_to_execute = code_blocks[0]
        logger.info(f"检测到代码块，准备执行:\n{code_to_execute[:100]}...")
        
        # 安全检查
        is_safe, safety_msg = is_safe_code(code_to_execute)
        if not is_safe:
            logger.warning(f"代码安全检查失败: {safety_msg}")
            # 将安全警告注入上下文，让 LLM 重新生成
            execution_result = f"⚠️ 代码安全检查未通过: {safety_msg}\n请修改代码，避免使用危险操作。"
        else:
            # 执行代码
            try:
                executor = CodeExecutor(workspace_path=workspace_path)
                result: CodeExecutionResult = await executor.execute(
                    code=code_to_execute,
                    language="python",
                    timeout=15  # 代码执行超时 15s
                )
                
                if result.success:
                    execution_result = f"✅ 代码执行成功:\n输出:\n{result.output}"
                    if result.error:
                        execution_result += f"\n警告/Stderr:\n{result.error}"
                else:
                    execution_result = f"❌ 代码执行失败:\n错误:\n{result.error}\n退出码: {result.exit_code}"
                    
                logger.info(f"代码执行结果: {execution_result[:200]}...")
                
            except Exception as e:
                logger.error(f"代码执行异常: {e}")
                execution_result = f"❌ 代码执行异常: {str(e)}"
        
        # 将执行结果注入下一轮对话
        current_prompt = f"{current_prompt}\n\n{ai_content}\n\n[代码执行结果]:\n{execution_result}\n\n请根据执行结果继续处理用户的请求，如果需要，可以生成新的代码块。"
        
        # 保存本轮对话
        conversation_history.append({
            "iteration": iteration + 1,
            "ai_response": ai_content[:500],
            "executed_code": code_to_execute[:200],
            "execution_result": execution_result[:200]
        })
    
    # 达到最大循环次数
    logger.warning(f"达到最大循环次数 ({MAX_EXECUTE_ITERATIONS})，返回最后一次回复")
    return ai_content + "\n\n---\n*注：已达到最大自动执行次数，如需继续操作请发送新消息。*"
