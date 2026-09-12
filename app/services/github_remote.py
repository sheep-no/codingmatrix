"""Read-only GitHub REST helpers. Callers pass a decrypted token; nothing is logged."""
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/\-]{1,256}$")


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CodingMatrix",
    }


def validate_repo_ref(owner: str, repo: str) -> None:
    if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(repo):
        raise HTTPException(status_code=422, detail="仓库路径无效")


def validate_git_ref(value: str) -> None:
    if not _REF_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="分支或提交引用无效")


async def github_get(token: str, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API}{path}",
                headers=github_headers(token),
                params=params,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="GitHub 请求超时") from None
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="GitHub 网络错误") from None
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub 凭据无效")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="GitHub 拒绝访问或达到速率限制")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="GitHub 资源不存在")
    if response.status_code >= 400:
        logger.warning("GitHub GET %s failed with status %s", path, response.status_code)
        raise HTTPException(status_code=502, detail="GitHub 请求失败")
    try:
        return response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="GitHub 响应无法解析") from None


async def fetch_user(token: str) -> dict[str, Any]:
    data = await github_get(token, "/user")
    if not isinstance(data, dict) or not data.get("login"):
        raise HTTPException(status_code=502, detail="GitHub 用户信息无效")
    return data


async def fetch_repos(token: str) -> list[dict[str, Any]]:
    data = await github_get(
        token,
        "/user/repos",
        params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator"},
    )
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="GitHub 仓库列表无效")
    repos: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        repos.append(
            {
                "full_name": item.get("full_name") or "",
                "name": item.get("name") or "",
                "owner": owner.get("login") or "",
                "private": bool(item.get("private")),
                "default_branch": item.get("default_branch") or "main",
                "html_url": item.get("html_url") or "",
                "description": item.get("description") or "",
                "updated_at": item.get("updated_at") or "",
            }
        )
    return repos


async def fetch_branches(token: str, owner: str, repo: str) -> list[dict[str, Any]]:
    validate_repo_ref(owner, repo)
    data = await github_get(token, f"/repos/{owner}/{repo}/branches", params={"per_page": 100})
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="GitHub 分支列表无效")
    branches: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        branches.append(
            {
                "name": item.get("name") or "",
                "sha": commit.get("sha") or "",
                "protected": bool(item.get("protected")),
            }
        )
    return branches


async def fetch_commits(token: str, owner: str, repo: str, sha: str | None = None) -> list[dict[str, Any]]:
    validate_repo_ref(owner, repo)
    params: dict[str, Any] = {"per_page": 20}
    if sha:
        validate_git_ref(sha)
        params["sha"] = sha
    data = await github_get(token, f"/repos/{owner}/{repo}/commits", params=params)
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="GitHub 提交列表无效")
    commits: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        message = str(commit.get("message") or "")
        commits.append(
            {
                "sha": item.get("sha") or "",
                "message": message.split("\n", 1)[0][:240],
                "author": author.get("name") or author.get("login") or "",
                "date": author.get("date") or "",
                "html_url": item.get("html_url") or "",
            }
        )
    return commits
