"""
SessionManager - 会话管理器

支持：
1. 会话状态持久化（断点续传）
2. 增量生成（基于已有 session_id，只生成修改部分）
3. 文件级 Embedding 增量检测（量化变更幅度，小改动跳过）
4. 差异检测（对比新旧需求和已生成内容）
5. 人机协作暂停/恢复
"""

import json
import hashlib
import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

from app.utils.math_utils import cosine_similarity

from app.agent.tracing import traced

logger = logging.getLogger(__name__)

# 会话存储目录
SESSION_DIR = Path("./sessions")
# 会话过期时间（30 天）
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
# 最大活跃会话数
MAX_ACTIVE_SESSIONS = 500


class SessionStatus(str, Enum):
    """会话状态"""
    RUNNING = "running"
    PAUSED = "paused"          # 等待用户确认
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileStatus:
    """单个文件的状态"""
    path: str
    status: str = "pending"    # pending, generating, completed, failed, skipped, needs_update
    content_hash: str = ""     # 内容哈希（用于增量检测）
    content_embedding: Optional[List[float]] = None  # 内容 embedding（用于语义变更检测）
    last_modified: str = ""    # 最后修改时间
    error: str = ""


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    requirement: str
    output_dir: str = ""
    status: str = SessionStatus.RUNNING.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # 架构设计
    architecture: Dict[str, Any] = field(default_factory=dict)
    file_plan: List[Dict[str, Any]] = field(default_factory=list)

    # 文件状态
    file_statuses: Dict[str, FileStatus] = field(default_factory=dict)

    # 进度
    current_step: str = ""
    current_file: str = ""
    files_generated: int = 0
    files_total: int = 0

    # 错误和警告
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 增量生成
    is_incremental: bool = False
    changed_files: List[str] = field(default_factory=list)  # 需要重新生成的文件
    unchanged_files: List[str] = field(default_factory=list)  # 可复用的文件

    # v4.8.0: Git 分支管理
    current_branch: Optional[str] = None
    base_commit: Optional[str] = None
    snapshot_tags: List[str] = field(default_factory=list)

# 人机协作
    pause_reason: str = ""      # 暂停原因
    pause_file: str = ""        # 暂停位置
    _approval_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)

    @property
    def approval_queue(self) -> asyncio.Queue:
        return self._approval_queue

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        d = {k: v for k, v in asdict(self).items() if not k.startswith('_')}
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """从字典反序列化"""
        data = data.copy()
        data['_approval_queue'] = asyncio.Queue()
        # 恢复 FileStatus
        file_statuses = data.get('file_statuses', {})
        for path, fs in file_statuses.items():
            if isinstance(fs, dict):
                file_statuses[path] = FileStatus(**fs)
        data['file_statuses'] = file_statuses
        return cls(**data)


