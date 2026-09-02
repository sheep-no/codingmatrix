import logging
import os
import shutil
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator, List

from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete, and_
from sqlalchemy.exc import SQLAlchemyError

from app.utils.security import verify_token
from app.db.database import get_db
from app.db.models import ProjectSession
from app.utils.guard_contracts import get_guard_contracts
from app.utils.agent_skills import get_skills_manager
from app.schema.codeRequest import GenerateRequest, AgentConfig
from app.agent.models import DEFAULT_FAST_MODEL

from .project_config import (
    PROJECTS_BASE_DIR,
    ALLOWED_PACKAGES,
    PROJECT_MIME_TYPES,
    SKIP_DIRS,
    MAX_TEXT_FILE_SIZE,
)

logger = logging.getLogger(__name__)

_dependency_graph_cache: Optional[Dict] = None
_guard_contracts_cache: Optional[Dict] = None

_session_manager = None
_session_manager_lock = asyncio.Lock()
_approval_queues: Dict[str, asyncio.Queue] = {}

_spec_cache = None
_spec_cache_lock = asyncio.Lock()

_feedback_learner = None
_feedback_learner_lock = asyncio.Lock()


def _validate_project_path(project_path: str, user_id: str) -> Path:
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

    # 用户归属校验：项目目录名格式为 {timestamp}_{unique_id}_{user_id}
    # 检查目录名最后一段是否等于 user_id，防止跨用户访问
    dir_name = project_dir.name
    if user_id and user_id != "anonymous":
        # 新格式：{timestamp}_{unique_id}_{user_id} — 取最后一段精确匹配
        parts = dir_name.rsplit("_", 1)
        if len(parts) == 2 and parts[1] == user_id:
            pass  # 校验通过
        elif user_id == parts[-1]:
            pass  # 兼容旧格式
        else:
            logger.warning(f"跨用户访问拒绝 | 请求用户: {user_id} | 项目目录: {dir_name}")
            raise HTTPException(status_code=403, detail="无权访问其他用户的项目")

    return project_dir


def resolve_output_dir(output_dir: str) -> Path:
    """将 output_dir 转为绝对路径（兼容新旧格式）
    
    新格式: "{user_id}/{project_name}" (相对路径)
    旧格式: "./projects/orchestrator/project_*" (绝对路径)
    """
    if output_dir.startswith("./projects/"):
        # 旧格式：绝对路径
        return Path(output_dir).resolve()
    else:
        # 新格式：相对路径
        return (Path(PROJECTS_BASE_DIR) / output_dir).resolve()


def cleanup_session_files(output_dir: str) -> bool:
    """清理会话产生的文件
    
    Args:
        output_dir: 会话的 output_dir（相对路径或绝对路径）
    
    Returns:
        是否成功清理
    """
    try:
        full_path = resolve_output_dir(output_dir)
        if full_path.exists():
            shutil.rmtree(full_path)
            logger.info(f"已清理会话文件: {full_path}")
            return True
        return True  # 目录不存在也算成功
    except Exception as e:
        logger.error(f"清理会话文件失败: {output_dir} - {e}")
        return False


async def _collect_files(project_dir: Path) -> AsyncGenerator[dict, None]:
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
    return AgentConfig(
        model=req.model,
        stream=stream,
        max_thinking_tokens=req.max_thinking_tokens,
        max_output_tokens=req.max_output_tokens,
        temperature=req.temperature,
        enable_validation=req.enable_validation,
        enable_venv_validation=req.enable_venv_validation,
        shared_base_venv="/opt/base_venv" if req.enable_venv_validation else None,
        auto_install_deps=False,
        allowed_packages=ALLOWED_PACKAGES
    )


def load_dependency_graph() -> Optional[Dict]:
    global _dependency_graph_cache
    if _dependency_graph_cache is not None:
        return _dependency_graph_cache
    graph_path = Path(__file__).parent.parent.parent.parent / "data" / "dependency_graph.json"
    if graph_path.exists():
        try:
            _dependency_graph_cache = json.loads(graph_path.read_text(encoding='utf-8'))
            logger.info(f"依赖图谱已加载: {_dependency_graph_cache.get('file_count', 0)} 个文件, "
                       f"{_dependency_graph_cache.get('edge_count', 0)} 条边")
            return _dependency_graph_cache
        except Exception as e:
            logger.error(f"依赖图谱加载失败: {e}")
    else:
        logger.warning("依赖图谱文件不存在，请先运行: python scripts/build_dependency_graph.py")
    return None


