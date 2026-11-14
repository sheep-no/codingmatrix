"""generated_asset_retention 文件名映射、分组与清理边界补测。"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import generated_asset_retention as module


def test_retention_seconds_from_days():
    assert module.retention_max_age_seconds(2) == 2 * 86400


def test_retention_seconds_rejects_zero():
    with pytest.raises(ValueError):
        module.retention_max_age_seconds(0)


def test_ppt_id_from_slides_json():
    assert module.ppt_id_from_filename("task-1_slides.json") == "task-1"


def test_ppt_id_from_supported_suffixes():
    for suffix in (".pptx", ".html", ".md", ".pdf"):
        assert module.ppt_id_from_filename(f"task{suffix}") == "task"


def test_ppt_id_rejects_unrelated_and_empty():
    assert module.ppt_id_from_filename("notes.txt") is None
    assert module.ppt_id_from_filename(".pptx") is None
    assert module.ppt_id_from_filename("_slides.json") is None


def test_collect_groups_returns_empty_for_missing_dir(tmp_path):
    assert module.collect_ppt_groups(tmp_path / "missing") == {}


def test_collect_groups_skips_owner_directory_entries(tmp_path):
    owners = tmp_path / ".owners"
    owners.mkdir()
    (owners / "fake.json").mkdir()

    assert module.collect_ppt_groups(tmp_path) == {}


def test_collect_groups_ignores_directories_and_owners(tmp_path):
    (tmp_path / "task.pptx").write_bytes(b"x")
    (tmp_path / "nested").mkdir()
    owners = tmp_path / ".owners"
    owners.mkdir()
    (owners / "owner-1.json").write_text("{}", encoding="utf-8")

    groups = module.collect_ppt_groups(tmp_path)

    assert set(groups) == {"task", "owner-1"}
    assert groups["owner-1"][0].name == "owner-1.json"


def test_newest_mtime_ignores_oserror(tmp_path, monkeypatch):
    path = tmp_path / "a.pptx"
    path.write_bytes(b"x")

    def boom(self):
        raise OSError("gone")

    monkeypatch.setattr(Path, "stat", boom)
    assert module._newest_mtime([path]) is None


def test_cleanup_rejects_negative_window(tmp_path):
    with pytest.raises(ValueError):
        module.cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=-1)


def test_cleanup_removes_only_expired_groups(tmp_path):
    old = tmp_path / "old.pptx"
    new = tmp_path / "new.pptx"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    import os
    os.utime(old, (1000, 1000))
    os.utime(new, (1000, 1000))

    result = module.cleanup_expired_ppt_artifacts(
        tmp_path, max_age_seconds=60, now=1_000_000
    )

    assert result["removed_ids"] == 2
    assert not old.exists() and not new.exists()


def test_cleanup_skips_group_without_mtime(tmp_path, monkeypatch):
    path = tmp_path / "task.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "_newest_mtime", lambda paths: None)

    result = module.cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=0)

    assert result == {"removed_ids": 0, "removed_files": 0}


def test_cleanup_counts_only_successful_deletes(tmp_path, monkeypatch):
    path = tmp_path / "task.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "_newest_mtime", lambda paths: 0)
    monkeypatch.setattr(module, "cleanup_file", lambda p: False)

    result = module.cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=60, now=1000)

    assert result["removed_files"] == 0


class _DB:
    def __init__(self, batches):
        self._batches = list(batches)
        self.deleted = []
        self.flushed = False

    async def scalars(self, _query):
        records = self._batches.pop(0)
        return type("S", (), {"all": lambda self: records})()

    async def delete(self, record):
        self.deleted.append(record)

    async def flush(self):
        self.flushed = True


async def test_cleanup_image_history_rejects_negative():
    with pytest.raises(ValueError):
        await module.cleanup_expired_image_history(_DB([]), max_age_seconds=-1)


async def test_cleanup_image_history_deletes_records_and_files(tmp_path, monkeypatch):
    target = tmp_path / "a.png"
    target.write_bytes(b"x")
    record = type("R", (), {"image_urls": ["a.png"]})()
    db = _DB([[record], []])
    monkeypatch.setattr(module, "resolve_reference", lambda url, root: target)
    monkeypatch.setattr(module, "cleanup_file", lambda path: True)
    monkeypatch.setattr(module, "cleanup_stale_files", lambda *a, **k: 3)

    result = await module.cleanup_expired_image_history(
        db, max_age_seconds=60, image_dir=tmp_path
    )

    assert result == {"removed_records": 1, "removed_files": 1, "removed_orphans": 3}
    assert db.flushed is True


async def test_cleanup_image_history_skips_unresolved_references(tmp_path, monkeypatch):
    record = type("R", (), {"image_urls": ["missing"]})()
    db = _DB([[record], []])
    monkeypatch.setattr(module, "resolve_reference", lambda url, root: None)
    monkeypatch.setattr(module, "cleanup_stale_files", lambda *a, **k: 0)

    result = await module.cleanup_expired_image_history(
        db, max_age_seconds=60, image_dir=tmp_path
    )

    assert result["removed_files"] == 0


async def test_cleanup_image_history_with_no_records_skips_flush(tmp_path, monkeypatch):
    db = _DB([[], []])
    monkeypatch.setattr(module, "cleanup_stale_files", lambda *a, **k: 0)

    await module.cleanup_expired_image_history(db, max_age_seconds=60, image_dir=tmp_path)

    assert db.flushed is False


async def test_cleanup_image_history_without_image_dir(tmp_path, monkeypatch):
    record = type("R", (), {"image_urls": None})()
    db = _DB([[record]])
    monkeypatch.setattr(module, "resolve_reference", lambda url, root: None)

    result = await module.cleanup_expired_image_history(db, max_age_seconds=60)

    assert result["removed_orphans"] == 0
    assert db.flushed is True


def test_cleanup_skips_ownerless_ppt_file(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    result = module.cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=0, now=0)
    assert result == {"removed_ids": 0, "removed_files": 0}


def test_newest_mtime_ignores_later_oserror(tmp_path, monkeypatch):
    good = tmp_path / "a.pptx"
    bad = tmp_path / "b.pptx"
    good.write_bytes(b"x")
    bad.write_bytes(b"x")
    original = Path.stat

    def stat(self):
        if self.name == "b.pptx":
            raise OSError("gone")
        return original(self)

    monkeypatch.setattr(Path, "stat", stat)
    assert module._newest_mtime([bad, good]) == good.stat().st_mtime


async def test_cleanup_generated_assets_with_injected_db(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "retention_max_age_seconds", lambda: 60)
    monkeypatch.setattr(module, "cleanup_expired_ppt_artifacts", lambda *a, **k: {"removed_ids": 0})
    monkeypatch.setattr(module, "cleanup_expired_image_history", _fake_image_cleanup)

    db = object()
    result = await module.cleanup_generated_assets(
        db, ppt_output_dir=tmp_path, image_dir=tmp_path
    )

    assert result == {"ppt": {"removed_ids": 0}, "images": {"removed_records": 0}}
    assert module._seen["db"] is db


async def _fake_image_cleanup(db, **kwargs):
    module._seen = {"db": db, "kwargs": kwargs}
    return {"removed_records": 0}


async def test_cleanup_generated_assets_opens_session_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "cleanup_expired_ppt_artifacts", lambda *a, **k: {"removed_ids": 1})
    monkeypatch.setattr(module, "cleanup_expired_image_history", _fake_image_cleanup)

    class _Session:
        committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            type(self).committed = True

    import app.db.database as database

    monkeypatch.setattr(database, "async_session", lambda: _Session())

    result = await module.cleanup_generated_assets(
        max_age_seconds=10, ppt_output_dir=tmp_path, image_dir=tmp_path
    )

    assert result["ppt"] == {"removed_ids": 1}
    assert _Session.committed is True


async def _fake_image_cleanup_empty(db, **kwargs):
    return {"removed_records": 0}


async def test_cleanup_generated_assets_without_db_uses_default_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "retention_max_age_seconds", lambda: 60)
    monkeypatch.setattr(module, "cleanup_expired_ppt_artifacts", lambda *a, **k: {"removed_ids": 0})
    monkeypatch.setattr(module, "cleanup_expired_image_history", _fake_image_cleanup_empty)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            pass

    import app.db.database as database

    monkeypatch.setattr(database, "async_session", lambda: _Session())
    result = await module.cleanup_generated_assets(ppt_output_dir=tmp_path, image_dir=tmp_path)

    assert result["images"] == {"removed_records": 0}


def test_newest_mtime_equal_values_keeps_first(tmp_path):
    import os

    first = tmp_path / "a.pptx"
    second = tmp_path / "b.pptx"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    os.utime(first, (500, 500))
    os.utime(second, (400, 400))

    assert module._newest_mtime([first, second]) == 500
