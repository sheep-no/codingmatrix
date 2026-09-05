from app.agent.database_profiles import (
    DEFAULT_DATABASE_PROFILES,
    DatabaseProfileStatus,
)


def test_default_database_profiles_expose_common_contracts() -> None:
    sqlite = DEFAULT_DATABASE_PROFILES.resolve("SQLite")
    postgres = DEFAULT_DATABASE_PROFILES.resolve("postgresql")

    assert sqlite.status is DatabaseProfileStatus.SUPPORTED
    assert sqlite.driver == "sqlite3"
    assert "restart_persistence" in sqlite.capabilities
    assert postgres.migration_tool == "alembic"


def test_unknown_database_is_explicitly_unsupported() -> None:
    profile = DEFAULT_DATABASE_PROFILES.resolve("cockroachdb")

    assert profile.status is DatabaseProfileStatus.UNSUPPORTED
    assert profile.test_database == "unsupported"
    assert profile.diagnostics == ("database profile not found: cockroachdb",)
