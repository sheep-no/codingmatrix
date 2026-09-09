"""Database contracts used by framework profiles and generation planning."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, Tuple

from pydantic import BaseModel, ConfigDict, Field


class DatabaseProfileStatus(str, Enum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


class DatabaseContract(BaseModel):
    """Framework-independent persistence requirements for one database."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    dialect: str = Field(min_length=1)
    driver: str | None = None
    orm: str | None = None
    migration_tool: str | None = None
    test_database: str = Field(min_length=1)
    status: DatabaseProfileStatus
    capabilities: Tuple[str, ...] = ()
    diagnostics: Tuple[str, ...] = ()


class DatabaseProfileRegistry:
    """Resolve aliases while preserving an explicit unsupported fallback."""

    def __init__(self, profiles: Iterable[DatabaseContract] = ()) -> None:
        self._profiles: Dict[str, DatabaseContract] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: DatabaseContract, *, aliases: Iterable[str] = ()) -> None:
        names = (profile.name, *aliases)
        for name in names:
            self._profiles[name.strip().lower()] = profile

    def resolve(self, name: str) -> DatabaseContract:
        key = name.strip().lower()
        profile = self._profiles.get(key)
        if profile is not None:
            return profile
        return DatabaseContract(
            name=name.strip() or "unknown",
            dialect="unknown",
            test_database="unsupported",
            status=DatabaseProfileStatus.UNSUPPORTED,
            diagnostics=(f"database profile not found: {name}",),
        )

    def all(self) -> Tuple[DatabaseContract, ...]:
        return tuple(dict.fromkeys(self._profiles.values()))


def default_database_profile_registry() -> DatabaseProfileRegistry:
    return DatabaseProfileRegistry([
        DatabaseContract(
            name="sqlite", dialect="sqlite", driver="sqlite3", orm="sqlalchemy",
            migration_tool="alembic", test_database="file-backed", status=DatabaseProfileStatus.SUPPORTED,
            capabilities=("transactions", "restart_persistence", "in_memory_tests"),
        ),
        DatabaseContract(
            name="postgresql", dialect="postgresql", driver="psycopg", orm="sqlalchemy",
            migration_tool="alembic", test_database="isolated-database", status=DatabaseProfileStatus.SUPPORTED,
            capabilities=("transactions", "migrations", "isolated_tests"),
        ),
        DatabaseContract(
            name="mysql", dialect="mysql", driver="pymysql", orm="sqlalchemy",
            migration_tool="alembic", test_database="isolated-database", status=DatabaseProfileStatus.SUPPORTED,
            capabilities=("transactions", "migrations", "isolated_tests"),
        ),
    ])


DEFAULT_DATABASE_PROFILES = default_database_profile_registry()

__all__ = [
    "DatabaseContract",
    "DatabaseProfileRegistry",
    "DatabaseProfileStatus",
    "DEFAULT_DATABASE_PROFILES",
    "default_database_profile_registry",
]
