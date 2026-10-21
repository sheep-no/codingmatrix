"""Celery 任务专用异常。

将 Celery 内部信号（如 SoftTimeLimitExceeded）转换为带语义的领域异常，
供上层日志、监控与兜底逻辑识别，避免裸 Exception 混淆真实错误来源。
"""


class AgentTaskTimeoutError(Exception):
    """Agent 生成类任务软超时（由 SoftTimeLimitExceeded 转换而来）。"""
