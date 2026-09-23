import time
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class AssociationFeedbackTracker:

    DB_PATH = Path("./data/association_feedback.db")
    MAX_DB_SIZE_BYTES = 2 * 1024 * 1024
    RETENTION_DAYS = 90
    # 清理频率闸：endpoint 每个请求都会 new 一个 tracker，若不限频则每请求
    # 都跑一次全表 DELETE + pragma 查询。清理是幂等的后台维护，按小时级执行足够。
    CLEANUP_INTERVAL_SECONDS = 3600
    _cleanup_gate = threading.Lock()
    _last_cleanup_at = 0.0

    def __init__(self):
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self._write_lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS association_feedback ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT NOT NULL, "
            "domain TEXT DEFAULT '', "
            "requirement TEXT, "
            "item_category TEXT, "
            "item_content TEXT, "
            "item_source TEXT, "
            "user_action TEXT, "
            "rejection_reason TEXT DEFAULT '', "
            "overall_helpfulness TEXT DEFAULT '', "
            "created_at REAL NOT NULL)"
        )
        self._conn.commit()
        self._maybe_cleanup()

    def _maybe_cleanup(self):
        """按频率闸执行清理，避免每次实例化都写库。"""
        now = time.time()
        with AssociationFeedbackTracker._cleanup_gate:
            if now - AssociationFeedbackTracker._last_cleanup_at < self.CLEANUP_INTERVAL_SECONDS:
                return
            AssociationFeedbackTracker._last_cleanup_at = now
        self._cleanup()

    def record_choice(self, session_id: str, requirement: str,
                      items: List[Dict], action: str):
        with self._write_lock:
            for item in items:
                self._conn.execute(
                    "INSERT INTO association_feedback "
                    "(session_id, domain, requirement, item_category, item_content, "
                    "item_source, user_action, rejection_reason, overall_helpfulness, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (session_id, "", requirement, item.get("category", ""),
                     item.get("content", ""), item.get("source", ""),
                     action, item.get("rejection_reason", ""),
                     item.get("helpfulness", ""),
                     time.time())
                )
            self._conn.commit()

    def record_helpfulness(self, session_id: str, requirement: str,
                           helpfulness: str):
        with self._write_lock:
            self._conn.execute(
                "UPDATE association_feedback SET overall_helpfulness = ? "
                "WHERE session_id = ? AND requirement = ?",
                (helpfulness, session_id, requirement)
            )
            self._conn.commit()

    def get_feedback_stats(self) -> Dict[str, Any]:
        cursor = self._conn.execute(
            "SELECT item_source, user_action, COUNT(*) FROM association_feedback "
            "GROUP BY item_source, user_action"
        )
        stats = {}
        for row in cursor.fetchall():
            source, action, count = row
            key = f"{source}:{action}"
            stats[key] = count
        return stats

    def get_rejection_reason_stats(self) -> Dict[str, int]:
        cursor = self._conn.execute(
            "SELECT rejection_reason, COUNT(*) FROM association_feedback "
            "WHERE user_action = 'rejected' AND rejection_reason != '' "
            "GROUP BY rejection_reason"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _cleanup(self):
        with self._write_lock:
            cutoff = time.time() - self.RETENTION_DAYS * 86400
            self._conn.execute(
                "DELETE FROM association_feedback WHERE created_at < ?", (cutoff,)
            )
            self._conn.commit()
            try:
                cursor = self._conn.execute(
                    "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
                )
                db_size = cursor.fetchone()[0]
                if db_size > self.MAX_DB_SIZE_BYTES:
                    # 超限时按行数裁剪最旧的四分之一。原实现把字节数当作 LIMIT
                    # 行数（db_size // 4），行数远小于该值时会把整表删空。
                    row_count = self._conn.execute(
                        "SELECT COUNT(*) FROM association_feedback"
                    ).fetchone()[0]
                    self._conn.execute(
                        "DELETE FROM association_feedback WHERE id IN "
                        "(SELECT id FROM association_feedback "
                        "ORDER BY created_at ASC, id ASC LIMIT ?)",
                        (max(1, row_count // 4),)
                    )
                    self._conn.commit()
            except Exception as e:
                logger.debug(f"反馈追踪操作失败：{e}")
