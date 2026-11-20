"""告警通知转发

Alertmanager 先把告警回调到 ``POST /api/v1/health/alerts``，再由本模块转发到
IM 群机器人或 SMTP 邮件。两个渠道独立降级：未配置就跳过，投递失败只记录日志
和指标，不影响 Alertmanager 的回调结果。
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.prometheus_metrics import get_prometheus_metrics

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
WEBHOOK_TIMEOUT_SECONDS = 5.0
SMTP_TIMEOUT_SECONDS = 10.0
MAX_TEXT_LENGTH = 2000


def _severity_rank(value: Any) -> int:
    """未知严重级别按 warning 处理，避免静默丢弃告警。"""
    return SEVERITY_ORDER.get(str(value or "").lower(), 1)


def _filter_alerts(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    threshold = _severity_rank(settings.ALERT_NOTIFY_MIN_SEVERITY)
    return [
        alert
        for alert in alerts
        if _severity_rank((alert.get("labels") or {}).get("severity")) >= threshold
    ]


def _format_alert(alert: Dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    status = str(alert.get("status") or "firing").upper()
    headline = f"[{status}] {labels.get('alertname', 'unknown')}"
    details = [
        f"{key}={labels[key]}"
        for key in ("severity", "provider", "model")
        if labels.get(key)
    ]
    if details:
        headline = f"{headline} ({', '.join(details)})"
    summary = (
        annotations.get("summary") or annotations.get("description") or ""
    ).strip()
    return f"{headline}\n{summary}" if summary else headline


def _format_text(alerts: List[Dict[str, Any]]) -> str:
    text = "\n\n".join(_format_alert(alert) for alert in alerts)
    return text[:MAX_TEXT_LENGTH]


def _build_webhook_payload(
    webhook_type: str, text: str, alerts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if webhook_type == "slack":
        return {"text": text}
    if webhook_type == "feishu":
        return {"msg_type": "text", "content": {"text": text}}
    if webhook_type in ("dingtalk", "wecom"):
        return {"msgtype": "text", "text": {"content": text}}
    return {"source": "ai-agent", "text": text, "alerts": alerts}


def _webhook_configured() -> bool:
    return bool(settings.ALERT_WEBHOOK_URL and settings.ALERT_WEBHOOK_TYPE)


def _smtp_recipients() -> List[str]:
    return [item.strip() for item in settings.ALERT_SMTP_TO.split(",") if item.strip()]


def _smtp_configured() -> bool:
    return bool(settings.ALERT_SMTP_HOST and settings.ALERT_SMTP_FROM and _smtp_recipients())


async def _post_webhook(payload: Dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(settings.ALERT_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        return response


def _webhook_rejection(response: httpx.Response, webhook_type: str) -> Optional[str]:
    """识别 IM 平台「HTTP 200 但业务错误」的响应。

    飞书、钉钉、企业微信在令牌失效或限流时仍返回 200，只在响应体里给出非 0
    错误码；不检查会把这些失败当成投递成功。
    """
    if webhook_type not in ("feishu", "dingtalk", "wecom"):
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("errcode", "code", "StatusCode"):
        if key in data and data[key] not in (0, "0"):
            detail = data.get("errmsg") or data.get("msg") or ""
            return f"{key}={data[key]} {detail}".strip()
    return None


async def _notify_webhook(alerts: List[Dict[str, Any]]) -> str:
    metrics = get_prometheus_metrics()
    try:
        text = _format_text(alerts)
        payload = _build_webhook_payload(settings.ALERT_WEBHOOK_TYPE, text, alerts)
        response = await _post_webhook(payload)
        rejection = _webhook_rejection(response, settings.ALERT_WEBHOOK_TYPE)
        if rejection:
            raise ValueError(f"Webhook 返回业务错误: {rejection}")
    except (httpx.HTTPError, ValueError, OSError) as exc:
        logger.error("告警 Webhook 投递失败: %s", exc)
        metrics.record_alert_notification("webhook", "failed")
        return "failed"
    metrics.record_alert_notification("webhook", "sent")
    return "sent"


def _send_email_sync(subject: str, body: str) -> None:
    recipients = _smtp_recipients()
    if not recipients:
        raise ValueError("ALERT_SMTP_TO 未配置收件人")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.ALERT_SMTP_FROM
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    security = settings.ALERT_SMTP_SECURITY
    if security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS
        )
    else:
        client = smtplib.SMTP(
            settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS
        )

    with client:
        if security == "starttls":
            client.starttls()
        if settings.ALERT_SMTP_USER:
            client.login(settings.ALERT_SMTP_USER, settings.ALERT_SMTP_PASSWORD)
        client.send_message(message)


async def _notify_email(alerts: List[Dict[str, Any]]) -> str:
    metrics = get_prometheus_metrics()
    status = "sent"
    try:
        body = _format_text(alerts)
        subject = f"[AI Agent] {len(alerts)} 条告警"
        await asyncio.to_thread(_send_email_sync, subject, body)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        logger.error("告警邮件投递失败: %s", exc)
        status = "failed"
    metrics.record_alert_notification("email", status)
    return status


async def notify_alerts(alerts: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """转发告警，返回各渠道结果；未配置任何渠道时返回 ``None``。"""
    if not alerts:
        return None

    webhook_enabled = _webhook_configured()
    email_enabled = _smtp_configured()
    if not webhook_enabled and not email_enabled:
        return None

    selected = _filter_alerts(alerts)
    if not selected:
        logger.info("告警均低于通知阈值 %s，跳过转发", settings.ALERT_NOTIFY_MIN_SEVERITY)
        return None

    results: Dict[str, str] = {}
    if webhook_enabled:
        results["webhook"] = await _notify_webhook(selected)
    if email_enabled:
        results["email"] = await _notify_email(selected)
    logger.info("告警已转发 %s 条，渠道结果=%s", len(selected), results)
    return results
