import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class UserPreferences:

    DB_PATH = Path("/tmp/user_preferences.db")

    MAX_PREFERENCES_SIZE = 512 * 1024
    MAX_STATS_SIZE = 256 * 1024

    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    stats TEXT NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS archived_users (
                    user_id TEXT PRIMARY KEY,
                    preferences TEXT NOT NULL,
                    stats TEXT NOT NULL,
                    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cutoff = datetime.utcnow() - timedelta(days=90)
            conn.execute(
                """
                INSERT OR IGNORE INTO archived_users (user_id, preferences, stats)
                SELECT user_id, preferences, stats FROM user_preferences
                WHERE updated_at < ?
                """,
                (cutoff.isoformat(),),
            )
            conn.execute(
                """
                DELETE FROM user_preferences WHERE updated_at < ?
                """,
                (cutoff.isoformat(),),
            )
            conn.commit()

    def get_preferences(self, user_id: int) -> Dict:
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            row = conn.execute(
                "SELECT preferences FROM user_preferences WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
            if row is None:
                return {}
            return json.loads(row[0])

    def set_preferences(self, user_id: int, preferences: Dict):
        serialized = json.dumps(preferences, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > self.MAX_PREFERENCES_SIZE:
            raise ValueError("preferences data exceeds size limit")
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences, stats, updated_at)
                VALUES (?, ?, '{}', ?)
                ON CONFLICT(user_id) DO UPDATE SET preferences=?, updated_at=?
                """,
                (str(user_id), serialized, now, serialized, now),
            )
            conn.commit()

    def get_stats(self, user_id: int) -> Dict:
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            row = conn.execute(
                "SELECT stats FROM user_preferences WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
            if row is None:
                return {}
            return json.loads(row[0])

    def update_stats(self, user_id: int, key: str, value: Any):
        stats = self.get_stats(user_id)
        stats[key] = value
        serialized = json.dumps(stats, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > self.MAX_STATS_SIZE:
            raise ValueError("stats data exceeds size limit")
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences, stats, updated_at)
                VALUES (?, '{}', ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET stats=?, updated_at=?
                """,
                (str(user_id), serialized, now, serialized, now),
            )
            conn.commit()

    def record_project_generation(self, user_id: int, project_info: Dict):
        stats = self.get_stats(user_id)
        generations = stats.get("project_generations", [])
        project_info["timestamp"] = datetime.utcnow().isoformat()
        generations.append(project_info)
        if len(generations) > 100:
            generations = generations[-100:]
        stats["project_generations"] = generations
        stats["total_generations"] = stats.get("total_generations", 0) + 1
        serialized = json.dumps(stats, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > self.MAX_STATS_SIZE:
            generations = generations[-20:]
            stats["project_generations"] = generations
            serialized = json.dumps(stats, ensure_ascii=False)
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences, stats, updated_at)
                VALUES (?, '{}', ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET stats=?, updated_at=?
                """,
                (str(user_id), serialized, now, serialized, now),
            )
            conn.commit()

    def get_preferred_models(self, user_id: int) -> Dict:
        prefs = self.get_preferences(user_id)
        return prefs.get("models", {})

    def get_preferred_frameworks(self, user_id: int) -> list:
        prefs = self.get_preferences(user_id)
        return prefs.get("frameworks", [])

    def cleanup_inactive_users(self, days: int = 90):
        cutoff = datetime.utcnow() - timedelta(days=days)
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO archived_users (user_id, preferences, stats)
                SELECT user_id, preferences, stats FROM user_preferences
                WHERE updated_at < ?
                """,
                (cutoff.isoformat(),),
            )
            conn.execute(
                "DELETE FROM user_preferences WHERE updated_at < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()

    def get_db_size(self) -> int:
        if self.DB_PATH.exists():
            return self.DB_PATH.stat().st_size
        return 0


_user_preferences: Optional[UserPreferences] = None


def get_user_preferences() -> UserPreferences:
    global _user_preferences
    if _user_preferences is None:
        _user_preferences = UserPreferences()
    return _user_preferences