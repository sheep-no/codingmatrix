"""
出站 URL 安全校验（SSRF 防护）

服务端向用户提交的 base_url 发起请求前，先确认目标是公网 http(s) 地址，
避免被用来探测内网服务或云元数据端点。
"""
import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = ("http", "https")


def check_outbound_url(url: str) -> Optional[str]:
    """校验出站 URL 是否可以安全请求。

    Args:
        url: 待校验的完整 URL

    Returns:
        不可请求时返回中文错误描述，可请求时返回 None
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "URL 格式无效"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"仅支持 http/https 协议，当前协议为 {parsed.scheme or '空'}"

    hostname = parsed.hostname
    if not hostname:
        return "URL 缺少主机名"

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except (socket.gaierror, UnicodeError):
        # 无法解析的域名在真正连接时自会失败，不构成 SSRF
        return None

    for *_, sockaddr in addr_info:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if not ip.is_global:
            logger.warning("SSRF 阻止：非公网地址 %s (%s)", hostname, ip)
            return f"不允许访问内网或保留地址: {hostname} ({ip})"
    return None
