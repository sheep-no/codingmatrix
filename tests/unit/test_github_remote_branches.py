"""Branch coverage for app/services/github_remote.py."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

import app.services.github_remote as module
from app.services.github_remote import (
    create_user_repo,
    fetch_branches,
    fetch_commits,
    fetch_repos,
    fetch_user,
    github_get,
    github_headers,
    github_https_remote,
    github_post,
    validate_git_ref,
    validate_project_name,
    validate_repo_ref,
)


class _Response:
    def __init__(self, status_code, payload=None, raises=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("bad json")
        return self._payload


def _client(monkeypatch, *, get=None, post=None, error=None):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            if error:
                raise error
            return get

        async def post(self, *args, **kwargs):
            if error:
                raise error
            return post

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: Client())


class TestValidation:
    @pytest.mark.parametrize("owner,repo", [("alice", "demo"), ("a", "a"), ("a-b", "x.y_z")])
    def test_valid_repo_refs(self, owner, repo):
        validate_repo_ref(owner, repo)

    @pytest.mark.parametrize(
        "owner,repo", [("-bad", "demo"), ("alice", "bad repo"), ("alice", "x" * 101)]
    )
    def test_invalid_repo_refs(self, owner, repo):
        with pytest.raises(HTTPException) as exc:
            validate_repo_ref(owner, repo)
        assert exc.value.status_code == 422

    def test_valid_git_ref(self):
        validate_git_ref("feature/abc-1.2")

    @pytest.mark.parametrize("value", ["bad ref", "", "x" * 300])
    def test_invalid_git_ref(self, value):
        with pytest.raises(HTTPException):
            validate_git_ref(value)

    def test_project_name_is_trimmed(self):
        assert validate_project_name("  demo  ") == "demo"

    def test_project_name_rejects_non_string(self):
        with pytest.raises(HTTPException):
            validate_project_name(None)

    def test_https_remote_uses_validated_parts(self):
        assert github_https_remote("alice", "demo") == "https://github.com/alice/demo.git"

    def test_headers_shape(self):
        assert github_headers("tok") == {
            "Authorization": "token tok",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodingMatrix",
        }


class TestGithubGet:
    async def test_success_payload(self, monkeypatch):
        _client(monkeypatch, get=_Response(200, {"login": "alice"}))
        assert await github_get("tok", "/user") == {"login": "alice"}

    async def test_timeout_maps_to_504(self, monkeypatch):
        _client(monkeypatch, error=httpx.ReadTimeout("slow"))
        with pytest.raises(HTTPException) as exc:
            await github_get("tok", "/user")
        assert exc.value.status_code == 504

    async def test_network_error_maps_to_502(self, monkeypatch):
        _client(monkeypatch, error=httpx.ConnectError("down"))
        with pytest.raises(HTTPException) as exc:
            await github_get("tok", "/user")
        assert exc.value.status_code == 502

    @pytest.mark.parametrize(
        "status,expected",
        [(401, 422), (403, 403), (404, 404), (500, 502), (418, 502)],
    )
    async def test_status_mapping(self, monkeypatch, status, expected):
        _client(monkeypatch, get=_Response(status))
        with pytest.raises(HTTPException) as exc:
            await github_get("tok", "/user")
        assert exc.value.status_code == expected

    async def test_invalid_json_maps_to_502(self, monkeypatch):
        _client(monkeypatch, get=_Response(200, raises=True))
        with pytest.raises(HTTPException) as exc:
            await github_get("tok", "/user")
        assert exc.value.status_code == 502

    async def test_unexpected_status_logs_warning(self, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)
        _client(monkeypatch, get=_Response(500))

        with pytest.raises(HTTPException):
            await github_get("tok", "/user")

        assert fake_logger.warning.called


class TestGithubPost:
    async def test_success_201(self, monkeypatch):
        _client(monkeypatch, post=_Response(201, {"clone_url": "x"}))
        assert await github_post("tok", "/user/repos", {"name": "x"}) == {"clone_url": "x"}

    async def test_success_200(self, monkeypatch):
        _client(monkeypatch, post=_Response(200, {"ok": True}))
        assert await github_post("tok", "/user/repos", {}) == {"ok": True}

    async def test_timeout_maps_to_504(self, monkeypatch):
        _client(monkeypatch, error=httpx.ReadTimeout("slow"))
        with pytest.raises(HTTPException) as exc:
            await github_post("tok", "/user/repos", {})
        assert exc.value.status_code == 504

    async def test_network_error_maps_to_502(self, monkeypatch):
        _client(monkeypatch, error=httpx.ConnectError("down"))
        with pytest.raises(HTTPException) as exc:
            await github_post("tok", "/user/repos", {})
        assert exc.value.status_code == 502

    @pytest.mark.parametrize(
        "status,expected",
        [(401, 422), (403, 403), (422, 400), (500, 502)],
    )
    async def test_status_mapping(self, monkeypatch, status, expected):
        _client(monkeypatch, post=_Response(status))
        with pytest.raises(HTTPException) as exc:
            await github_post("tok", "/user/repos", {})
        assert exc.value.status_code == expected

    async def test_invalid_json_maps_to_502(self, monkeypatch):
        _client(monkeypatch, post=_Response(201, raises=True))
        with pytest.raises(HTTPException) as exc:
            await github_post("tok", "/user/repos", {})
        assert exc.value.status_code == 502

    async def test_unexpected_status_logs_warning(self, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)
        _client(monkeypatch, post=_Response(500))

        with pytest.raises(HTTPException):
            await github_post("tok", "/user/repos", {})

        assert fake_logger.warning.called


class TestCreateUserRepo:
    async def test_success(self, monkeypatch):
        post = AsyncMock(return_value={"clone_url": "https://x"})
        monkeypatch.setattr(module, "github_post", post)

        result = await create_user_repo("tok", "  demo  ", "desc")

        assert result == {"clone_url": "https://x"}
        post.assert_awaited_once_with(
            "tok", "/user/repos", {"name": "demo", "description": "desc", "private": False}
        )

    async def test_empty_description(self, monkeypatch):
        post = AsyncMock(return_value={"clone_url": "https://x"})
        monkeypatch.setattr(module, "github_post", post)

        await create_user_repo("tok", "demo")

        assert post.call_args.args[2]["description"] == ""

    async def test_conflict_retries_with_timestamp_suffix(self, monkeypatch):
        calls = []

        async def fake_post(_token, path, payload):
            calls.append(payload)
            if len(calls) == 1:
                raise HTTPException(status_code=400, detail="exists")
            return {"clone_url": "https://x"}

        monkeypatch.setattr(module, "github_post", fake_post)
        monkeypatch.setattr(module.time, "time", lambda: 1700000000)

        result = await create_user_repo("tok", "x" * 100)

        assert result["clone_url"] == "https://x"
        assert len(calls) == 2
        assert calls[1]["name"].endswith("-1700000000")
        assert len(calls[1]["name"]) <= 100

    async def test_non_400_http_error_propagates(self, monkeypatch):
        async def fake_post(*_args, **_kwargs):
            raise HTTPException(status_code=403, detail="nope")

        monkeypatch.setattr(module, "github_post", fake_post)

        with pytest.raises(HTTPException) as exc:
            await create_user_repo("tok", "demo")

        assert exc.value.status_code == 403

    @pytest.mark.parametrize("data", [{}, {"clone_url": ""}, [], None])
    async def test_invalid_repo_info(self, monkeypatch, data):
        monkeypatch.setattr(module, "github_post", AsyncMock(return_value=data))

        with pytest.raises(HTTPException) as exc:
            await create_user_repo("tok", "demo")

        assert exc.value.status_code == 502


class TestFetchUser:
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(module, "github_get", AsyncMock(return_value={"login": "a"}))
        assert await fetch_user("tok") == {"login": "a"}

    @pytest.mark.parametrize("data", [{}, {"login": ""}, [], None])
    async def test_invalid_payload(self, monkeypatch, data):
        monkeypatch.setattr(module, "github_get", AsyncMock(return_value=data))
        with pytest.raises(HTTPException) as exc:
            await fetch_user("tok")
        assert exc.value.status_code == 502


class TestFetchRepos:
    async def test_non_list_payload_rejected(self, monkeypatch):
        monkeypatch.setattr(module, "github_get", AsyncMock(return_value={"a": 1}))
        with pytest.raises(HTTPException) as exc:
            await fetch_repos("tok")
        assert exc.value.status_code == 502

    async def test_skips_non_dict_and_handles_missing_fields(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "github_get",
            AsyncMock(
                return_value=[
                    "not-a-dict",
                    {
                        "full_name": "a/b",
                        "name": "b",
                        "owner": "not-a-dict",
                        "private": 0,
                        "default_branch": "",
                        "html_url": "",
                        "description": None,
                        "updated_at": None,
                    },
                ]
            ),
        )

        repos = await fetch_repos("tok")

        assert repos == [
            {
                "full_name": "a/b",
                "name": "b",
                "owner": "",
                "private": False,
                "default_branch": "main",
                "html_url": "",
                "description": "",
                "updated_at": "",
            }
        ]


class TestFetchBranches:
    async def test_non_list_payload_rejected(self, monkeypatch):
        monkeypatch.setattr(module, "github_get", AsyncMock(return_value={}))
        with pytest.raises(HTTPException):
            await fetch_branches("tok", "alice", "demo")

    async def test_skips_non_dict_and_handles_missing_fields(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "github_get",
            AsyncMock(return_value=[None, {"name": "main", "commit": "bad", "protected": 1}]),
        )

        branches = await fetch_branches("tok", "alice", "demo")

        assert branches == [{"name": "main", "sha": "", "protected": True}]


class TestFetchCommits:
    async def test_non_list_payload_rejected(self, monkeypatch):
        monkeypatch.setattr(module, "github_get", AsyncMock(return_value={}))
        with pytest.raises(HTTPException):
            await fetch_commits("tok", "alice", "demo")

    async def test_skips_non_dict_and_handles_missing_fields(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "github_get",
            AsyncMock(
                return_value=[
                    "skip",
                    {
                        "sha": "abc",
                        "commit": {
                            "message": "line one\nline two",
                            "author": {"login": "alice", "date": "2026-01-01"},
                        },
                        "html_url": "u",
                    },
                    {
                        "sha": "def",
                        "commit": {"message": None, "author": "bad"},
                    },
                ]
            ),
        )

        commits = await fetch_commits("tok", "alice", "demo")

        assert commits[0] == {
            "sha": "abc",
            "message": "line one",
            "author": "alice",
            "date": "2026-01-01",
            "html_url": "u",
        }
        assert commits[1]["message"] == ""
        assert commits[1]["author"] == ""
        assert commits[1]["date"] == ""

    async def test_no_sha_omits_param(self, monkeypatch):
        get = AsyncMock(return_value=[])
        monkeypatch.setattr(module, "github_get", get)

        await fetch_commits("tok", "alice", "demo")

        assert get.await_args.kwargs["params"] == {"per_page": 20}

    async def test_long_message_truncated(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "github_get",
            AsyncMock(
                return_value=[{"sha": "a", "commit": {"message": "x" * 500}}]
            ),
        )

        commits = await fetch_commits("tok", "alice", "demo")

        assert len(commits[0]["message"]) == 240
