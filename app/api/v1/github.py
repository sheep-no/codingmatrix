"""
GitHub Integration API - GitHub 集成接口

提供 GitHub 项目保存和同步功能：
- GitHub 账号配置
- 仓库创建和推送
- 项目同步到 GitHub
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.security import verify_token
from app.db.database import get_db
from app.models.user import User
from app.models.github_config import GithubUserConfig
from app.services.github_config_service import config_summary, load_readable_token, resolve_save_credentials, save_config
from app.services.github_remote import (
    create_user_repo,
    fetch_branches,
    fetch_commits,
    fetch_repos,
    fetch_user,
    github_https_remote,
    validate_project_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

class GithubConfig(BaseModel):
    """GitHub 配置模型"""
    username: str = Field(..., description="GitHub 用户名")
    token: str = Field(..., description="GitHub Personal Access Token", repr=False)
    use_github: bool = Field(default=False, description="是否使用 GitHub")

class GithubSaveConfig(BaseModel):
    username: str = ""
    token: str = Field(default="", repr=False)
    use_github: Optional[bool] = None

class GithubSaveRequest(BaseModel):
    """GitHub 保存请求模型"""
    project_name: str = Field(..., description="项目名称")
    project_description: str = Field(default="", description="项目描述")
    project_data: str = Field(..., description="项目数据（JSON 字符串）")
    github_config: Optional[GithubSaveConfig] = Field(default=None, description="可选；缺省凭据时使用已保存配置")

class GithubSaveResponse(BaseModel):
    """GitHub 保存响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="操作消息")
    repo_url: Optional[str] = Field(None, description="仓库 URL")
    commit_id: Optional[str] = Field(None, description="提交 ID")

@router.post("/config", response_model=Dict[str, Any])
async def set_github_config(
    config: GithubConfig,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    设置用户的 GitHub 配置
    
    配置将存储在用户会话中，用于后续的项目保存操作。
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    try:
        return await save_config(db, int(user_id), config.username, config.token, config.use_github)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="GitHub 配置保存失败，请重新读取配置确认状态") from None

@router.post("/save", response_model=GithubSaveResponse)
async def save_project_to_github(
    request: GithubSaveRequest,
    background_tasks: BackgroundTasks,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    将项目保存到 GitHub 仓库
    
    如果用户启用了 GitHub 集成，项目将被推送到用户的 GitHub 仓库。
    否则，将使用本地 Git 保存。
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    try:
        validate_project_name(request.project_name)
        config = request.github_config
        username, github_token, use_github = await resolve_save_credentials(
            db,
            int(user_id),
            username=config.username if config else "",
            token=config.token if config else "",
            use_github=None if config is None else config.use_github,
        )
        if use_github:
            return await _save_to_github(request, str(user_id), username, github_token)
        return await _save_to_local_git(request, str(user_id))
    except HTTPException:
        raise
    except Exception:
        logger.exception("保存项目失败")
        raise HTTPException(status_code=500, detail="保存项目失败") from None

GIT_TIMEOUT = 60


def _run_git(args: list[str], cwd: Path, extra_config: list[tuple[str, str]] | None = None):
    command = ["git"]
    for key, value in extra_config or []:
        command.extend(["-c", f"{key}={value}"])
    command.extend(args)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git 操作超时") from None
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Git 操作失败") from None


def _write_project_files(project_path: Path, project_data: str) -> None:
    import json
    try:
        project_files = json.loads(project_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="项目数据不是合法 JSON") from None
    if not isinstance(project_files, dict):
        raise HTTPException(status_code=400, detail="项目数据必须是路径到内容的对象")
    if not project_files:
        raise HTTPException(status_code=400, detail="项目数据不能为空")
    root = project_path.resolve()
    for file_path, content in project_files.items():
        full_path = (root / str(file_path)).resolve()
        if full_path == root or not full_path.is_relative_to(root):
            raise HTTPException(status_code=400, detail="非法路径")
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(str(content))


async def _save_to_github(
    request: GithubSaveRequest, user_id: str, username: str, github_token: str
) -> GithubSaveResponse:
    project_name = validate_project_name(request.project_name)
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir) / project_name
        project_path.mkdir()
        _write_project_files(project_path, request.project_data)
        _run_git(["init"], project_path)
        _run_git(["symbolic-ref", "HEAD", "refs/heads/main"], project_path)
        _run_git(["add", "."], project_path)
        _run_git(["config", "user.name", username], project_path)
        _run_git(["config", "user.email", f"{username}@users.noreply.github.com"], project_path)
        _run_git(["commit", "-m", f"Initial commit for {project_name}"], project_path)
        repo_info = await create_user_repo(github_token, project_name, request.project_description)
        repo_name = str(repo_info.get("name") or project_name)
        owner = username
        if isinstance(repo_info.get("owner"), dict) and repo_info["owner"].get("login"):
            owner = str(repo_info["owner"]["login"])
        remote_url = github_https_remote(owner, repo_name)
        _run_git(["remote", "add", "origin", remote_url], project_path)
        _run_git(
            ["push", "-u", "origin", "main"],
            project_path,
            extra_config=[("http.extraHeader", f"AUTHORIZATION: token {github_token}")],
        )
        commit_id = _run_git(["rev-parse", "HEAD"], project_path).stdout.strip()
        return GithubSaveResponse(
            success=True,
            message="项目已成功保存到 GitHub",
            repo_url=repo_info.get("html_url") or repo_info.get("clone_url"),
            commit_id=commit_id,
        )

