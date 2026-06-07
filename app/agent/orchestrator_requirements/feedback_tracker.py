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
                    self._conn.execute(
                        "DELETE FROM association_feedback WHERE id IN "
                        "(SELECT id FROM association_feedback ORDER BY created_at ASC LIMIT ?)",
                        (db_size // 4,)
                    )
                    self._conn.commit()
            except Exception as e:
                logger.debug(f"反馈追踪操作失败：{e}")
