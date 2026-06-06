"""
OrchestratorRequest.project_path 字段测试

修复：前端 useAgentStreaming.js 发送 project_path 用于增量模式
但 OrchestratorRequest 之前没有这个字段，被 Pydantic 静默丢弃，
导致 incremental 模式永远找不到原项目。

本测试验证：
1. project_path 字段被 schema 接受
2. 路径安全校验（不允许 ../ 遍历、绝对路径）
3. 字段在请求体中可序列化
"""
import pytest
from pydantic import ValidationError

from app.api.v1.ai_agent.schemas import OrchestratorRequest


class TestProjectPathAcceptance:
    """project_path 字段接受性测试"""

    def test_minimal_request_without_project_path(self):
        """最小请求（无 project_path）应该成功"""
        req = OrchestratorRequest(requirement="创建一个 FastAPI 项目")
        assert req.project_path is None
        assert req.incremental is False
        assert req.requirement == "创建一个 FastAPI 项目"

    def test_request_with_project_path(self):
        """带 project_path 的请求应该成功"""
        req = OrchestratorRequest(
            requirement="修改登录页",
            project_path="orchestrator/20260101_120000_1",
            incremental=True,
        )
        assert req.project_path == "orchestrator/20260101_120000_1"
        assert req.incremental is True

    def test_project_path_relative(self):
        """相对路径应该被接受"""
        req = OrchestratorRequest(
            requirement="test",
            project_path="users/123/myproject"
        )
        assert req.project_path == "users/123/myproject"

    def test_project_path_too_long_rejected(self):
        """超过 500 字符的 project_path 应该被拒绝"""
        long_path = "a" * 501
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorRequest(requirement="test", project_path=long_path)
        assert "project_path" in str(exc_info.value).lower() or "string_too_long" in str(exc_info.value).lower()

    def test_project_path_max_length_allowed(self):
        """正好 500 字符的 project_path 应该被接受"""
        path_500 = "a" * 500
        req = OrchestratorRequest(requirement="test", project_path=path_500)
        assert len(req.project_path) == 500


class TestProjectPathSecurity:
    """project_path 路径安全校验测试"""

    def test_path_traversal_rejected(self):
        """../ 路径遍历必须被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorRequest(
                requirement="test",
                project_path="../../../etc/passwd"
            )
        error_msg = str(exc_info.value).lower()
        assert ".." in error_msg or "traversal" in error_msg or "父目录" in str(exc_info.value)

    def test_windows_path_traversal_rejected(self):
        """Windows 风格 ..\\ 路径遍历必须被拒绝"""
        with pytest.raises(ValidationError):
            OrchestratorRequest(
                requirement="test",
                project_path="..\\..\\windows\\system32"
            )

    def test_absolute_unix_path_rejected(self):
        """Unix 绝对路径必须被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorRequest(
                requirement="test",
                project_path="/etc/passwd"
            )
        assert "绝对路径" in str(exc_info.value) or "absolute" in str(exc_info.value).lower()

    def test_absolute_windows_path_rejected(self):
        """Windows 绝对路径必须被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorRequest(
                requirement="test",
                project_path="C:\\Windows\\System32"
            )
        assert "绝对路径" in str(exc_info.value) or "absolute" in str(exc_info.value).lower()

    def test_hidden_traversal_rejected(self):
        """路径中间包含 .. 组件必须被拒绝"""
        with pytest.raises(ValidationError):
            OrchestratorRequest(
                requirement="test",
                project_path="projects/../etc"
            )


class TestProjectPathSerialization:
    """project_path 序列化测试"""

    def test_project_path_in_model_dump(self):
        """model_dump 应该包含 project_path"""
        req = OrchestratorRequest(
            requirement="test",
            project_path="orchestrator/20260101_120000_1",
            incremental=True,
        )
        dump = req.model_dump()
        assert dump["project_path"] == "orchestrator/20260101_120000_1"
        assert dump["incremental"] is True
        assert dump["requirement"] == "test"

    def test_project_path_default_none(self):
        """未提供 project_path 时默认为 None"""
        req = OrchestratorRequest(requirement="test")
        dump = req.model_dump()
        assert "project_path" in dump
        assert dump["project_path"] is None

    def test_json_serialization_roundtrip(self):
        """JSON 序列化往返不应该丢失数据"""
        import json
        original = OrchestratorRequest(
            requirement="修改代码",
            project_path="orchestrator/abc123",
            incremental=True,
        )
        json_str = original.model_dump_json()
        restored = OrchestratorRequest.model_validate_json(json_str)
        assert restored.project_path == "orchestrator/abc123"
        assert restored.incremental is True
        assert restored.requirement == "修改代码"


class TestOrchestratorRequestIntegration:
    """OrchestratorRequest 集成测试（与原字段配合）"""

    def test_all_fields_together(self):
        """所有字段一起使用"""
        req = OrchestratorRequest(
            requirement="创建一个电商网站",
            project_name="my-shop",
            project_path="users/1/my-shop",
            enable_review=True,
            enable_validation=True,
            enable_error_recovery=True,
            enable_memory=True,
            spec_first=True,
            dependency_graph=True,
            session_id="user_1_my-shop",
            incremental=True,
            require_approval=False,
            evaluation_only=False,
            api_key_token="token-abc",
            provider_id="provider-1",
        )
        assert req.requirement == "创建一个电商网站"
        assert req.project_name == "my-shop"
        assert req.project_path == "users/1/my-shop"
        assert req.session_id == "user_1_my-shop"
        assert req.incremental is True
        assert req.provider_id == "provider-1"

    def test_backward_compatible(self):
        """不传 project_path 时行为不变（向后兼容）"""
        req = OrchestratorRequest(
            requirement="test",
            project_name="proj",
            incremental=True,
        )
        assert req.project_path is None
        # 旧客户端调 incremental=True + 不传 project_path 的场景
        # 应该让后端走原本的 output_dir 逻辑（fallback 到时间戳）
