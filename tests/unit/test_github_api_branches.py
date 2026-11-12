"""github API 全分支回归。"""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import github as gh


class TestConfigEndpoints:
    @pytest.mark.asyncio
    async def test_set_config_missing_user(self):
        with pytest.raises(HTTPException) as exc:
            await gh.set_github_config(gh.GithubConfig(username="a", token="t"), {}, db=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_set_config_success(self, monkeypatch):
        save = AsyncMock(return_value={"saved": True})
        monkeypatch.setattr(gh, "save_config", save)
        db = MagicMock()
        db.rollback = AsyncMock()
        result = await gh.set_github_config(
            gh.GithubConfig(username="a", token="t"), {"sub": "7"}, db
        )
        assert result == {"saved": True}

    @pytest.mark.asyncio
    async def test_set_config_http_exception_rolls_back(self, monkeypatch):
        monkeypatch.setattr(gh, "save_config", AsyncMock(side_effect=HTTPException(status_code=400)))
        db = MagicMock()
        db.rollback = AsyncMock()
        with pytest.raises(HTTPException):
            await gh.set_github_config(gh.GithubConfig(username="a", token="t"), {"sub": "7"}, db)
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_config_unexpected_error(self, monkeypatch):
        monkeypatch.setattr(gh, "save_config", AsyncMock(side_effect=RuntimeError("x")))
        db = MagicMock()
        db.rollback = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await gh.set_github_config(gh.GithubConfig(username="a", token="t"), {"sub": "7"}, db)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_config_missing_user(self):
        with pytest.raises(HTTPException) as exc:
            await gh.get_github_config({}, db=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_config_success(self, monkeypatch):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        monkeypatch.setattr(gh, "config_summary", lambda record: {"verified": False})
        assert await gh.get_github_config({"sub": "7"}, db) == {"verified": False}

    @pytest.mark.asyncio
    async def test_get_config_failure(self):
        db = MagicMock()
        db.get = AsyncMock(side_effect=RuntimeError("x"))
        with pytest.raises(HTTPException) as exc:
            await gh.get_github_config({"sub": "7"}, db)
        assert exc.value.status_code == 503

    def test_require_user_id_missing(self):
        with pytest.raises(HTTPException) as exc:
            gh._require_user_id({})
        assert exc.value.status_code == 401

    def test_require_user_id_ok(self):
        assert gh._require_user_id({"sub": "12"}) == 12


class TestSaveEndpoint:
    @pytest.mark.asyncio
    async def test_missing_user(self):
        request = gh.GithubSaveRequest(project_name="demo", project_data="{}")
        with pytest.raises(HTTPException) as exc:
            await gh.save_project_to_github(request, None, {}, db=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_uses_request_config(self, monkeypatch):
        credentials = AsyncMock(return_value=("u", "t", True))
        monkeypatch.setattr(gh, "resolve_save_credentials", credentials)
        save = AsyncMock(return_value=gh.GithubSaveResponse(success=True, message="ok"))
        monkeypatch.setattr(gh, "_save_to_github", save)
        request = gh.GithubSaveRequest(
            project_name="demo",
            project_data='{"a":"b"}',
            github_config=gh.GithubSaveConfig(username="u", token="t", use_github=True),
        )
        result = await gh.save_project_to_github(request, None, {"sub": "7"}, db=MagicMock())
        assert result.success is True
        assert credentials.await_args.kwargs == {
            "username": "u", "token": "t", "use_github": True
        }

    @pytest.mark.asyncio
    async def test_local_when_disabled(self, monkeypatch):
        monkeypatch.setattr(
            gh, "resolve_save_credentials", AsyncMock(return_value=("u", "t", False))
        )
        local = AsyncMock(return_value=gh.GithubSaveResponse(success=True, message="local"))
        monkeypatch.setattr(gh, "_save_to_local_git", local)
        request = gh.GithubSaveRequest(project_name="demo", project_data='{"a":"b"}')
        result = await gh.save_project_to_github(request, None, {"sub": "7"}, db=MagicMock())
        assert result.message == "local"

    @pytest.mark.asyncio
    async def test_invalid_project_name(self, monkeypatch):
        monkeypatch.setattr(
            gh, "resolve_save_credentials", AsyncMock(return_value=("u", "t", False))
        )
        request = gh.GithubSaveRequest(project_name="..", project_data="{}")
        with pytest.raises(HTTPException) as exc:
            await gh.save_project_to_github(request, None, {"sub": "7"}, db=MagicMock())
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_unexpected_error(self, monkeypatch):
        monkeypatch.setattr(
            gh, "resolve_save_credentials", AsyncMock(side_effect=RuntimeError("x"))
        )
        monkeypatch.setattr(gh.logger, "exception", lambda *a, **k: None)
        request = gh.GithubSaveRequest(project_name="demo", project_data='{"a":"b"}')
        with pytest.raises(HTTPException) as exc:
            await gh.save_project_to_github(request, None, {"sub": "7"}, db=MagicMock())
        assert exc.value.status_code == 500


class TestGitHelpers:
    def test_run_git_success(self, monkeypatch):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(stdout="ok")

        monkeypatch.setattr(gh.subprocess, "run", fake_run)
        result = gh._run_git(["status"], Path("."), extra_config=[("a", "b")])
        assert result.stdout == "ok"
        assert calls[0][0][:3] == ["git", "-c", "a=b"]
        assert calls[0][1]["check"] is True

    def test_run_git_timeout(self, monkeypatch):
        monkeypatch.setattr(gh.subprocess, "run", MagicMock(side_effect=subprocess.TimeoutExpired("git", 1)))
        with pytest.raises(HTTPException) as exc:
            gh._run_git(["x"], Path("."))
        assert exc.value.status_code == 504

    def test_run_git_called_process_error(self, monkeypatch):
        monkeypatch.setattr(
            gh.subprocess, "run",
            MagicMock(side_effect=subprocess.CalledProcessError(1, "git")),
        )
        with pytest.raises(HTTPException) as exc:
            gh._run_git(["x"], Path("."))
        assert exc.value.status_code == 500

    def test_write_invalid_json(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            gh._write_project_files(tmp_path, "not json")
        assert exc.value.status_code == 400

    def test_write_empty_after_parse(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            gh._write_project_files(tmp_path, "{}")
        assert exc.value.status_code == 400

    def test_write_non_dict(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            gh._write_project_files(tmp_path, "[]")
        assert exc.value.status_code == 400

    def test_write_root_path_rejected(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            gh._write_project_files(tmp_path, '{".": "x"}')
        assert exc.value.status_code == 400

    def test_write_success(self, tmp_path):
        gh._write_project_files(tmp_path, '{"a/b.txt": "hello", "c.txt": 5}')
        assert (tmp_path / "a" / "b.txt").read_text() == "hello"
        assert (tmp_path / "c.txt").read_text() == "5"


class TestSaveToGithub:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        run = MagicMock(return_value=SimpleNamespace(stdout="deadbeef\n"))
        monkeypatch.setattr(gh, "_run_git", run)
        repo = {"name": "demo", "owner": {"login": "alice"}, "html_url": "https://github.com/alice/demo"}
        monkeypatch.setattr(gh, "create_user_repo", AsyncMock(return_value=repo))
        monkeypatch.setattr(gh, "github_https_remote", lambda owner, name: f"https://x/{owner}/{name}.git")
        request = gh.GithubSaveRequest(project_name="demo", project_data='{"README.md":"# d"}')
        result = await gh._save_to_github(request, "7", "alice", "tok")
        assert result.success is True
        assert result.repo_url == "https://github.com/alice/demo"
        assert result.commit_id == "deadbeef"

    @pytest.mark.asyncio
    async def test_fallback_repo_name_and_clone_url(self, monkeypatch):
        monkeypatch.setattr(gh, "_run_git", MagicMock(return_value=SimpleNamespace(stdout="sha")))
        monkeypatch.setattr(
            gh, "create_user_repo", AsyncMock(return_value={"clone_url": "https://c.git"})
        )
        monkeypatch.setattr(gh, "github_https_remote", lambda owner, name: "remote")
        request = gh.GithubSaveRequest(project_name="demo", project_data='{"a":"b"}')
        result = await gh._save_to_github(request, "7", "alice", "tok")
        assert result.repo_url == "https://c.git"


class TestSaveToLocal:
    @pytest.mark.asyncio
    async def test_success_and_backup(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run = MagicMock(return_value=SimpleNamespace(stdout="sha"))
        monkeypatch.setattr(gh, "_run_git", run)
        request = gh.GithubSaveRequest(project_name="demo", project_data='{"a":"b"}')
        first = await gh._save_to_local_git(request, "7")
        assert first.success is True
        second = await gh._save_to_local_git(request, "7")
        assert second.success is True
        backups = list((tmp_path / "projects" / "7").glob("demo_backup_*"))
        assert len(backups) == 1


class TestReadonlyEndpoints:
    @pytest.mark.asyncio
    async def test_branches_endpoint(self, monkeypatch):
        record = SimpleNamespace(username="alice")
        db = MagicMock()
        monkeypatch.setattr(
            gh, "load_readable_token", AsyncMock(return_value=(record, "tok"))
        )
        monkeypatch.setattr(gh, "fetch_branches", AsyncMock(return_value=[{"name": "main"}]))
        result = await gh.list_github_branches("alice", "demo", {"sub": "7"}, db)
        assert result == {"owner": "alice", "repo": "demo", "branches": [{"name": "main"}]}

    @pytest.mark.asyncio
    async def test_commits_endpoint_without_sha(self, monkeypatch):
        record = SimpleNamespace(username="alice")
        db = MagicMock()
        monkeypatch.setattr(
            gh, "load_readable_token", AsyncMock(return_value=(record, "tok"))
        )
        fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(gh, "fetch_commits", fetch)
        result = await gh.list_github_commits("alice", "demo", token={"sub": "7"}, db=db)
        assert result["sha"] is None
        fetch.assert_awaited_once_with("tok", "alice", "demo", None)