async def _save_to_local_git(request: GithubSaveRequest, user_id: str) -> GithubSaveResponse:
    import datetime

    project_name = validate_project_name(request.project_name)
    projects_dir = Path("projects") / str(user_id)
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_path = projects_dir / project_name
    if project_path.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_path.rename(projects_dir / f"{project_name}_backup_{timestamp}")
    project_path.mkdir()
    _write_project_files(project_path, request.project_data)
    _run_git(["init"], project_path)
    _run_git(["symbolic-ref", "HEAD", "refs/heads/main"], project_path)
    _run_git(["add", "."], project_path)
    _run_git(["config", "user.name", "CodingMatrix AI"], project_path)
    _run_git(["config", "user.email", "ai@codingmatrix.com"], project_path)
    _run_git(["commit", "-m", f"Initial commit for {project_name}"], project_path)
    commit_id = _run_git(["rev-parse", "HEAD"], project_path).stdout.strip()
    return GithubSaveResponse(
        success=True,
        message="项目已成功保存到本地 Git",
        repo_url=str(project_path.absolute()),
        commit_id=commit_id,
    )

@router.get("/config", response_model=Dict[str, Any])
async def get_github_config(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的 GitHub 配置
    
    返回当前用户的 GitHub 配置信息。
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    try:
        return config_summary(await db.get(GithubUserConfig, int(user_id)))
    except Exception:
        raise HTTPException(status_code=503, detail="GitHub 配置读取失败") from None


def _require_user_id(token: dict) -> int:
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    return int(user_id)


@router.post("/verify")
async def verify_github_credentials(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    record, github_token = await load_readable_token(db, _require_user_id(token))
    user = await fetch_user(github_token)
    login = str(user["login"])
    matched = login.lower() == (record.username or "").lower()
    return {
        "success": matched,
        "verified": matched,
        "login": login,
        "username": record.username,
        "message": "GitHub 凭据有效" if matched else "用户名与 Token 不匹配",
    }


@router.get("/repos")
async def list_github_repos(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    _, github_token = await load_readable_token(db, _require_user_id(token))
    return {"repos": await fetch_repos(github_token)}


@router.get("/repos/{owner}/{repo}/branches")
async def list_github_branches(
    owner: str,
    repo: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    _, github_token = await load_readable_token(db, _require_user_id(token))
    return {"owner": owner, "repo": repo, "branches": await fetch_branches(github_token, owner, repo)}


@router.get("/repos/{owner}/{repo}/commits")
async def list_github_commits(
    owner: str,
    repo: str,
    sha: Optional[str] = None,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    _, github_token = await load_readable_token(db, _require_user_id(token))
    return {
        "owner": owner,
        "repo": repo,
        "sha": sha,
        "commits": await fetch_commits(github_token, owner, repo, sha),
    }
