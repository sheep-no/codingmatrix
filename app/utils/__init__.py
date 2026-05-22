"""
app.utils - 工具模块全局入口

提供全局通用的工具函数，所有模块可从此处导入。
"""

from app.utils.llm_caller import call_llm, get_adapter

__all__ = ["call_llm", "get_adapter"]
