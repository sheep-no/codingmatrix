"""中间件层 P2 缺陷回归：端点限流前缀失配与输入校验误报。
"""
import json

import pytest

from app.middleware.input_validator import InputValidatorMiddleware
from app.middleware.rate_limiter import RateLimitTier, RateLimiter
from app.services.rate_limit_config import RateLimitConfig


def _scope(path: str, body: bytes, content_type: str = "application/json") -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
        ],
    }


def _receive(body: bytes):
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _run(path: str, body: bytes, content_type: str = "application/json"):
    """返回 (是否到达下游, 拦截响应消息列表)。"""
    reached = False
    messages = []
    scope = _scope(path, body, content_type)

    async def app(scope, receive, send):
        nonlocal reached
        reached = True

    async def send(message):
        messages.append(message)

    middleware = InputValidatorMiddleware(app)
    await middleware(scope, _receive(body), send)
    return reached, messages


class TestEndpointRulePrefixMatching:
    """RLM1：带路径参数的请求必须命中前缀规则，且桶按规则前缀聚合。"""

    def test_prefixed_parameterized_path_resolves_registered_rule(self):
        config = RateLimitConfig()
        assert config.get_endpoint_rule("/api/v1/aicloud/jobs/abc-123") == (10, 60)
        assert config.get_endpoint_rule("/api/v1/ai_agent/process/stream") == (10, 60)
        assert config.get_endpoint_rule("/api/v1/workflow/run/xyz") == (10, 60)

    def test_prefix_match_respects_path_segment_boundary(self):
        config = RateLimitConfig()
        # /api/v1/ai_agentx 不是 /api/v1/ai_agent 的子路径，应回落默认 (60, 60)
        assert config.get_endpoint_rule("/api/v1/ai_agentx/tasks") == (60, 60)
        assert config.resolve_endpoint_key("/api/v1/ai_agentx/tasks") is None

    def test_longest_registered_prefix_wins(self):
        config = RateLimitConfig()
        config.set_endpoint_rule("/api/v1/aicloud/jobs", 3, 60)
        assert config.get_endpoint_rule("/api/v1/aicloud/jobs/42") == (3, 60)
        assert config.get_endpoint_rule("/api/v1/aicloud/other") == (10, 60)

    def test_parameterized_paths_share_one_endpoint_bucket(self):
        limiter = RateLimiter()
        outcomes = [
            limiter.check_multi_tier("10.1.2.3", None, f"/api/v1/aicloud/jobs/{index}")
            for index in range(11)
        ]

        assert outcomes[9][0] is False, "第 10 次请求仍在端点配额内"
        limited, tier, limit, window = outcomes[10]
        assert limited is True
        assert tier == RateLimitTier.ENDPOINT
        assert (limit, window) == (10, 60)


class TestInputValidatorProse:
    """IV1：业务文本中的 SQL/代码词汇不再被当作攻击 payload。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text",
        (
            "Create and delete SQLite database records",
            "update the user profile after selecting a template",
            "explain eval() and document.cookie to me",
            "on error resume next is legacy VB syntax",
        ),
    )
    async def test_regular_endpoint_accepts_prose(self, text):
        body = json.dumps({"name": text}).encode()
        reached, messages = await _run("/api/v1/users", body)
        assert reached is True, f"正常文本被误拦: {text} -> {messages}"
        assert messages == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        (
            "' OR 1=1 --",
            "1' UNION SELECT password FROM users --",
            "'; DROP TABLE users; --",
            "admin' AND '1'='1",
        ),
    )
    async def test_regular_endpoint_still_rejects_injection(self, payload):
        body = json.dumps({"name": payload}).encode()
        reached, messages = await _run("/api/v1/users", body)
        assert reached is False, f"注入 payload 未被拦截: {payload}"
        assert messages[0]["status"] == 400
        assert "sql_injection" in json.loads(messages[1]["body"])["details"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_regular_endpoint_still_rejects_xss_payload(self):
        body = json.dumps({"comment": "<script>alert(1)</script>"}).encode()
        reached, messages = await _run("/api/v1/chat", body)
        assert reached is False
        assert messages[0]["status"] == 400
        assert "xss" in json.loads(messages[1]["body"])["details"]["detected_issues"]


class TestAiPathStillEnforcesTransportChecks:
    """IV1：AI 主链路只应跳过内容扫描，不应跳过 Content-Type 与大小校验。"""

    @pytest.mark.asyncio
    async def test_ai_path_rejects_unsupported_content_type(self):
        body = b"<xml>payload</xml>"
        reached, messages = await _run(
            "/api/v1/agent/orchestrate", body, content_type="application/xml"
        )
        assert reached is False
        assert messages[0]["status"] == 415

    @pytest.mark.asyncio
    async def test_ai_path_still_scans_free_of_sql_scan(self):
        # 白名单路径应放行含 SQL 词汇的需求文本
        body = json.dumps({"requirement": "Create and delete SQLite records"}).encode()
        reached, messages = await _run("/api/v1/agent/orchestrate", body)
        assert reached is True
        assert messages == []
