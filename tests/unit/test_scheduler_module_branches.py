"""Branch coverage for app/db/scheduler.py task functions."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.db.scheduler as scheduler


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, results=None, error=None):
        self._results = list(results or [])
        self.error = error
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt):
        if self.error:
            raise self.error
        return self._results.pop(0) if self._results else _Rows([])

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Session:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture(autouse=True)
def _fake_session(monkeypatch):
    holder = {}

    def _install(db):
        holder["db"] = db
        monkeypatch.setattr(scheduler, "async_session", lambda: _Session(db))

    yield _install


class TestHelpers:
    @pytest.mark.parametrize(
        "value,expected",
        [("daily", 1), ("WEEKLY", 7), (" monthly ", 30), ("yearly", 7)],
    )
    def test_log_cleanup_interval_days(self, monkeypatch, value, expected):
        monkeypatch.setattr(
            scheduler.settings, "LOG_CLEANUP_SCHEDULE", value, raising=False
        )
        assert scheduler._log_cleanup_interval_days() == expected

    def test_deferred_start_is_near_future(self):
        now = datetime.now()
        result = scheduler._deferred_start(30)
        assert now < result < now + timedelta(minutes=5)

    def test_delete_managed_path_unresolvable(self, monkeypatch):
        monkeypatch.setattr(
            scheduler.Path, "resolve", MagicMock(side_effect=ValueError("bad"))
        )
        assert scheduler._delete_managed_path("x") is False

    def test_delete_managed_path_oserror(self, monkeypatch, tmp_path):
        root = tmp_path / "uploads"
        root.mkdir()
        monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())
        target = root / "a.txt"
        target.write_text("x")
        monkeypatch.setattr(
            scheduler.Path, "unlink", MagicMock(side_effect=OSError("denied"))
        )
        assert scheduler._delete_managed_path(str(target)) is False


class TestTaskFunctions:
    @pytest.mark.asyncio
    async def test_archive_task(self, monkeypatch, _fake_session):
        db = _DB()
        _fake_session(db)
        archiver = SimpleNamespace(archive_all_users=AsyncMock())
        monkeypatch.setattr(scheduler, "ChatArchiver", MagicMock(return_value=archiver))

        await scheduler.archive_task()

        archiver.archive_all_users.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_files_task_success(self, monkeypatch, _fake_session, tmp_path):
        root = tmp_path / "uploads"
        root.mkdir()
        monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())

        deleted_file = SimpleNamespace(
            id=1,
            file_path=str(root / "old.txt"),
            is_deleted=1,
            updated_at=datetime.utcnow() - timedelta(days=10),
            created_at=datetime.utcnow() - timedelta(days=40),
        )
        raw = _Rows([deleted_file])
        orphan_rows = _Rows([])
        db = _DB(results=[raw, orphan_rows])
        _fake_session(db)

        await scheduler.cleanup_files_task()

        assert db.deleted == [deleted_file]
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_cleanup_files_task_skips_recent_deleted(self, _fake_session):
        recent = SimpleNamespace(
            id=1,
            file_path="x",
            is_deleted=1,
            updated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db = _DB(results=[_Rows([recent]), _Rows([])])
        _fake_session(db)

        await scheduler.cleanup_files_task()
        assert db.deleted == []

    @pytest.mark.asyncio
    async def test_cleanup_files_task_skips_no_updated_at(self, _fake_session):
        record = SimpleNamespace(
            id=1,
            file_path="x",
            is_deleted=1,
            updated_at=None,
            created_at=datetime.utcnow(),
        )
        db = _DB(results=[_Rows([record]), _Rows([])])
        _fake_session(db)

        await scheduler.cleanup_files_task()
        assert db.deleted == []

    @pytest.mark.asyncio
    async def test_cleanup_files_task_error_rolls_back(self, _fake_session):
        db = _DB(error=SQLAlchemyError("boom"))
        _fake_session(db)

        with pytest.raises(SQLAlchemyError):
            await scheduler.cleanup_files_task()
        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_cleanup_tasks_task_success(self, _fake_session, monkeypatch):
        old_task = SimpleNamespace(id=1)
        db = _DB(results=[_Rows([old_task])])
        _fake_session(db)
        monkeypatch.setattr(
            scheduler.task_manager,
            "cleanup_old_tasks",
            AsyncMock(return_value=2),
        )

        await scheduler.cleanup_tasks_task()

        assert db.deleted == [old_task]
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_cleanup_tasks_task_error(self, _fake_session):
        db = _DB(error=RuntimeError("boom"))
        _fake_session(db)

        with pytest.raises(RuntimeError):
            await scheduler.cleanup_tasks_task()
        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_cleanup_logs_task_success(self, monkeypatch):
        archiver = SimpleNamespace(
            archive_all=MagicMock(
                return_value={"rotated": [1], "archived": [1, 2], "cleaned": []}
            )
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.utils.log_archiver",
            SimpleNamespace(get_log_archiver=lambda: archiver),
        )

        await scheduler.cleanup_logs_task()
        archiver.archive_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_logs_task_error(self, monkeypatch):
        archiver = SimpleNamespace(
            archive_all=MagicMock(side_effect=RuntimeError("boom"))
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.utils.log_archiver",
            SimpleNamespace(get_log_archiver=lambda: archiver),
        )
        await scheduler.cleanup_logs_task()

    @pytest.mark.asyncio
    async def test_recover_expired_tasks_task_with_results(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler, "recover_expired_tasks", AsyncMock(return_value=[1, 2])
        )

        await scheduler.recover_expired_tasks_task()

        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_recover_expired_tasks_task_empty(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler, "recover_expired_tasks", AsyncMock(return_value=[])
        )

        await scheduler.recover_expired_tasks_task()

        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_recover_expired_tasks_task_error(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler,
            "recover_expired_tasks",
            AsyncMock(side_effect=RuntimeError("boom")),
        )

        await scheduler.recover_expired_tasks_task()

        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_unified_retention_task_success(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler,
            "process_retention_records",
            AsyncMock(return_value={"archived": 1}),
        )

        await scheduler.unified_retention_task()

        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_unified_retention_task_error(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler,
            "process_retention_records",
            AsyncMock(side_effect=RuntimeError("boom")),
        )

        await scheduler.unified_retention_task()

        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_project_retention_sweep_task_success(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler, "sweep_project_retention", AsyncMock(return_value={"scanned": 2})
        )

        await scheduler.project_retention_sweep_task()

        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_project_retention_sweep_task_error(self, _fake_session, monkeypatch):
        db = _DB()
        _fake_session(db)
        monkeypatch.setattr(
            scheduler,
            "sweep_project_retention",
            AsyncMock(side_effect=RuntimeError("boom")),
        )

        await scheduler.project_retention_sweep_task()

        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_cleanup_generated_assets_task_success(self, monkeypatch):
        module = SimpleNamespace(cleanup_generated_assets=AsyncMock(return_value={"x": 1}))
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.services.generated_asset_retention",
            module,
        )

        await scheduler.cleanup_generated_assets_task()
        module.cleanup_generated_assets.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_generated_assets_task_error(self, monkeypatch):
        module = SimpleNamespace(
            cleanup_generated_assets=AsyncMock(side_effect=RuntimeError("boom"))
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.services.generated_asset_retention",
            module,
        )
        await scheduler.cleanup_generated_assets_task()

    def test_start_and_stop_scheduler(self, monkeypatch):
        fake = SimpleNamespace(
            start=MagicMock(),
            running=True,
            shutdown=MagicMock(),
        )
        monkeypatch.setattr(scheduler, "scheduler", fake)
        fake_logger = MagicMock()
        monkeypatch.setattr(scheduler, "logger", fake_logger)

        scheduler.start_scheduler()
        fake.start.assert_called_once()
        assert fake_logger.info.called

        scheduler.stop_scheduler()
        fake.shutdown.assert_called_once_with(wait=False)

    def test_stop_scheduler_when_not_running(self, monkeypatch):
        fake = SimpleNamespace(running=False, shutdown=MagicMock())
        monkeypatch.setattr(scheduler, "scheduler", fake)

        scheduler.stop_scheduler()
        fake.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_files_task_processes_orphans(monkeypatch, _fake_session, tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())
    orphan = SimpleNamespace(
        id=5,
        file_path=str(root / "orphan.txt"),
        is_deleted=0,
        updated_at=None,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    linked = SimpleNamespace(
        id=6,
        file_path=str(root / "linked.txt"),
        is_deleted=0,
        updated_at=None,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    db = _DB(results=[_Rows([]), _Rows([orphan, linked]), _Rows([(6,), (None,)])])
    _fake_session(db)

    await scheduler.cleanup_files_task()

    assert db.deleted == [orphan]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_cleanup_files_task_orphan_delete_failure_keeps_record(
    monkeypatch, _fake_session
):
    orphan = SimpleNamespace(
        id=7,
        file_path="x",
        is_deleted=0,
        updated_at=None,
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    db = _DB(results=[_Rows([]), _Rows([orphan]), _Rows([])])
    _fake_session(db)
    monkeypatch.setattr(scheduler, "_delete_managed_path", lambda path: False)

    await scheduler.cleanup_files_task()

    assert db.deleted == []


def test_delete_managed_path_handles_unlink_and_rmtree(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())

    directory = root / "dir"
    directory.mkdir()
    monkeypatch.setattr(scheduler.shutil, "rmtree", MagicMock())
    assert scheduler._delete_managed_path(str(directory)) is True


def test_delete_managed_path_file_not_found(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())
    target = root / "missing.txt"

    monkeypatch.setattr(
        scheduler.Path, "unlink", MagicMock(side_effect=FileNotFoundError())
    )
    assert scheduler._delete_managed_path(str(target)) is True
