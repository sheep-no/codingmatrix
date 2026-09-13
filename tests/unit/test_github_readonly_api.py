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
    assert exc.value.status_code == 422
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


def test_github_https_remote_has_no_credentials():
    url = github_remote.github_https_remote("alice", "demo")
    assert url == "https://github.com/alice/demo.git"


def test_write_project_files_rejects_traversal(tmp_path):
    with pytest.raises(HTTPException) as exc:
        github_api._write_project_files(tmp_path, '{"../secret":"x"}')
    assert exc.value.status_code == 400


def test_write_project_files_rejects_prefix_sibling(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    with pytest.raises(HTTPException) as exc:
        github_api._write_project_files(root, '{"../demo-evil/x":"x"}')
    assert exc.value.status_code == 400
    assert not (tmp_path / "demo-evil" / "x").exists()


def test_write_project_files_rejects_empty_object(tmp_path):
    with pytest.raises(HTTPException) as exc:
        github_api._write_project_files(tmp_path, "{}")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_save_credentials_uses_stored_token(monkeypatch):
    record = SimpleNamespace(username="alice", use_github=True, encrypted_token="envelope")
    db = AsyncMock()
    db.get = AsyncMock(return_value=record)
    monkeypatch.setattr(
        github_config_service,
        "load_readable_token",
        AsyncMock(return_value=(record, "stored-token")),
    )
    username, token, enabled = await github_config_service.resolve_save_credentials(db, 7)
    assert username == "alice"
    assert token == "stored-token"
    assert enabled is True


@pytest.mark.asyncio
async def test_resolve_save_credentials_prefers_request_token():
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(username="alice", use_github=True))
    username, token, enabled = await github_config_service.resolve_save_credentials(
        db, 7, username="alice", token="request-token", use_github=True
    )
    assert username == "alice"
    assert token == "request-token"
    assert enabled is True


@pytest.mark.asyncio
async def test_save_endpoint_uses_stored_credentials(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        github_api,
        "resolve_save_credentials",
        AsyncMock(return_value=("alice", "stored-token", True)),
    )
    save = AsyncMock(
        return_value=github_api.GithubSaveResponse(
            success=True,
            message="ok",
            repo_url="https://github.com/alice/demo",
            commit_id="abc",
        )
    )
    monkeypatch.setattr(github_api, "_save_to_github", save)
    request = github_api.GithubSaveRequest(project_name="demo", project_data='{"README.md":"# demo"}')
    result = await github_api.save_project_to_github(
        request, background_tasks=None, token={"sub": "7"}, db=db
    )
    assert result.success is True
    assert save.await_args.args[2:] == ("alice", "stored-token")


@pytest.mark.asyncio
async def test_create_user_repo_retries_with_timestamp_suffix(monkeypatch):
    calls = []

    async def fake_post(_token, _path, payload):
        calls.append(payload["name"])
        if payload["name"] == "demo":
            raise HTTPException(status_code=400, detail="GitHub 仓库创建失败")
        return {"clone_url": f"https://github.com/alice/{payload['name']}.git", "name": payload["name"]}

    monkeypatch.setattr(github_remote, "github_post", fake_post)
    data = await github_remote.create_user_repo("stored-token", "demo")
    assert calls[0] == "demo"
    assert calls[1].startswith("demo-")
    assert data["name"].startswith("demo-")