class SessionManager:
    """会话管理器（统一状态管理：DB 为唯一真相源，SM 为写透缓存）"""

    def __init__(self, session_dir: Optional[Path] = None, db_session_factory=None):
        self.session_dir = session_dir or SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._active_sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._db_session_factory = db_session_factory

    async def _sync_to_db(self, session_id: str, status: str, files_generated: int = 0, files_total: int = 0, error_message: Optional[str] = None):
        """将状态变更写透到 DB（统一状态管理的核心方法）"""
        if not self._db_session_factory:
            return
        try:
            from app.db.models import ProjectSession
            from sqlalchemy import select
            async with self._db_session_factory() as db:
                result = await db.execute(
                    select(ProjectSession).where(ProjectSession.session_id == session_id)
                )
                session = result.scalar_one_or_none()
                if session:
                    session.status = status
                    session.last_activity_at = datetime.now(timezone.utc)
                    if files_generated > 0:
                        session.files_generated = files_generated
                    if files_total > 0:
                        session.files_total = files_total
                    if error_message:
                        session.error_message = error_message
                    if status in ("completed", "failed", "cancelled"):
                        session.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.debug(f"[SessionManager] DB 同步完成: session={session_id} status={status}")
                else:
                    logger.warning(f"[SessionManager] DB 中找不到会话: session_id={session_id}")
        except Exception as e:
            logger.warning(f"[SessionManager] DB 同步失败（不影响 SM 状态）: {e}")

    @traced("session.create", attributes={"component": "session"})
    async def create_session(
        self,
        requirement: str,
        output_dir: str,
        architecture: Optional[Dict] = None,
        file_plan: Optional[List[Dict]] = None,
        session_id: Optional[str] = None
    ) -> SessionState:
        """创建新会话"""
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        state = SessionState(
            session_id=session_id,
            requirement=requirement,
            output_dir=output_dir,
            architecture=architecture or {},
            file_plan=file_plan or [],
            files_total=len(file_plan) if file_plan else 0
        )

        for file_info in (file_plan or []):
            path = file_info.get("path", "")
            if path:
                state.file_statuses[path] = FileStatus(path=path)

        async with self._lock:
            self._active_sessions[session_id] = state
        await self._save_session(state)
        await self.cleanup_if_needed()
        return state

    @traced("session.resume", attributes={"component": "session"})
    async def resume_session(self, session_id: str) -> Optional[SessionState]:
        """恢复已有会话（增量生成）"""
        async with self._lock:
            if session_id in self._active_sessions:
                return self._active_sessions[session_id]

        session_file = self._session_file(session_id)
        if not session_file.exists():
            logger.warning(f"会话不存在: {session_id}")
            return None

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            state = SessionState.from_dict(data)
            async with self._lock:
                self._active_sessions[session_id] = state
            return state
        except Exception as e:
            logger.error(f"恢复会话失败: {e}")
            return None

    async def update_file_status(
        self,
        session_id: str,
        file_path: str,
        status: str,
        content: Optional[str] = None,
        error: str = ""
    ):
        """更新文件状态"""
        state = await self._get_state(session_id)
        if not state:
            return

        if file_path not in state.file_statuses:
            state.file_statuses[file_path] = FileStatus(path=file_path)

        fs = state.file_statuses[file_path]
        fs.status = status
        fs.last_modified = datetime.now().isoformat()
        if error:
            fs.error = error
        if content:
            fs.content_hash = self._compute_hash(content)

        state.updated_at = datetime.now().isoformat()
        if status == "completed":
            state.files_generated = sum(
                1 for f in state.file_statuses.values()
                if f.status == "completed"
            )

        await self._save_session(state)

    async def pause_session(
        self,
        session_id: str,
        reason: str,
        current_file: str = ""
    ):
        """暂停会话（等待用户确认）"""
        state = await self._get_state(session_id)
        if not state:
            return

        state.status = SessionStatus.PAUSED.value
        state.pause_reason = reason
        state.pause_file = current_file
        state.current_step = "waiting_for_approval"
        await self._save_session(state)

    async def resume_from_pause(self, session_id: str, approved: bool = True):
        """从暂停状态恢复"""
        state = await self._get_state(session_id)
        if not state:
            return

        if approved:
            state.status = SessionStatus.RUNNING.value
            state.current_step = "resuming"
        else:
            if state.pause_file in state.file_statuses:
                state.file_statuses[state.pause_file].status = "skipped"
            state.status = SessionStatus.RUNNING.value
            state.current_step = "resuming"

        state.pause_reason = ""
        state.pause_file = ""
        state.updated_at = datetime.now().isoformat()
        await self._save_session(state)

    async def complete_session(self, session_id: str, errors: Optional[List[str]] = None, files_generated: int = 0, files_total: int = 0):
        """完成会话（写透到 DB）"""
        state = await self._get_state(session_id)
        if not state:
            return

        status = SessionStatus.FAILED.value if errors else SessionStatus.COMPLETED.value
        state.status = status
        state.completed_at = datetime.now().isoformat()
        state.updated_at = datetime.now().isoformat()
        if errors:
            state.errors.extend(errors)
        if files_generated > 0:
            state.files_generated = files_generated
        if files_total > 0:
            state.files_total = files_total
        await self._save_session(state)
        await self._sync_to_db(session_id, status, files_generated, files_total)

    async def cancel_session(self, session_id: str):
        """取消会话（写透到 DB）"""
        state = await self._get_state(session_id)
        if not state:
            # 即使内存中无状态，也要更新 DB
            await self._sync_to_db(session_id, SessionStatus.CANCELLED.value)
            return

        state.status = SessionStatus.CANCELLED.value
        state.completed_at = datetime.now().isoformat()
        state.updated_at = datetime.now().isoformat()
        await self._save_session(state)
        await self._sync_to_db(session_id, SessionStatus.CANCELLED.value)

    async def _get_state(self, session_id: str) -> Optional[SessionState]:
        """获取会话状态，优先从内存加载，失败则从磁盘恢复"""
        async with self._lock:
            state = self._active_sessions.get(session_id)
        if not state:
            state = await self.resume_session(session_id)
        return state

    @traced("session.cleanup", attributes={"component": "session"})
    async def cleanup_expired(self) -> int:
        """清理过期会话"""
        now = time.time()
        expired = []
        async with self._lock:
            for sid, state in list(self._active_sessions.items()):
                try:
                    updated = datetime.fromisoformat(state.updated_at).timestamp()
                    if now - updated > SESSION_TTL_SECONDS:
                        expired.append(sid)
                except (ValueError, OSError):
                    expired.append(sid)
            for sid in expired:
                del self._active_sessions[sid]
                self._session_locks.pop(sid, None)  # 清理对应的锁
        for sid in expired:
            session_file = self._session_file(sid)
            if session_file.exists():
                session_file.unlink()

            # 联动清理：同步更新 DB 中的会话状态
            try:
                from app.db.database import async_session
                from app.db.models import ProjectSession
                from sqlalchemy import select

                async with async_session() as db:
                    result = await db.execute(
                        select(ProjectSession).where(ProjectSession.session_id == sid)
                    )
                    session = result.scalar_one_or_none()
                    if session and session.status == "running":
                        session.status = "expired"
                        session.error_message = "会话已过期（TTL 清理）"
                        session.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                        logger.debug(f"已同步 DB 会话状态: session_id={sid} -> expired")
            except Exception as e:
                logger.warning(f"同步 DB 会话状态失败（不影响内存清理）: {e}")

        if expired:
            logger.info(f"清理 {len(expired)} 个过期会话")
        return len(expired)

    async def cleanup_if_needed(self):
        """如果活跃会话数超过上限，自动清理过期和最旧的非运行中会话"""
        async with self._lock:
            count = len(self._active_sessions)
        if count > MAX_ACTIVE_SESSIONS:
            await self.cleanup_expired()
            # 如果仍然超限，移除最旧的非运行中会话
            async with self._lock:
                count = len(self._active_sessions)
                if count > MAX_ACTIVE_SESSIONS:
                    # 只驱逐非 RUNNING 状态的会话
                    evictable = [
                        (sid, state) for sid, state in self._active_sessions.items()
                        if state.status != SessionStatus.RUNNING.value
                    ]
                    sorted_sessions = sorted(evictable, key=lambda x: x[1].updated_at)
                    to_remove = min(count - MAX_ACTIVE_SESSIONS, len(sorted_sessions))
                    for sid, _ in sorted_sessions[:to_remove]:
                        del self._active_sessions[sid]
                        self._session_locks.pop(sid, None)
                    if to_remove > 0:
                        logger.warning(f"会话数超限，强制移除 {to_remove} 个最旧非运行会话")

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态"""
        state = await self._get_state(session_id)
        if not state:
            return None

        return {
            "session_id": state.session_id,
            "requirement": state.requirement[:100],
            "status": state.status,
            "current_step": state.current_step,
            "current_file": state.current_file,
            "files_generated": state.files_generated,
            "files_total": state.files_total,
            "is_incremental": state.is_incremental,
            "changed_files": state.changed_files,
            "unchanged_files": state.unchanged_files,
            "pause_reason": state.pause_reason,
            "errors": state.errors,
            "warnings": state.warnings,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "files": {
                path: {
                    "status": fs.status,
                    "last_modified": fs.last_modified,
                    "error": fs.error
                }
                for path, fs in state.file_statuses.items()
            }
        }

    async def detect_incremental_changes(
        self,
        session_id: str,
        new_requirement: str,
        output_dir: Path,
        file_embeddings: Optional[Dict[str, List[float]]] = None
    ) -> Dict[str, Any]:
        """
        检测增量变化，返回需要重新生成的文件列表

        优化：
        - 使用 embedding 相似度检测语义变更
        - 小变更（相似度 > 0.95）直接跳过重新生成

        Returns:
            {
                "state": SessionState,
                "changed_files": [...],
                "unchanged_files": [...],
                "small_changes": [...]  # 有小变更但可复用的文件
            }
        """
        state = await self.resume_session(session_id)
        if not state:
            raise ValueError(f"会话不存在: {session_id}")

        state.is_incremental = True

        # 检测需求变化
        old_req_hash = self._compute_hash(state.requirement)
        new_req_hash = self._compute_hash(new_requirement)
        requirement_changed = old_req_hash != new_req_hash

        if requirement_changed:
            state.requirement = new_requirement

        # 检测已生成文件的变化
        changed = []
        unchanged = []
        small_changes = []  # 语义相似度高，可跳过重新生成

        for file_info in state.file_plan:
            file_path = file_info.get("path", "")
            if not file_path:
                continue

            full_path = output_dir / file_path
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                current_hash = self._compute_hash(content)

                fs = state.file_statuses.get(file_path)
                if fs and fs.status == "completed" and fs.content_hash and fs.content_hash == current_hash:
                    # 文件已成功生成且未修改且需求未变，可复用
                    if not requirement_changed:
                        unchanged.append(file_path)
                        continue

                # 文件已修改或需求变化，检查语义变更幅度
                if (file_embeddings and file_path in file_embeddings and
                        fs and fs.content_embedding is not None):
                    similarity = self._compute_embedding_similarity(
                        fs.content_embedding, file_embeddings[file_path]
                    )
                    # 语义相似度高（> 0.95），视为小变更，跳过重新生成
                    if similarity > 0.95:
                        small_changes.append(file_path)
                        unchanged.append(file_path)
                        continue

                # 文件需要重新生成
                changed.append(file_path)
            else:
                # 文件不存在，需要生成
                changed.append(file_path)

        state.changed_files = changed
        state.unchanged_files = unchanged + small_changes

        logger.info(
            f"增量检测完成: {len(changed)} 个文件需要更新, "
            f"{len(unchanged)} 个文件可复用, "
            f"{len(small_changes)} 个小变更跳过"
        )

        await self._save_session(state)
        return {
            "state": state,
            "changed_files": changed,
            "unchanged_files": unchanged,
            "small_changes": small_changes
        }

    def get_file_plan_for_incremental(self, state: SessionState) -> List[Dict]:
        """获取增量生成的文件计划（只包含需要生成的文件）"""
        if not state.is_incremental:
            return state.file_plan

        return [
            fi for fi in state.file_plan
            if fi.get("path", "") in state.changed_files
        ]

    @staticmethod
    def _compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    @staticmethod
    def _compute_embedding_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算 embedding 余弦相似度"""
        return cosine_similarity(vec1, vec2)

    def _session_file(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.session_dir / f"{session_id}.json"

    @traced("session.save", attributes={"component": "session"})
    async def _save_session(self, state: SessionState):
        """保存会话到磁盘（使用 per-session 锁防止并发写入竞争）"""
        session_id = state.session_id
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        async with self._session_locks[session_id]:
            session_file = self._session_file(session_id)
            try:
                data = state.to_dict()
                # 使用原子写入：先写临时文件，再重命名，防止并发写入导致文件损坏
                tmp_file = session_file.with_suffix('.tmp')
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                tmp_file.replace(session_file)
            except Exception as e:
                logger.error(f"保存会话失败: {e}")
                raise
