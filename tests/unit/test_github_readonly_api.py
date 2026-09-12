from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import github as github_api
from app.services import github_config_service, github_remote


@pytest.mark.asyncio
async def test_fetch_repos_maps_owner_and_visibility(monkeypatch):
    monkeypatch.setattr(
        github_remote,
        "github_get",
        AsyncMock(
            return_value=[
                {
                    "full_name": "alice/demo",
                    "name": "demo",
                    "owner": {"login": "alice"},
                    "private": True,
                    "default_branch": "main",
                    "html_url": "https://github.com/alice/demo",
                    "description": "demo repo",
                    "updated_at": "2026-09-12T00:00:00Z",
                }
            ]
        ),
    )
    repos = await github_remote.fetch_repos("stored-token")
    assert repos == [
        {
            "full_name": "alice/demo",
            "name": "demo",
            "owner": "alice",
            "private": True,
            "default_branch": "main",
            "html_url": "https://github.com/alice/demo",
            "description": "demo repo",
            "updated_at": "2026-09-12T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_fetch_branches_rejects_invalid_repo():
    with pytest.raises(HTTPException) as exc:
        await github_remote.fetch_branches("stored-token", "alice", "../etc")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_fetch_commits_maps_first_line(monkeypatch):
    monkeypatch.setattr(
        github_remote,
        "github_get",
        AsyncMock(
            return_value=[
                {
                    "sha": "abc123",
                    "html_url": "https://github.com/alice/demo/commit/abc123",
                    "commit": {
                        "message": "fix login\nmore detail",
                        "author": {"name": "Alice", "date": "2026-09-12T01:00:00Z"},
                    },
                }
            ]
        ),
    )
    commits = await github_remote.fetch_commits("stored-token", "alice", "demo", "main")
    assert commits[0]["message"] == "fix login"
    assert commits[0]["sha"] == "abc123"
    assert "token" not in commits[0]


@pytest.mark.asyncio
async def test_github_get_maps_unauthorized(monkeypatch):
    class Response:
        status_code = 401

        def json(self):
            return {"message": "bad credentials"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(github_remote.httpx, "AsyncClient", lambda timeout: Client())
    with pytest.raises(HTTPException) as exc:
        await github_remote.github_get("secret-token", "/user")
    assert exc.value.status_code == 401
    assert "secret-token" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_load_readable_token_requires_stored_config():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await github_config_service.load_readable_token(db, 7)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_verify_endpoint_compares_login(monkeypatch):
    record = SimpleNamespace(username="Alice", encrypted_token="envelope")
    db = AsyncMock()
    monkeypatch.setattr(
        github_api,
        "load_readable_token",
        AsyncMock(return_value=(record, "stored-token")),
    )
    monkeypatch.setattr(github_api, "fetch_user", AsyncMock(return_value={"login": "alice"}))
    result = await github_api.verify_github_credentials(token={"sub": "7"}, db=db)
    assert result["verified"] is True
    assert result["login"] == "alice"
    assert "token" not in result


@pytest.mark.asyncio
async def test_verify_endpoint_username_mismatch(monkeypatch):
    record = SimpleNamespace(username="bob", encrypted_token="envelope")
    db = AsyncMock()
    monkeypatch.setattr(
        github_api,
        "load_readable_token",
        AsyncMock(return_value=(record, "stored-token")),
    )
    monkeypatch.setattr(github_api, "fetch_user", AsyncMock(return_value={"login": "alice"}))
    result = await github_api.verify_github_credentials(token={"sub": "7"}, db=db)
    assert result["success"] is False
    assert result["verified"] is False


@pytest.mark.asyncio
async def test_list_repos_endpoint_uses_stored_token(monkeypatch):
    record = SimpleNamespace(username="alice", encrypted_token="envelope")
    db = AsyncMock()
    load = AsyncMock(return_value=(record, "stored-token"))
    monkeypatch.setattr(github_api, "load_readable_token", load)
    monkeypatch.setattr(
        github_api,
        "fetch_repos",
        AsyncMock(return_value=[{"full_name": "alice/demo", "name": "demo", "owner": "alice"}]),
    )
    result = await github_api.list_github_repos(token={"sub": "7"}, db=db)
    assert result["repos"][0]["full_name"] == "alice/demo"
    load.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_branches_and_commits_endpoints(monkeypatch):
    record = SimpleNamespace(username="alice", encrypted_token="envelope")
    db = AsyncMock()
    monkeypatch.setattr(
        github_api,
        "load_readable_token",
        AsyncMock(return_value=(record, "stored-token")),
    )
    monkeypatch.setattr(
        github_api,
        "fetch_branches",
        AsyncMock(return_value=[{"name": "main", "sha": "abc", "protected": False}]),
    )
    monkeypatch.setattr(
        github_api,
        "fetch_commits",
        AsyncMock(return_value=[{"sha": "abc", "message": "init", "author": "Alice"}]),
    )
    branches = await github_api.list_github_branches("alice", "demo", token={"sub": "7"}, db=db)
    commits = await github_api.list_github_commits("alice", "demo", sha="main", token={"sub": "7"}, db=db)
    assert branches["branches"][0]["name"] == "main"
    assert commits["commits"][0]["message"] == "init"
    assert commits["sha"] == "main"