def load_guard_contracts() -> Optional[Dict]:
    global _guard_contracts_cache
    if _guard_contracts_cache is not None:
        return _guard_contracts_cache
    try:
        contracts = get_guard_contracts()
        _guard_contracts_cache = contracts.to_dict()
        logger.info(f"守护合约已加载: {len(contracts.rules)} 条规则")
        return _guard_contracts_cache
    except Exception as e:
        logger.error(f"守护合约加载失败: {e}")
    return None


def get_agent_knowledge_base() -> Dict[str, Any]:
    knowledge = {
        "dependency_graph": load_dependency_graph(),
        "guard_contracts": load_guard_contracts(),
        "cognitive_skills": get_skills_manager().get_all_skills_context(),
    }
    return knowledge


async def _safe_update_progress(update_progress, **kwargs) -> bool:
    for attempt in range(3):
        try:
            await update_progress(**kwargs)
            return True
        except Exception as e:
            logger.warning(f"进度更新失败 (尝试 {attempt+1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
    return False


def _create_zip_archive_safe(source_dir: Path, zip_path: Path):
    try:
        shutil.make_archive(
            str(zip_path.with_suffix('')),
            'zip',
            source_dir
        )
        logger.info(f"压缩完成 | 文件夹: {source_dir.name} -> {zip_path.name}")
        return True
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"压缩失败 | 文件夹: {source_dir} | 错误: {str(e)}")
        return False


def _cleanup_temp_dir(temp_dir: str, project_name: str):
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"清理完成 | 项目: {project_name} | 临时目录: {temp_dir}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.warning(f"清理失败 | 临时目录: {temp_dir} | 错误: {str(e)}")


async def get_session_manager():
    global _session_manager
    if _session_manager is None:
        async with _session_manager_lock:
            if _session_manager is None:
                from app.agent.session_manager import SessionManager
                from app.db.database import async_session
                _session_manager = SessionManager(db_session_factory=async_session)
    return _session_manager


async def get_spec_cache():
    global _spec_cache
    if _spec_cache is None:
        async with _spec_cache_lock:
            if _spec_cache is None:
                from app.agent.spec_cache import SpecCache
                _spec_cache = SpecCache()
    return _spec_cache


async def get_feedback_learner():
    global _feedback_learner
    if _feedback_learner is None:
        async with _feedback_learner_lock:
            if _feedback_learner is None:
                from app.agent.feedback_learner import FeedbackLearner
                _feedback_learner = FeedbackLearner()
    return _feedback_learner


async def _cleanup_old_session(user_id: str, db: AsyncSession):
    from app.core.config import settings

    max_sessions = settings.MAX_PROJECT_SESSIONS_PER_USER

    result = await db.execute(
        select(ProjectSession).where(
            ProjectSession.user_id == user_id,
            ProjectSession.status.in_(["running", "completed", "failed", "expired", "cancelled"])
        ).order_by(ProjectSession.created_at.desc())
    )
    all_sessions = result.scalars().all()

    if len(all_sessions) <= max_sessions:
        return

    sessions_to_keep = set(s.session_id for s in all_sessions[:max_sessions])
    sessions_to_cleanup = [s for s in all_sessions if s.session_id not in sessions_to_keep]

    for old_sess in sessions_to_cleanup:
        sm = await get_session_manager()
        session_file = sm._session_file(old_sess.session_id)
        if session_file.exists():
            try:
                session_file.unlink()
                logger.info(f"已删除旧会话文件: {session_file}")
            except OSError as e:
                logger.warning(f"删除会话文件失败: {e}")

        if old_sess.output_dir:
            output_path = Path(old_sess.output_dir)
            if output_path.exists():
                try:
                    shutil.rmtree(output_path)
                    logger.info(f"已删除旧项目目录: {output_path}")
                except OSError as e:
                    logger.warning(f"删除项目目录失败: {e}")

        from app.models.history import History
        await db.execute(
            sql_delete(History).where(
                History.user_id == user_id,
                History.metadata_json.contains(f'"session_id": "{old_sess.session_id}"')
            )
        )

        old_sess.status = "cancelled"
        old_sess.completed_at = datetime.now(timezone.utc)

    await db.commit()

    if sessions_to_cleanup:
        logger.info(f"已清理用户 {user_id} 的 {len(sessions_to_cleanup)} 个旧会话资源（保留最新 {max_sessions} 个）")


