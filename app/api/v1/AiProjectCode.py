# /api/agent.py
import io
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
import asyncio
import json
from pathlib import Path
from typing import Generator, AsyncGenerator
from fastapi import APIRouter, HTTPException, Depends, Query, Header, UploadFile, File
from fastapi.responses import StreamingResponse,FileResponse,Response
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.exc import SQLAlchemyError

from starlette.background import BackgroundTask

from app.schema.codeRequest import GenerateRequest, GenerateResponse, AgentConfig
from app.models.saved_project import SavedProject
from app.models.agent_memory import AgentSession, ToolExecutionLog, ModelUsageStats
from app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, and_
from sqlalchemy.exc import SQLAlchemyError
from app.utils.security import verify_token
from app.utils.agent_core import ProjectGeneratorAgent, ProjectFileManager
from app.utils.task_manager import task_manager
from app.schema.task_schema import TaskResponse, TaskStatusEnum

router = APIRouter(prefix="/agent", tags=["项目生成 Agent"])
logger = logging.getLogger(__name__)


async def create_agent_session(
    db: AsyncSession,
    user_id: int,
    model_key: str,
    task_description: str
) -> Optional[AgentSession]:
    """创建 Agent 会话并记录项目生成"""
    try:
        session = AgentSession(
            user_id=user_id,
            session_type="code_generation",
            model_key=model_key,
            context_summary=task_description[:500] if task_description else None
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session
    except Exception as e:
        logger.error(f"创建 Agent 会话失败: {e}")
        return None


async def log_tool_execution(
    db: AsyncSession,
    session_id: str,
    tool_name: str,
    params: dict,
    result: str,
    success: bool = True,
    execution_time: float = 0
) -> None:
    """记录工具执行日志"""
    try:
        log = ToolExecutionLog(
            session_id=session_id,
            tool_name=tool_name,
            tool_params=params,
            tool_result=result[:5000] if result else None,
            success=success,
            execution_time=execution_time
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.error(f"记录工具执行日志失败: {e}")


async def update_model_stats(
    db: AsyncSession,
    user_id: int,
    model_key: str,
    model_name: str,
    tokens: int = 0,
    success: bool = True,
    execution_time: float = 0
) -> None:
    """更新模型使用统计"""
    try:
        result = await db.execute(
            select(ModelUsageStats).where(
                and_(
                    ModelUsageStats.user_id == user_id,
                    ModelUsageStats.model_key == model_key
                )
            )
        )
        stats = result.scalar_one_or_none()

        if stats:
            stats.request_count += 1
            stats.total_tokens += tokens
            if success:
                stats.success_count += 1
            else:
                stats.failure_count += 1
            stats.last_used_at = datetime.utcnow()
        else:
            stats = ModelUsageStats(
                user_id=user_id,
                model_key=model_key,
                model_name=model_name,
                request_count=1,
                total_tokens=tokens,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                avg_execution_time=execution_time,
                last_used_at=datetime.utcnow()
            )
            db.add(stats)

        await db.commit()
    except Exception as e:
        logger.error(f"更新模型统计失败: {e}")


async def accumulate_knowledge(
    db: AsyncSession,
    user_id: int,
    requirement: str,
    output_dir: str,
    result: dict
) -> None:
    """积累知识：从项目生成结果中提取知识"""
    try:
        from app.models.agent_memory import KnowledgeEntry

        knowledge_items = []

        # 1. 提取项目类型/框架
        if 'validation' in result and 'tech_stack' in result['validation']:
            tech_stack = result['validation'].get('tech_stack', [])
            for tech in tech_stack[:5]:  # 最多5个
                knowledge_items.append({
                    'content': f"项目使用了 {tech} 技术栈",
                    'category': 'tech_stack',
                    'source': 'project_generation'
                })

        # 2. 提取文件结构模式
        if 'total_files_created' in result and result['total_files_created'] > 0:
            knowledge_items.append({
                'content': f"生成了 {result['total_files_created']} 个文件到 {output_dir}",
                'category': 'project_pattern',
                'source': 'project_generation'
            })

        # 3. 保存用户需求作为参考
        if requirement:
            knowledge_items.append({
                'content': f"需求：{requirement[:200]}",
                'category': 'user_requirement',
                'source': 'project_generation'
            })

        # 批量写入
        for item in knowledge_items:
            entry = KnowledgeEntry(
                user_id=user_id,
                content=item['content'],
                category=item['category'],
                source=item['source'],
                importance=0.5
            )
            db.add(entry)

        if knowledge_items:
            await db.commit()
            logger.info(f"知识积累：添加了 {len(knowledge_items)} 条知识")
    except Exception as e:
        logger.error(f"知识积累失败: {e}")


async def log_generation_result(
    session_id: str,
    user_id: int,
    model_key: str,
    requirement: str,
    output_dir: str,
    result: dict,
    success: bool,
    execution_time: float
) -> None:
    """记录流式生成的结果（日志、统计、知识积累）"""
    try:
        from app.db.database import get_db

        async for db in get_db():
            try:
                # 记录工具执行
                await log_tool_execution(
                    db, session_id, "generate_project_stream",
                    {"requirement": requirement, "output_dir": output_dir},
                    json.dumps(result, ensure_ascii=False)[:5000] if result else None,
                    success=success,
                    execution_time=execution_time
                )
                # 更新模型统计
                await update_model_stats(
                    db, user_id, model_key, model_key,
                    tokens=result.get("total_tokens", 0) if result else 0,
                    success=success,
                    execution_time=execution_time
                )
                # 知识积累
                await accumulate_knowledge(
                    db, user_id, requirement, output_dir, result if result else {}
                )
            finally:
                break
    except Exception as e:
        logger.error(f"记录生成结果失败: {e}")

PROJECTS_BASE_DIR = "./projects"
USER_UPLOADS_DIR = os.path.join(PROJECTS_BASE_DIR, "user_uploads")

ALLOWED_PACKAGES = [
    "fastapi", "pydantic", "httpx", "sqlalchemy",
    "click", "typer", "pytest", "aiofiles"
]

PROJECT_MIME_TYPES = {
    '.py': 'text/x-python',
    '.js': 'text/javascript',
    '.ts': 'text/typescript',
    '.jsx': 'text/javascript',
    '.tsx': 'text/typescript',
    '.vue': 'text/x-vue',
    '.html': 'text/html',
    '.css': 'text/css',
    '.scss': 'text/x-scss',
    '.sass': 'text/x-sass',
    '.less': 'text/x-less',
    '.md': 'text/markdown',
    '.markdown': 'text/markdown',
    '.json': 'application/json',
    '.yaml': 'application/x-yaml',
    '.yml': 'application/x-yaml',
    '.txt': 'text/plain',
    '.log': 'text/plain',
    '.sh': 'text/x-sh',
    '.bash': 'text/x-sh',
    '.env': 'text/plain',
    '.gitignore': 'text/plain',
    '.dockerfile': 'text/plain',
    '.toml': 'application/x-toml',
    '.xml': 'application/xml',
    '.sql': 'application/x-sql',
    '.graphql': 'application/graphql',
    '.mdx': 'text/mdx'
}

SKIP_DIRS = {'__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build', '.next', 'coverage'}

MAX_TEXT_FILE_SIZE = 1024 * 1024
MAX_SAVED_PROJECTS_PER_USER = 3


def _validate_project_path(project_path: str, user_id: str) -> Path:
    """
    验证项目路径安全性，返回resolved路径
    抛出 HTTPException 如果路径越界或不存在
    """
    base_dir = Path(PROJECTS_BASE_DIR).resolve()
    project_dir = (base_dir / project_path).resolve()

    if not str(project_dir).startswith(str(base_dir)):
        logger.warning(f"路径越界 | 用户: {user_id} | 尝试访问: {project_dir}")
        raise HTTPException(status_code=403, detail="无权访问该路径")

    if not project_dir.exists():
        logger.warning(f"项目不存在 | 路径: {project_dir}")
        raise HTTPException(status_code=404, detail="项目不存在")

    if not project_dir.is_dir():
        logger.warning(f"不是文件夹 | 路径: {project_dir}")
        raise HTTPException(status_code=400, detail="不是有效的项目文件夹")

    return project_dir


async def _collect_files(project_dir: Path) -> AsyncGenerator[dict, None]:
    """
    异步生成器：收集项目文件信息
    边扫描边 yield，避免大项目一次性加载到内存
    """
    try:
        for file_path in project_dir.rglob("*"):
            try:
                if any(part.startswith('.') or part in SKIP_DIRS for part in file_path.parts):
                    continue

                if not file_path.is_file():
                    continue

                rel_path = file_path.relative_to(project_dir)
                stat = file_path.stat()

                if file_path.name.startswith('.'):
                    continue

                suffix = file_path.suffix.lower()
                file_type = PROJECT_MIME_TYPES.get(suffix, 'text/plain')

                if stat.st_size > MAX_TEXT_FILE_SIZE:
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read(1024)
                except (UnicodeDecodeError, PermissionError, IOError):
                    continue

                yield {
                    'name': file_path.name,
                    'path': str(rel_path),
                    'type': file_type,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                logger.debug(f"读取文件失败 | 文件：{file_path} | 错误：{str(e)}")
                continue
    except Exception as e:
        logger.error(f"扫描目录失败 | 目录：{project_dir} | 错误：{str(e)}")


def _build_agent_config(req: GenerateRequest, stream: bool = False) -> AgentConfig:
    """
    统一创建 AgentConfig
    确保所有接口使用相同的默认配置
    """
    return AgentConfig(
        model=req.model,
        stream=stream,
        max_thinking_tokens=req.max_thinking_tokens,
        max_output_tokens=req.max_output_tokens,
        temperature=req.temperature,
        enable_validation=True,
        enable_venv_validation=req.enable_venv_validation,
        shared_base_venv="/opt/base_venv" if req.enable_venv_validation else None,
        auto_install_deps=False,
        allowed_packages=ALLOWED_PACKAGES
    )


async def _safe_update_progress(update_progress, **kwargs) -> bool:
    """
    带重试的进度更新
    最多重试3次，提高进度更新的可靠性
    """
    for attempt in range(3):
        try:
            await update_progress(**kwargs)
            return True
        except Exception as e:
            logger.warning(f"进度更新失败 (尝试 {attempt+1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
    return False


class ThinkingStreamer:
    """辅助类：将思考内容通过队列流式输出"""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.logs = []

    def callback(self, msg: str) -> None:
        """符合 (str) -> None 签名的回调"""
        self.logs.append(msg)
        if msg.startswith("[Thinking]"):
            # 将思考内容放入队列
            self.queue.put_nowait(msg[10:])

    async def stream(self) -> Generator[str, None, None]:
        """SSE 生成器：从队列读取并yield"""
        while True:
            item = await self.queue.get()
            if item == "[DONE]":
                break
            yield f"data: {json.dumps({'type': 'thinking', 'content': item})}\n\n"

        yield "data: [DONE]\n\n"

    def get_logs(self) -> list:
        """获取所有日志"""
        return self.logs


def _create_zip_archive_safe(source_dir: Path, zip_path: Path):
    """创建zip压缩包 - 简单版本"""
    try:
        # 直接用shutil.make_archive，它会自动创建zip
        shutil.make_archive(
            str(zip_path.with_suffix('')),  # 去掉.zip后缀
            'zip',
            source_dir
        )
        logger.info(f"压缩完成 | 文件夹: {source_dir.name} -> {zip_path.name}")
        return True
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"压缩失败 | 文件夹: {source_dir} | 错误: {str(e)}")
        return False


def _cleanup_temp_dir(temp_dir: str, project_name: str):
    """清理临时目录"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"清理完成 | 项目: {project_name} | 临时目录: {temp_dir}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.warning(f"清理失败 | 临时目录: {temp_dir} | 错误: {str(e)}")

class SearchMatch:
    file_path: str
    line_number: int
    line_content: str
    match_start: int
    match_end: int


class ProjectTreeNode(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    children: Optional[list] = None


# ==================== 压缩包上传相关 ====================

USER_UPLOADS_MAX_SIZE = 50 * 1024 * 1024  # 50MB
USER_UPLOADS_ALLOWED_EXTENSIONS = {'.zip'}
USER_UPLOADS_ALLOWED_INNER_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.css', '.scss',
    '.sass', '.less', '.json', '.yaml', '.yml', '.xml', '.toml', '.ini',
    '.cfg', '.conf', '.properties', '.env', '.gitignore', '.dockerignore',
    '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs', '.rb', '.php',
    '.swift', '.kt', '.scala', '.cs', '.sh', '.bash', '.sql', '.md',
    '.txt', '.rst', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.ico', '.woff', '.woff2', '.ttf', '.eot', '.csv', '.xlsx',
    '.lock', '.pyi', '.mjs', '.cjs', '.dockerfile', 'dockerfile',
    'makefile', 'recipe',
}


def _sanitize_project_name(name: str) -> str:
    """清理项目名称，只保留安全字符"""
    name = re.sub(r'[^\w\-_.\u4e00-\u9fff]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if not name:
        name = f"project_{int(time.time())}"
    return name[:80]


def _validate_zip_safety(zf: zipfile.ZipFile) -> list:
    """
    验证 zip 文件安全性
    返回：允许解压的文件列表 [(zip_name, safe_name), ...]
    """
    safe_files = []
    for info in zf.infolist():
        name = info.filename

        if name.endswith('/'):
            continue

        if '..' in name:
            logger.warning(f"跳过包含 '..' 的条目: {name}")
            continue

        if name.startswith('/') or name.startswith('\\'):
            logger.warning(f"跳过绝对路径条目: {name}")
            continue

        inner_ext = Path(name).suffix.lower()
        inner_name = Path(name).name.lower()

        if inner_name in ('.gitignore', '.dockerignore', 'dockerfile', 'makefile', 'recipe'):
            safe_files.append((name, name))
            continue

        if inner_ext not in USER_UPLOADS_ALLOWED_INNER_EXTENSIONS:
            logger.warning(f"跳过不允许的文件类型: {name} (扩展名: {inner_ext})")
            continue

        safe_files.append((name, name))

    return safe_files


class ZipUploadResponse(BaseModel):
    success: bool
    project_name: str
    project_path: str
    file_count: int
    message: str


@router.post("/projects/upload-zip", response_model=ZipUploadResponse, summary="上传压缩包部署项目")
async def upload_project_zip(
    file: UploadFile = File(...),
    project_name: Optional[str] = Query(None, description="项目名称（可选，默认使用文件名）"),
    token: dict = Depends(verify_token)
):
    """
    上传 zip 压缩包并解压到用户项目目录

    - 仅支持 .zip 格式
    - 最大 50MB
    - 自动过滤不安全路径和不允许的文件类型
    - 解压到 ./projects/user_uploads/{project_name}/
    """
    user_id = int(token.get("sub"))
    logger.info(f"压缩包上传 | user_id={user_id} | filename={file.filename}")

    ext = Path(file.filename).suffix.lower() if file.filename else ''
    if ext not in USER_UPLOADS_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持 {', '.join(USER_UPLOADS_ALLOWED_EXTENSIONS)} 格式")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件不能为空")
    if len(content) > USER_UPLOADS_MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制 ({USER_UPLOADS_MAX_SIZE // 1024 // 1024}MB)")

    if not content.startswith(b'PK'):
        raise HTTPException(status_code=400, detail="无效的 zip 文件")

    base_name = Path(file.filename).stem if file.filename else 'project'
    final_name = _sanitize_project_name(project_name or base_name)

    target_dir = (Path(USER_UPLOADS_DIR).resolve() / str(user_id) / final_name).resolve()

    # 验证路径安全
    user_uploads_base = (Path(USER_UPLOADS_DIR).resolve() / str(user_id)).resolve()
    if not str(target_dir).startswith(str(user_uploads_base)):
        raise HTTPException(status_code=403, detail="路径不安全")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            bad_file = zf.testzip()
            if bad_file:
                raise HTTPException(status_code=400, detail=f"zip 文件损坏: {bad_file}")

            safe_files = _validate_zip_safety(zf)

            if not safe_files:
                raise HTTPException(status_code=400, detail="压缩包中没有允许的文件类型")

            target_dir.mkdir(parents=True, exist_ok=True)

            file_count = 0
            for zip_name, safe_name in safe_files:
                file_data = zf.read(zip_name)
                dest_path = target_dir / safe_name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(file_data)
                file_count += 1

        logger.info(f"压缩包解压成功 | user_id={user_id} | project={final_name} | files={file_count}")

        return ZipUploadResponse(
            success=True,
            project_name=final_name,
            project_path=f"user_uploads/{final_name}",
            file_count=file_count,
            message=f"成功解压 {file_count} 个文件到 {final_name}"
        )

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="无效的 zip 文件")
    except Exception as e:
        logger.error(f"压缩包解压失败 | user_id={user_id} | error={e}")
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="解压失败，请检查文件后重试")


class UploadedProjectInfo(BaseModel):
    project_name: str
    project_path: str
    file_count: int
    size_bytes: int
    created_at: str
    modified_at: str


@router.get("/projects/user-uploads", response_model=list[UploadedProjectInfo], summary="获取用户上传的项目列表")
async def list_user_uploads(token: dict = Depends(verify_token)):
    """获取用户上传的所有项目列表"""
    user_id = int(token.get("sub"))
    uploads_dir = Path(USER_UPLOADS_DIR).resolve() / str(user_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    projects = []
    for entry in sorted(uploads_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if entry.is_dir():
            file_count = sum(1 for _ in entry.rglob('*') if _.is_file())
            total_size = sum(_.stat().st_size for _ in entry.rglob('*') if _.is_file())
            stat = entry.stat()
            projects.append(UploadedProjectInfo(
                project_name=entry.name,
                project_path=f"user_uploads/{user_id}/{entry.name}",
                file_count=file_count,
                size_bytes=total_size,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))

    return projects


@router.delete("/projects/user-uploads/{project_name}", summary="删除用户上传的项目")
async def delete_user_upload(project_name: str, token: dict = Depends(verify_token)):
    """删除用户上传的项目"""
    user_id = int(token.get("sub"))
    safe_name = _sanitize_project_name(project_name)
    target_dir = Path(USER_UPLOADS_DIR).resolve() / str(user_id) / safe_name

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    user_uploads_base = (Path(USER_UPLOADS_DIR).resolve() / str(user_id)).resolve()
    if not str(target_dir).startswith(str(user_uploads_base)):
        raise HTTPException(status_code=403, detail="无权操作该路径")

    try:
        shutil.rmtree(target_dir)
        logger.info(f"删除用户上传项目 | user_id={user_id} | project={safe_name}")
        return {"success": True, "message": f"已删除项目 {safe_name}"}
    except Exception as e:
        logger.error(f"删除项目失败 | user_id={user_id} | error={e}")
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试")

