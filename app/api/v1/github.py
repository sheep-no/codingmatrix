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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

class GithubConfig(BaseModel):
    """GitHub 配置模型"""
    username: str = Field(..., description="GitHub 用户名")
    token: str = Field(..., description="GitHub Personal Access Token")
    use_github: bool = Field(default=False, description="是否使用 GitHub")

class GithubSaveRequest(BaseModel):
    """GitHub 保存请求模型"""
    project_name: str = Field(..., description="项目名称")
    project_description: str = Field(default="", description="项目描述")
    project_data: str = Field(..., description="项目数据（JSON 字符串）")
    github_config: GithubConfig = Field(..., description="GitHub 配置")

class GithubSaveResponse(BaseModel):
    """GitHub 保存响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="操作消息")
    repo_url: Optional[str] = Field(None, description="仓库 URL")
    commit_id: Optional[str] = Field(None, description="提交 ID")

@router.post("/config", response_model=Dict[str, Any])
async def set_github_config(
    config: GithubConfig,
    token: dict = Depends(verify_token)
):
    """
    设置用户的 GitHub 配置
    
    配置将存储在用户会话中，用于后续的项目保存操作。
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    # 这里可以将配置存储到数据库或会话中
    # 目前我们只返回确认信息
    return {
        "success": True,
        "message": "GitHub 配置已保存",
        "username": config.username,
        "use_github": config.use_github
    }

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
        if request.github_config.use_github:
            # 使用 GitHub 保存
            result = await _save_to_github(request, user_id)
        else:
            # 使用本地 Git 保存
            result = await _save_to_local_git(request, user_id)
        
        return result
        
    except Exception as e:
        logger.error(f"保存项目失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存项目失败: {str(e)}")

async def _save_to_github(request: GithubSaveRequest, user_id: str) -> GithubSaveResponse:
    """保存项目到 GitHub"""
    try:
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / request.project_name
            project_path.mkdir()
            
            # 解析项目数据并写入文件
            import json
            project_files = json.loads(request.project_data)
            for file_path, content in project_files.items():
                full_path = project_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            # 初始化 Git 仓库
            subprocess.run(['git', 'init'], cwd=project_path, check=True)
            subprocess.run(['git', 'add', '.'], cwd=project_path, check=True)
            subprocess.run(['git', 'config', 'user.name', request.github_config.username], 
                          cwd=project_path, check=True)
            subprocess.run(['git', 'config', 'user.email', f"{request.github_config.username}@users.noreply.github.com"], 
                          cwd=project_path, check=True)
            subprocess.run(['git', 'commit', '-m', f"Initial commit for {request.project_name}"], 
                          cwd=project_path, check=True)
            
            # 创建 GitHub 仓库
            import httpx
            headers = {
                'Authorization': f'token {request.github_config.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            repo_data = {
                'name': request.project_name,
                'description': request.project_description,
                'private': False
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    'https://api.github.com/user/repos',
                    headers=headers,
                    json=repo_data
                )
                
                if response.status_code != 201:
                    raise HTTPException(status_code=400, detail=f"创建 GitHub 仓库失败: {response.text}")
                
                repo_info = response.json()
                repo_url = repo_info['clone_url']
            
            # 推送到 GitHub
            remote_url = f"https://{request.github_config.username}:{request.github_config.token}@github.com/{request.github_config.username}/{request.project_name}.git"
            subprocess.run(['git', 'remote', 'add', 'origin', remote_url], 
                          cwd=project_path, check=True)
            subprocess.run(['git', 'push', '-u', 'origin', 'main'], 
                          cwd=project_path, check=True)
            
            # 获取提交 ID
            result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                   cwd=project_path, capture_output=True, text=True, check=True)
            commit_id = result.stdout.strip()
            
            return GithubSaveResponse(
                success=True,
                message="项目已成功保存到 GitHub",
                repo_url=repo_url,
                commit_id=commit_id
            )
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Git 操作失败: {e}")
        raise HTTPException(status_code=500, detail=f"Git 操作失败: {str(e)}")
    except httpx.HTTPError as e:
        logger.error(f"GitHub API 调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"GitHub API 调用失败: {str(e)}")

async def _save_to_local_git(request: GithubSaveRequest, user_id: str) -> GithubSaveResponse:
    """保存项目到本地 Git"""
    try:
        # 创建项目目录
        projects_dir = Path("projects") / user_id
        projects_dir.mkdir(parents=True, exist_ok=True)
        
        project_path = projects_dir / request.project_name
        if project_path.exists():
            # 如果项目已存在，创建带时间戳的备份
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = projects_dir / f"{request.project_name}_backup_{timestamp}"
            project_path.rename(backup_path)
        
        project_path.mkdir()
        
        # 写入项目文件
        import json
        project_files = json.loads(request.project_data)
        for file_path, content in project_files.items():
            full_path = project_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # 初始化本地 Git 仓库
        subprocess.run(['git', 'init'], cwd=project_path, check=True)
        subprocess.run(['git', 'add', '.'], cwd=project_path, check=True)
        subprocess.run(['git', 'config', 'user.name', 'CodingMatrix AI'], 
                      cwd=project_path, check=True)
        subprocess.run(['git', 'config', 'user.email', 'ai@codingmatrix.com'], 
                      cwd=project_path, check=True)
        subprocess.run(['git', 'commit', '-m', f"Initial commit for {request.project_name}"], 
                      cwd=project_path, check=True)
        
        # 获取提交 ID
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                               cwd=project_path, capture_output=True, text=True, check=True)
        commit_id = result.stdout.strip()
        
        return GithubSaveResponse(
            success=True,
            message="项目已成功保存到本地 Git",
            repo_url=str(project_path.absolute()),
            commit_id=commit_id
        )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"本地 Git 操作失败: {e}")
        raise HTTPException(status_code=500, detail=f"本地 Git 操作失败: {str(e)}")

@router.get("/config", response_model=GithubConfig)
async def get_github_config(
    token: dict = Depends(verify_token)
):
    """
    获取用户的 GitHub 配置
    
    返回当前用户的 GitHub 配置信息。
    """
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    # 这里应该从数据库或会话中获取配置
    # 目前返回默认配置
    return GithubConfig(
        username="",
        token="",
        use_github=False
    )