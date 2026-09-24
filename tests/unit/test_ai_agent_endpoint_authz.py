"""回归：ai_agent_api AA2/AA3/AA10（快照端点归属、ModifyRequest 校验、generate 身份校验）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.ai_agent import generate_endpoints
from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.schemas import ModifyRequest


class TestSnapshotEndpointAuthorization:
    """AA2: 快照三端点补归属校验与路径穿越防护"""

    @pytest.mark.asyncio
    async def test_list_snapshots_rejects_other_user(self, monkeypatch):
        async def deny(db, session_id, user_id):
            raise HTTPException(status_code=404, detail="会话不存在或无访问权限")

        monkeypatch.setattr(endpoints, "verify_session_ownership", deny)
        with pytest.raises(HTTPException) as error:
            await endpoints.list_snapshots(
                "project_123456", token={"sub": "42"}, db=SimpleNamespace()
            )
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_rollback_rejects_other_user(self, monkeypatch):
        async def deny(db, session_id, user_id):
            raise HTTPException(status_code=404, detail="会话不存在或无访问权限")

        monkeypatch.setattr(endpoints, "verify_session_ownership", deny)
        with pytest.raises(HTTPException) as error:
            await endpoints.rollback_to_snapshot(
                "project_123456", "tag-1", token={"sub": "42"}, db=SimpleNamespace()
            )
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_rejects_other_user(self, monkeypatch):
        async def deny(db, session_id, user_id):
            raise HTTPException(status_code=404, detail="会话不存在或无访问权限")

        monkeypatch.setattr(endpoints, "verify_session_ownership", deny)
        with pytest.raises(HTTPException) as error:
            await endpoints.diff_snapshots(
                "project_123456", "a", "b", token={"sub": "42"}, db=SimpleNamespace()
            )
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_session", ["..", "../etc", "a/b", ""])
    async def test_snapshot_rejects_path_traversal(self, monkeypatch, bad_session):
        async def allow(db, session_id, user_id):
            return None

        monkeypatch.setattr(endpoints, "verify_session_ownership", allow)
        with pytest.raises(HTTPException) as error:
            await endpoints.list_snapshots(
                bad_session, token={"sub": "42"}, db=SimpleNamespace()
            )
        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_snapshot_rejects_anonymous(self, monkeypatch):
        async def allow(db, session_id, user_id):
            return None

        monkeypatch.setattr(endpoints, "verify_session_ownership", allow)
        with pytest.raises(HTTPException) as error:
            await endpoints.list_snapshots(
                "project_123456", token={"sub": "anonymous"}, db=SimpleNamespace()
            )
        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_snapshots_allows_owner(self, monkeypatch, tmp_path):
        seen = {}

        async def allow(db, session_id, user_id):
            seen["session_id"] = session_id
            seen["user_id"] = user_id

        monkeypatch.setattr(endpoints, "verify_session_ownership", allow)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "orchestrator" / "project_123456").mkdir(parents=True)

        from app.agent.git_operations import GitOperations

        monkeypatch.setattr(
            GitOperations, "list_snapshots", AsyncMock(return_value=[])
        )
        result = await endpoints.list_snapshots(
            "project_123456", token={"sub": "42"}, db=SimpleNamespace()
        )
        assert seen == {"session_id": "project_123456", "user_id": "42"}
        assert result["snapshots"] == []


class TestModifyRequestValidation:
    """AA3: ModifyRequest.session_id 增加格式校验"""

    def test_rejects_path_traversal_session_id(self):
        with pytest.raises(ValidationError):
            ModifyRequest(session_id="../../evil")

    def test_rejects_dotted_session_id(self):
        with pytest.raises(ValidationError):
            ModifyRequest(session_id="a.b")

    def test_accepts_valid_session_id(self):
        request = ModifyRequest(session_id="project_123456")
        assert request.session_id == "project_123456"

    def test_accepts_none_session_id(self):
        assert ModifyRequest(session_id=None).session_id is None


class TestGenerateIdentity:
    """AA10: generate 端点拒绝非数字 user_id"""

    @pytest.mark.asyncio
    async def test_generate_rejects_non_numeric_user(self):
        request = SimpleNamespace()
        with pytest.raises(HTTPException) as error:
            await generate_endpoints.generate_project(
                SimpleNamespace(), token={"sub": "../evil"}, request=request
            )
        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_rejects_anonymous(self):
        with pytest.raises(HTTPException) as error:
            await generate_endpoints.generate_project(
                SimpleNamespace(), token={"sub": "anonymous"}, request=SimpleNamespace()
            )
        assert error.value.status_code == 403
