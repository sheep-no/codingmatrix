"""
HTTP Request Node - HTTP 请求节点

发送 HTTP 请求调用外部 API
"""

import logging
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from app.schema.workflow import TaskType
from app.utils.url_safety import check_outbound_url
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5
_REDIRECT_STATUS = (301, 302, 303, 307, 308)
# 响应头中不进入上下文的敏感字段
_SENSITIVE_HEADERS = {
    "set-cookie", "authorization", "proxy-authorization", "www-authenticate",
}


class HTTPRequestNode(TaskNodeBase):
    """
    HTTP 请求节点

    发送 HTTP 请求调用外部 API

    参数:
        url: 请求 URL（必填）
        method: 请求方法（可选，默认 GET）
        headers: 请求头（可选）
        body: 请求体（可选，POST/PUT/PATCH 时使用）
        params: URL 参数（可选）
        timeout: 超时时间（秒，可选，默认 30）
        output_variable: 结果存入上下文的变量名（可选，默认 "http_response"）
    """

    task_type = TaskType.HTTP_REQUEST

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return ["url"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "method": "GET",
            "headers": {},
            "body": None,
            "params": None,
            "timeout": 30,
            "output_variable": "http_response",
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "url" not in self.params:
            errors.append("Missing required parameter: url")
        elif not isinstance(self.params["url"], str):
            errors.append("Parameter 'url' must be a string")
        elif not self.params["url"].startswith(("http://", "https://")):
            errors.append("Parameter 'url' must start with http:// or https://")
        else:
            ssrf_error = self._check_ssrf(self.params["url"])
            if ssrf_error:
                errors.append(ssrf_error)

        if "method" in self.params:
            method = self.params["method"].upper()
            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
                errors.append(f"Unsupported HTTP method: {method}")

        if "timeout" in self.params:
            timeout = self.params["timeout"]
            if not isinstance(timeout, (int, float)):
                errors.append("Parameter 'timeout' must be a number")
            elif timeout < 1 or timeout > 120:
                errors.append("Parameter 'timeout' must be between 1 and 120")

        return errors

    def _check_ssrf(self, url: str, strict: bool = False) -> Optional[str]:
        """检查 URL 是否存在 SSRF 风险。

        strict=True 时 DNS 解析失败即拒绝，用于执行期已替换为实际值的 URL。
        """
        error = check_outbound_url(url, fail_closed_on_dns_error=strict)
        if error:
            logger.warning(f"[{self.node_id}] URL 安全校验未通过 | {url} | {error}")
        return error

    async def _request_with_redirects(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ):
        """手动跟随重定向，逐跳校验目标地址，避免跳转绕过 SSRF 检查。"""
        for _ in range(_MAX_REDIRECTS + 1):
            response = await client.request(
                method=method, url=url, follow_redirects=False, **kwargs
            )
            if response.status_code not in _REDIRECT_STATUS:
                return response, None

            location = response.headers.get("location")
            if not location:
                return response, None

            target = urljoin(url, location)
            error = self._check_ssrf(target, strict=True)
            if error:
                return None, f"重定向目标被拒绝: {error}"

            if response.status_code == 303 or (
                response.status_code in (301, 302) and method not in ("GET", "HEAD")
            ):
                method = "GET"
                kwargs.pop("content", None)
                kwargs.pop("json", None)
            url = target

        return None, "重定向次数超过上限"

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        发送 HTTP 请求

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 执行结果
        """
        url = self.params["url"]
        method = self.params.get("method", "GET").upper()
        headers = self.params.get("headers", {})
        body = self.params.get("body")
        params = self.params.get("params")
        timeout = self.params.get("timeout", 30)
        output_variable = self.params.get("output_variable", "http_response")

        # 从上下文替换变量
        url = self._replace_variables(url, context)
        if body and isinstance(body, str):
            body = self._replace_variables(body, context)
        if params and isinstance(params, dict):
            params = {k: self._replace_variables(str(v), context) for k, v in params.items()}

        # 变量替换后目标可能已经指向内网，必须重新校验
        ssrf_error = self._check_ssrf(url, strict=True)
        if ssrf_error:
            return NodeResult.error_result(error=f"URL 安全校验未通过: {ssrf_error}")

        logger.info(f"[{self.node_id}] HTTP 请求 | {method} {url}")

        try:
            async with httpx.AsyncClient() as client:
                response, redirect_error = await self._request_with_redirects(
                    client,
                    method,
                    url,
                    headers=headers,
                    json=body if body and isinstance(body, (dict, list)) else None,
                    content=body if body and isinstance(body, str) else None,
                    params=params,
                    timeout=timeout,
                )
                if redirect_error:
                    return NodeResult.error_result(error=redirect_error)

                # 解析响应
                try:
                    response_data = response.json()
                except (json.JSONDecodeError, ValueError):
                    response_data = response.text

                result_data = {
                    "status_code": response.status_code,
                    "data": response_data,
                    "headers": {
                        key: value
                        for key, value in response.headers.items()
                        if key.lower() not in _SENSITIVE_HEADERS
                    },
                    "output_variable": output_variable,
                }

                is_success = 200 <= response.status_code < 300
                logger.info(
                    f"[{self.node_id}] HTTP 响应 | status={response.status_code} | "
                    f"success={is_success}"
                )

                if is_success:
                    return NodeResult.success_result(
                        data=result_data,
                        metadata={"status_code": response.status_code}
                    )
                else:
                    return NodeResult.error_result(
                        error=f"HTTP {response.status_code}: {str(response_data)[:200]}",
                        metadata={"status_code": response.status_code, "data": result_data}
                    )

        except httpx.TimeoutException:
            error_msg = f"HTTP request timeout after {timeout}s"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)

        except Exception as e:
            error_msg = f"HTTP request failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)

    def _replace_variables(self, text: str, context: Dict[str, Any]) -> str:
        """替换文本中的上下文变量"""
        if not isinstance(text, str):
            return text

        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in text:
                if isinstance(value, (dict, list)):
                    text = text.replace(placeholder, json.dumps(value, ensure_ascii=False))
                else:
                    text = text.replace(placeholder, str(value))

        return text