async def _detect_and_clean_zombie_sessions(db: AsyncSession, user_id: str) -> int:
    """
    检测并清理僵尸会话
    
    僵尸会话定义：
    1. DB 中 status=running 但内存中无对应 SessionState 的会话
    2. DB 中 status=running 且最后活动时间超过 7 天的会话
    
    Returns:
        清理的僵尸会话数量
    """
    from app.utils.dynamic_concurrent import ConcurrentLimitManager
    from datetime import timedelta
    
    try:
        # 查询 DB 中 status=running 的会话
        result = await db.execute(
            select(ProjectSession).where(
                ProjectSession.user_id == int(user_id),
                ProjectSession.status == "running"
            )
        )
        running_sessions = result.scalars().all()
        
        if not running_sessions:
            return 0
        
        # 检查内存中是否有对应的 SessionState
        sm = await get_session_manager()
        zombie_count = 0
        concurrent_mgr = ConcurrentLimitManager()
        
        # 7 天超时阈值（基于最后活动时间）
        timeout_threshold = datetime.now(timezone.utc) - timedelta(days=7)
        
        for session in running_sessions:
            is_zombie = False
            
            # 检查 1：最后活动时间超过 7 天
            last_activity_at = session.last_activity_at
            if last_activity_at and last_activity_at.tzinfo is None:
                last_activity_at = last_activity_at.replace(tzinfo=timezone.utc)
            if last_activity_at and last_activity_at < timeout_threshold:
                is_zombie = True
                logger.warning(f"检测到超时会话 (最后活动超过7天): session_id={session.session_id}, user_id={user_id}")
            
            # 检查 2：内存中无该会话
            if not is_zombie:
                memory_state = await sm._get_state(session.session_id)
                if memory_state is None:
                    is_zombie = True
                    logger.warning(f"检测到僵尸会话 (内存无状态): session_id={session.session_id}, user_id={user_id}")
            
            if is_zombie:
                # 清理文件
                if session.output_dir:
                    cleanup_session_files(session.output_dir)
                
                # 标记为 failed
                session.status = "failed"
                session.error_message = "僵尸会话自动清理（超时或进程崩溃）"
                session.completed_at = datetime.now(timezone.utc)
                
                zombie_count += 1
        
        if zombie_count > 0:
            await db.commit()
            logger.info(f"已清理 {zombie_count} 个僵尸会话 (user_id={user_id})")
        
        return zombie_count
        
    except Exception as e:
        logger.error(f"僵尸会话检测失败: {e}", exc_info=True)
        return 0


async def _create_project_session(db: AsyncSession, user_id: int, session_id: str, requirement: str, output_dir: str):
    session = ProjectSession(
        session_id=session_id,
        user_id=user_id,
        requirement=requirement,
        output_dir=output_dir,
        status="running"
    )
    db.add(session)
    await db.commit()
    return session


