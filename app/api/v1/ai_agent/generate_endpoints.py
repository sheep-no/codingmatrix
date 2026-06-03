import asyncio
import logging
import json
import time
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, and_
from sqlalchemy.exc import SQLAlchemyError

from app.utils.security import verify_token
from app.db.database import get_db
from app.schema.codeRequest import GenerateRequest, GenerateResponse
from app.models.saved_project import SavedProject
from app.utils.agent_core import ProjectGeneratorAgent

from .schemas import (
    SaveProjectRequest, SaveProjectResponse,
    ProjectListResponse, LoadProjectResponse,
)
from .helpers import (
    _build_agent_config, _validate_project_path, _collect_files,
    _create_zip_archive_safe, _cleanup_temp_dir,
)
from .project_config import (
    PROJECTS_BASE_DIR, PROJECT_MIME_TYPES,
    MAX_SAVED_PROJECTS_PER_USER,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate_project(
        req: GenerateRequest,
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub", "anonymous")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"./projects/{timestamp}_{user_id}"

    agent_config = _build_agent_config(req)

    agent = ProjectGeneratorAgent(config=agent_config)

    def empty_callback(msg: str):
        pass

    try:
        result = await agent.generate_project(
            requirement=req.requirement,
            output_dir=output_dir,
            session_id=req.session_id,
            callback=empty_callback
        )

        project_name = Path(output_dir).name

        if not result["validation"]["runnable"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "项目生成完成但验证未通过",
                    "validation": result["validation"],
                    "output_dir": project_name
                }
            )

        return GenerateResponse(
            success=True,
            output_dir=project_name,
            total_files_created=result["total_files_created"],
            steps=result["steps"],
            validation=result["validation"]
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "项目生成失败",
                "error": str(e),
                "output_dir": Path(output_dir).name
            }
        )


@router.get("/generate/download/{project_path:path}")
async def download_project(
        project_path: str,
        token: dict = Depends(verify_token)
):
    user_id = token.get("sub", "anonymous")
    logger.info(f"下载请求 | 用户: {user_id} | 项目: {project_path}")
    start_time = time.time()

    project_dir = _validate_project_path(project_path, user_id)

    temp_dir = tempfile.mkdtemp()

    zip_filename = f"{project_dir.name}.zip"
    zip_filepath = Path(temp_dir) / zip_filename

    logger.info(f"开始压缩 | 文件夹: {project_dir.name} | 目标: {zip_filename}")

    success = await asyncio.to_thread(_create_zip_archive_safe, project_dir, zip_filepath)

    if not success or not zip_filepath.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="创建压缩包失败")

    zip_size = zip_filepath.stat().st_size
    elapsed = time.time() - start_time
    logger.info(f"下载准备就绪 | 项目: {project_dir.name} | 大小: {zip_size / 1024:.1f}KB | 耗时: {elapsed:.2f}s")

    return FileResponse(
        path=str(zip_filepath),
        filename=zip_filename,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        },
        background=BackgroundTask(
            lambda: _cleanup_temp_dir(temp_dir, project_dir.name)
        )
    )


@router.get("/generate/files")
async def get_project_files(
    project_path: str,
    token: dict = Depends(verify_token)
):
    user_id = token.get("sub", "anonymous")
    start_time = time.time()
    logger.info(f"获取项目文件列表 | 用户：{user_id} | 项目：{project_path}")
    
    project_dir = _validate_project_path(project_path, user_id)

    files = []
    skipped_dirs = 0
    skipped_files = 0

    async for file_info in _collect_files(project_dir):
        files.append(file_info)
    
    priority_files = ['README.md', 'index.html', 'main.py', 'package.json', 'requirements.txt']
    
    def sort_key(file):
        path = file['path']
        name = file['name']
        for i, priority in enumerate(priority_files):
            if path == priority or name == priority:
                return (0, i, path, name)
        return (1, 0, path, name)
    
    files.sort(key=sort_key)
    
    elapsed = time.time() - start_time
    logger.info(f"返回文件列表 | 文件数：{len(files)} | 跳过目录：{skipped_dirs} | 跳过文件：{skipped_files} | 耗时：{elapsed:.3f}s")
    
    return {
        'project': project_path,
        'total': len(files),
        'skipped_dirs': skipped_dirs,
        'skipped_files': skipped_files,
        'files': files
    }

