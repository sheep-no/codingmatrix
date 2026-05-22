"""
统一模型调用层 - 全局入口

从 app.utils.aicloud.llm_caller 导入，提供全局 `call_llm()` 函数。
所有 Agent、API、Utils 模块都应该使用这个统一接口调用模型。

用法：
    from app.utils import call_llm
    
    result = await call_llm(model="Qwen/Qwen3.5-4B", prompt="你好")
"""

from app.utils.aicloud.llm_caller import call_llm, get_adapter, ADAPTER_FACTORIES

__all__ = ["call_llm", "get_adapter", "ADAPTER_FACTORIES"]
