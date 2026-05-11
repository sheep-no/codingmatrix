"""
Sentry 错误追踪集成

支持：
- 异步错误捕获
- 性能监控
- 请求上下文关联
- 自定义标签和用户信息
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_sentry_initialized = False
_sentry_client = None


async def init_sentry(dsn: Optional[str] = None, environment: str = "production"):
    """
    初始化 Sentry SDK

    Args:
        dsn: Sentry DSN 地址，从环境变量 SENTRY_DSN 获取
        environment: 运行环境标识
    """
    global _sentry_initialized, _sentry_client

    if _sentry_initialized:
        return

    if not dsn:
        from app.core.config import settings
        dsn = getattr(settings, 'SENTRY_DSN', None)

    if not dsn:
        logger.info("Sentry DSN 未配置，跳过 Sentry 初始化")
        return

    try:
        import sentry_sdk
        from sentry_sdk import capture_message, capture_exception
        from sentry_sdk.integrations import asyncio as sentry_asyncio
        from sentry_sdk.integrations.fastapi import FastAPIIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        _sentry_client = sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            integrations=[
                sentry_asyncio.AsyncioIntegration(),
                FastAPIIntegration(auto_continue_trace=True),
                StarletteIntegration(),
            ],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            send_default_pii=False,
            max_breadcrumbs=50,
            attach_stacktrace=True,
            before_send=lambda event, hint: _before_send(event, hint),
        )

        _sentry_initialized = True
        logger.info(f"Sentry 初始化完成 | environment={environment}")

    except ImportError:
        logger.warning("sentry-sdk 未安装，跳过 Sentry 初始化")
    except Exception as e:
        logger.error(f"Sentry 初始化失败: {e}")


def _before_send(event, hint):
    """
    在发送错误前处理事件
    过滤敏感信息和无关错误
    """
    if 'log_record' in hint:
        log_record = hint['log_record']
        if hasattr(log_record, 'name'):
            if log_record.name in ['aiohttp.client', 'urllib3.connectionpool']:
                return None

    if event.get('platform') == 'python':
        if 'exception' in event:
            exc_values = event['exception']['values']
            for exc in exc_values:
                if 'ssl.SSLCertVerificationError' in exc.get('type', ''):
                    return None
                if 'ConnectionRefusedError' in exc.get('type', ''):
                    return None

    return event


def capture_error(error: Exception, **kwargs):
    """
    捕获错误到 Sentry

    Args:
        error: 异常对象
        **kwargs: 额外参数 (extra, tags, user_id 等)
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            if 'extra' in kwargs:
                for key, value in kwargs['extra'].items():
                    scope.set_extra(key, value)

            if 'tags' in kwargs:
                for key, value in kwargs['tags'].items():
                    scope.set_tag(key, value)

            if 'user_id' in kwargs:
                scope.user = {'id': str(kwargs['user_id'])}

            sentry_sdk.capture_exception(error)
    except Exception as e:
        logger.error(f"Sentry capture_error 失败: {e}")


def capture_message_sync(message: str, level: str = "info", **kwargs):
    """
    同步捕获消息到 Sentry

    Args:
        message: 消息内容
        level: 级别 (debug/info/warning/error)
        **kwargs: 额外参数
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            if 'extra' in kwargs:
                for key, value in kwargs['extra'].items():
                    scope.set_extra(key, value)

            if 'tags' in kwargs:
                for key, value in kwargs['tags'].items():
                    scope.set_tag(key, value)

            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.error(f"Sentry capture_message 失败: {e}")


async def capture_message_async(message: str, level: str = "info", **kwargs):
    """
    异步捕获消息到 Sentry

    Args:
        message: 消息内容
        level: 级别 (debug/info/warning/error)
        **kwargs: 额外参数
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        await asyncio.sleep(0)

        with sentry_sdk.configure_scope() as scope:
            if 'extra' in kwargs:
                for key, value in kwargs['extra'].items():
                    scope.set_extra(key, value)

            if 'tags' in kwargs:
                for key, value in kwargs['tags'].items():
                    scope.set_tag(key, value)

            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.error(f"Sentry capture_message_async 失败: {e}")


def set_user(user_id: str, email: Optional[str] = None, username: Optional[str] = None):
    """
    设置当前用户上下文

    Args:
        user_id: 用户 ID
        email: 用户邮箱
        username: 用户名
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        sentry_sdk.set_user({
            'id': str(user_id),
            'email': email,
            'username': username
        })
    except Exception as e:
        logger.error(f"Sentry set_user 失败: {e}")


def set_tag(key: str, value: str):
    """
    设置标签

    Args:
        key: 标签名
        value: 标签值
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        sentry_sdk.set_tag(key, value)
    except Exception as e:
        logger.error(f"Sentry set_tag 失败: {e}")


def add_breadcrumb(message: str, category: str = "default", level: str = "info", **kwargs):
    """
    添加面包屑导航

    Args:
        message: 消息
        category: 分类
        level: 级别
        **kwargs: 额外参数
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Sentry add_breadcrumb 失败: {e}")


def get_sentry_client():
    """获取 Sentry 客户端实例"""
    return _sentry_client


def is_sentry_initialized() -> bool:
    """检查 Sentry 是否已初始化"""
    return _sentry_initialized