@router.get("/generate/read")
async def read_project_file(
    project_path: str,
    file_path: str,
    token: dict = Depends(verify_token)
):
    user_id = token.get("sub", "anonymous")
    logger.info(f"读取项目文件 | 用户：{user_id} | 项目：{project_path} | 文件：{file_path}")

    project_dir = _validate_project_path(project_path, user_id)

    target_file = (project_dir / file_path).resolve()

    if not str(target_file).startswith(str(project_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {target_file}")
        raise HTTPException(status_code=403, detail="无权访问该文件")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="不是有效的文件")

    suffix = target_file.suffix.lower()
    mime_type = PROJECT_MIME_TYPES.get(suffix, 'text/plain')

    try:
        content = target_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = "[二进制文件，无法显示]"
    except Exception as e:
        logger.error(f"读取文件失败 | 文件：{target_file} | 错误：{str(e)}")
        raise HTTPException(status_code=500, detail=f"读取文件失败：{str(e)}")

    stat = target_file.stat()

    return {
        'project': project_path,
        'file_path': file_path,
        'name': target_file.name,
        'mime_type': mime_type,
        'size': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'content': content
    }

@router.delete("/generate/file")
async def delete_project_file(
    project_path: str,
    file_path: str,
    token: dict = Depends(verify_token)
):
    user_id = token.get("sub", "anonymous")
    logger.info(f"删除项目文件 | 用户：{user_id} | 项目：{project_path} | 文件：{file_path}")

    project_dir = _validate_project_path(project_path, user_id)

    target_file = (project_dir / file_path).resolve()

    if not str(target_file).startswith(str(project_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {target_file}")
        raise HTTPException(status_code=403, detail="无权访问该文件")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="不是有效的文件")

    try:
        target_file.unlink()
        logger.info(f"文件已删除 | 文件：{target_file}")
        return {'status': 'deleted', 'file_path': file_path}
    except Exception as e:
        logger.error(f"删除文件失败 | 文件：{target_file} | 错误：{str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件失败：{str(e)}")


@router.post("/save", response_model=SaveProjectResponse)
async def save_project(
    request: SaveProjectRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    logger.info(f"保存项目 | user_id={user_id} | name={request.name}")

    try:
        try:
            json.loads(request.project_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"project_data 必须是有效的 JSON 格式：{str(e)}")

        count_result = await db.execute(
            select(func.count()).select_from(SavedProject).where(
                SavedProject.user_id == user_id
            )
        )
        current_count = count_result.scalar() or 0

        if current_count >= MAX_SAVED_PROJECTS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"已达到保存项目上限（{MAX_SAVED_PROJECTS_PER_USER}个）。请先删除不需要的项目后再保存。"
            )

        saved_project = SavedProject(
            user_id=user_id,
            name=request.name,
            description=request.description,
            project_path=request.project_path,
            project_data=request.project_data
        )
        db.add(saved_project)
        await db.commit()
        await db.refresh(saved_project)

        logger.info(f"项目保存成功 | user_id={user_id} | project_id={saved_project.id}")

        return SaveProjectResponse(
            id=saved_project.id,
            name=saved_project.name,
            description=saved_project.description,
            project_path=saved_project.project_path,
            created_at=saved_project.created_at,
            message="项目保存成功"
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"保存项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="保存项目失败")

@router.get("/saved", response_model=ProjectListResponse)
async def list_saved_projects(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 50
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        count_result = await db.execute(
            select(func.count()).select_from(SavedProject).where(
                SavedProject.user_id == user_id
            )
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            select(SavedProject)
            .where(SavedProject.user_id == user_id)
            .order_by(SavedProject.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        projects = result.scalars().all()

        project_list = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "project_path": p.project_path,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            }
            for p in projects
        ]

        logger.info(f"获取保存项目列表 | user_id={user_id} | count={len(project_list)}")

        return ProjectListResponse(
            projects=project_list,
            total=total,
            max_allowed=MAX_SAVED_PROJECTS_PER_USER
        )

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"获取项目列表异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取项目列表失败")

@router.get("/saved/{project_id}", response_model=LoadProjectResponse)
async def load_saved_project(
    project_id: int,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        result = await db.execute(
            select(SavedProject).where(
                and_(
                    SavedProject.id == project_id,
                    SavedProject.user_id == user_id
                )
            )
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        logger.info(f"加载保存项目 | user_id={user_id} | project_id={project_id}")

        return LoadProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            project_path=project.project_path,
            project_data=project.project_data,
            created_at=project.created_at,
            updated_at=project.updated_at
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"加载项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="加载项目失败")

@router.delete("/saved/{project_id}")
async def delete_saved_project(
    project_id: int,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    try:
        result = await db.execute(
            delete(SavedProject).where(
                and_(
                    SavedProject.id == project_id,
                    SavedProject.user_id == user_id
                )
            )
        )
        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目不存在")

        logger.info(f"删除保存项目 | user_id={user_id} | project_id={project_id}")

        return {"status": "deleted", "project_id": project_id}

    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"删除项目异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除项目失败")