async def _update_session_activity(db: AsyncSession, session_id: str):
    """更新会话的最后活动时间"""
    try:
        result = await db.execute(
            select(ProjectSession).where(ProjectSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.last_activity_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.warning(f"更新会话活动时间失败: {session_id} - {e}")


async def _update_project_session_status(db: Optional[AsyncSession], session_id: str, status: str, files_generated: int = 0, files_total: int = 0, error_message: Optional[str] = None):
    """更新会话状态（DB + 内存同步）"""
    if db is None:
        logger.warning(f"更新会话状态失败：db 为 None | session_id={session_id} | status={status}")
        return
    
    try:
        result = await db.execute(
            select(ProjectSession).where(ProjectSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            # 会话结束时清理文件（仅失败/取消时清理，成功完成时保留文件以支持 resume）
            if status in ("failed", "cancelled"):
                if session.output_dir:
                    cleanup_session_files(session.output_dir)
            
            session.status = status
            session.files_generated = files_generated
            session.files_total = files_total
            session.last_activity_at = datetime.now(timezone.utc)
            if error_message:
                session.error_message = error_message
            if status in ("completed", "failed", "cancelled"):
                session.completed_at = datetime.now(timezone.utc)
                
                # 联动清理：同步更新内存中的会话状态
                try:
                    sm = await get_session_manager()
                    memory_state = await sm._get_state(session_id)
                    if memory_state:
                        memory_state.status = status
                        memory_state.completed_at = datetime.now(timezone.utc).isoformat()
                        memory_state.updated_at = datetime.now(timezone.utc).isoformat()
                        await sm._save_session(memory_state)
                        logger.debug(f"已同步内存会话状态: session_id={session_id} -> {status}")
                except Exception as e:
                    logger.warning(f"同步内存会话状态失败（不影响 DB 更新）: {e}")
            
            await db.commit()
        else:
            logger.warning(f"会话不存在：session_id={session_id}")
    except SQLAlchemyError as e:
        logger.error(f"更新会话状态异常 | session_id={session_id} | error={str(e)}", exc_info=True)


def verify_admin_token(token: dict = Depends(verify_token)) -> dict:
    if token.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return token


async def verify_session_ownership(db: AsyncSession, session_id: str, user_id: str) -> ProjectSession:
    """
    验证会话所有权 - 防止越权操作
    
    Args:
        db: 数据库会话
        session_id: 会话 ID
        user_id: 用户 ID
        
    Returns:
        ProjectSession 对象
        
    Raises:
        HTTPException: 如果会话不存在或不属于当前用户
    """
    try:
        result = await db.execute(
            select(ProjectSession).where(
                and_(
                    ProjectSession.session_id == session_id,
                    ProjectSession.user_id == int(user_id)
                )
            )
        )
        session = result.scalar_one_or_none()
        
        if session is None:
            # 不区分"不存在"和"无权限"，防止信息泄露
            raise HTTPException(status_code=404, detail="会话不存在或无访问权限")
        
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证会话所有权失败 | session_id={session_id} | error={e}")
        raise HTTPException(status_code=500, detail="验证会话失败")


# ==================== 意图检测 ====================

async def detect_resume_intent(requirement: str, model: str = DEFAULT_FAST_MODEL) -> Dict[str, Any]:
    """
    检测用户输入是否包含"继续"意图
    
    Args:
        requirement: 用户输入
        model: 用于意图检测的轻量模型
        
    Returns:
        {
            "is_resume": bool,           # 是否是继续意图
            "has_changes": bool,         # 是否包含需求变更
            "additional_requirement": str,  # 补充的需求（如有）
            "original_requirement": str,    # 原始需求（从最近会话获取）
            "target_session_id": str,       # 目标会话 ID（空表示最近会话）
            "resume_type": str              # 恢复类型: "recent" | "historical"
        }
    """
    from app.utils import call_llm
    
    prompt = f"""分析以下用户输入，判断是否包含"继续"意图。

用户输入："{requirement}"

请返回 JSON：
{{
  "is_resume": true/false,  // 是否是继续意图（继续、resume、恢复、接着来、修复上次的bug等）
  "has_changes": true/false,  // 是否包含需求变更或补充
  "additional_requirement": "补充的需求内容"  // 如果有补充需求，提取出来；否则为空字符串
}}

只返回 JSON，不要其他文字："""

    try:
        result = await call_llm(
            model=model,
            prompt=prompt,
            temperature=0.1,
            max_tokens=200
        )
        
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # 提取 JSON
        import json
        json_match = __import__('re').search(r'\{[^{}]+\}', content)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "is_resume": data.get("is_resume", False),
                "has_changes": data.get("has_changes", False),
                "additional_requirement": data.get("additional_requirement", ""),
                "target_session_id": "",
                "resume_type": "recent"
            }
    except Exception as e:
        logger.warning(f"意图检测失败: {e}")
    
    # 兜底：简单关键词检测
    resume_keywords = ["继续生成", "继续项目", "继续开发", "resume", "恢复项目", "接着生成", "接着写"]
    is_resume = any(kw in requirement for kw in resume_keywords)
    
    return {
        "is_resume": is_resume,
        "has_changes": False,
        "additional_requirement": "",
        "target_session_id": "",
        "resume_type": "recent"
    }


async def resolve_resume_session(
    db: AsyncSession,
     user_id: str,
     requirement: str,
     model: str = DEFAULT_FAST_MODEL,
     limit: int = 20
) -> Optional[ProjectSession]:
    """
    方案 2：智能解析要恢复的 session
    
    根据用户输入，从最近 N 个 session 中找到最相关的那个。
    适用于"修复上上轮的登录 bug"等需要语义匹配的场景。
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        requirement: 用户输入
        model: 用于匹配的模型
        limit: 要检索的 session 数量
        
    Returns:
        最相关的 session，或者 None（没有找到可恢复的）
    """
    from app.utils import call_llm
    
    # 1. 获取用户最近的 session（排除 running 状态，因为那是当前正在进行的）
    query = select(ProjectSession).where(
        ProjectSession.user_id == user_id,
        ProjectSession.status.in_(["completed", "cancelled", "failed"])
    )
    query = query.order_by(ProjectSession.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    sessions = list(result.scalars().all())
    
    if not sessions:
        # 只检查 running 状态
        return await get_user_recent_session(db, user_id, status_filter="running")
    
    # 2. 构建 session 摘要列表
    session_summaries = []
    for i, s in enumerate(sessions):
        req_preview = s.requirement[:100] + ("..." if len(s.requirement) > 100 else "")
        session_summaries.append(
            f"[{i+1}] ID: {s.session_id}\n"
            f"    时间: {s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '未知'}\n"
            f"    需求: {req_preview}\n"
            f"    状态: {s.status}\n"
            f"    文件: {s.files_generated}/{s.files_total}"
        )
    
    summaries_text = "\n\n".join(session_summaries)
    
    # 3. 让 LLM 找到最相关的那个
    prompt = f"""你是会话匹配助手。根据用户的输入，从历史会话列表中找到最匹配的那个。

用户输入："{requirement}"

历史会话列表：
{summaries_text}

请返回最匹配的会话编号（数字 1-{len(sessions)}）。
如果没有任何匹配的，返回 0。
只返回数字，不要其他文字："""

    try:
        result = await call_llm(
            model=model,
            prompt=prompt,
            temperature=0.1,
            max_tokens=10
        )
        
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        import re
        match = re.search(r'\d+', content)
        if match:
            idx = int(match.group())
            if 1 <= idx <= len(sessions):
                return sessions[idx - 1]
    except Exception as e:
        logger.warning(f"智能匹配 session 失败: {e}")
    
    # 兜底：返回最近的
    return sessions[0] if sessions else None


async def analyze_files_to_regenerate(
     original_requirement: str,
     additional_requirement: str,
     generated_files: List[str],
     model: str = DEFAULT_FAST_MODEL
) -> List[str]:
    """
    分析哪些文件需要重新生成
    
    Args:
        original_requirement: 原始需求
        additional_requirement: 补充/变更的需求
        generated_files: 已生成的文件列表
        model: 用于分析的模型
        
    Returns:
        需要重新生成的文件路径列表
    """
    from app.utils import call_llm
    
    files_str = "\n".join(f"- {f}" for f in generated_files)
    
    prompt = f"""分析需求变更，判断哪些文件需要重新生成。

原始需求：{original_requirement}

需求变更：{additional_requirement}

已生成的文件：
{files_str}

请分析需求变更会影响哪些文件，返回需要重新生成的文件列表。
只返回 JSON 数组，不要其他文字：
["file1.py", "file2.py"]"""

    try:
        result = await call_llm(
            model=model,
            prompt=prompt,
            temperature=0.1,
            max_tokens=500
        )
        
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # 提取 JSON 数组
        import json
        json_match = __import__('re').search(r'\[[^\[\]]*\]', content)
        if json_match:
            files_to_regenerate = json.loads(json_match.group())
            # 验证文件路径
            valid_files = [f for f in files_to_regenerate if f in generated_files]
            return valid_files
    except Exception as e:
        logger.warning(f"文件分析失败: {e}")
    
    return []


async def get_user_recent_session(db: AsyncSession, user_id: str, status_filter: Optional[str] = None) -> Optional[ProjectSession]:
    """
    获取用户最近的会话
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        status_filter: 状态过滤（如 "running", "cancelled"）
    
    Returns:
        最近的会话或 None
    """
    try:
        query = select(ProjectSession).where(ProjectSession.user_id == user_id)
        
        if status_filter:
            query = query.where(ProjectSession.status == status_filter)
        
        query = query.order_by(ProjectSession.created_at.desc()).limit(1)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"查询用户最近会话失败: {e}")
        return None
