"""cleanup_files_task 受管路径删除回归（db_layer.md DB13）。

原实现直接信任 File.file_path，配合 os.path.exists 做 exists→remove
的 TOCTOU 删除，脏数据或误配置可让 shutil.rmtree 指向上传目录之外。
"""

import importlib
from datetime import datetime, timedelta

import pytest

scheduler = importlib.import_module("app.db.scheduler")


@pytest.fixture()
def upload_root(tmp_path, monkeypatch):
    root = (tmp_path / "uploads")
    root.mkdir()
    monkeypatch.setattr(scheduler, "UPLOAD_ROOT", root.resolve())
    return root.resolve()


def test_deletes_file_inside_managed_root(upload_root):
    target = upload_root / "2026" / "09" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x")

    assert scheduler._delete_managed_path(str(target)) is True
    assert not target.exists()


def test_deletes_directory_inside_managed_root(upload_root):
    target = upload_root / "pkg"
    target.mkdir()
    (target / "inner.txt").write_text("x")

    assert scheduler._delete_managed_path(str(target)) is True
    assert not target.exists()


def test_rejects_path_outside_managed_root(upload_root, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me")

    assert scheduler._delete_managed_path(str(outside)) is False
    assert outside.exists()


def test_rejects_parent_escape(upload_root):
    escaped = upload_root.parent / "escape.txt"
    escaped.write_text("keep me")

    assert scheduler._delete_managed_path(str(upload_root / ".." / "escape.txt")) is False
    assert escaped.exists()


def test_rejects_managed_root_itself(upload_root):
    assert scheduler._delete_managed_path(str(upload_root)) is False
    assert upload_root.exists()


def test_missing_path_is_treated_as_deleted(upload_root):
    # 磁盘上已无该产物等价于删除完成，调用方应可清理数据库记录
    assert scheduler._delete_managed_path(str(upload_root / "gone.txt")) is True


def test_empty_path_is_rejected():
    assert scheduler._delete_managed_path("") is False


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeFile:
    def __init__(self, fid, path):
        self.id = fid
        self.file_path = path
        self.is_deleted = 0
        self.updated_at = datetime.utcnow() - timedelta(days=10)
        self.created_at = datetime.utcnow() - timedelta(days=40)


class _FakeDb:
    """按顺序返回软删除列表/孤立列表，并统计 Task 关联查询次数。"""

    def __init__(self, deleted, orphaned, linked_ids):
        self.deleted = deleted
        self.orphaned = orphaned
        self.linked_ids = linked_ids
        self.task_queries = 0
        self._file_queries = 0
        self.deleted_records = []

    async def execute(self, stmt):
        if "input_file_id" in str(stmt):
            self.task_queries += 1
            return _FakeRows([(i,) for i in self.linked_ids])
        self._file_queries += 1
        return _FakeRows(self.deleted if self._file_queries == 1 else self.orphaned)

    async def delete(self, obj):
        self.deleted_records.append(obj)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeSession:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc_info):
        return False


async def test_cleanup_issues_one_batch_task_query(upload_root, monkeypatch):
    orphaned = [
        _FakeFile(1, str(upload_root / "missing-1.txt")),
        _FakeFile(2, str(upload_root / "missing-2.txt")),
        _FakeFile(3, str(upload_root / "missing-3.txt")),
    ]
    db = _FakeDb(deleted=[], orphaned=orphaned, linked_ids={2})
    monkeypatch.setattr(scheduler, "async_session", lambda: _FakeSession(db))

    await scheduler.cleanup_files_task()

    # 三个孤立文件只需一次关联查询；原实现逐文件查询会得到 3
    assert db.task_queries == 1
    # 仅删除无关联任务的文件（1 与 3），保留被引用的 2
    assert sorted(record.id for record in db.deleted_records) == [1, 3]


async def test_physical_delete_failure_keeps_record(upload_root, monkeypatch):
    """物理删除失败时必须保留数据库记录，避免磁盘残留失去索引。"""
    taken = _FakeFile(7, str(upload_root / "locked.txt"))
    db = _FakeDb(deleted=[taken], orphaned=[], linked_ids=set())
    monkeypatch.setattr(scheduler, "async_session", lambda: _FakeSession(db))
    monkeypatch.setattr(scheduler, "_delete_managed_path", lambda path: False)

    await scheduler.cleanup_files_task()

    assert db.deleted_records == []


async def test_orphan_delete_failure_keeps_record(upload_root, monkeypatch):
    orphan = _FakeFile(9, str(upload_root / "locked-orphan.txt"))
    db = _FakeDb(deleted=[], orphaned=[orphan], linked_ids=set())
    monkeypatch.setattr(scheduler, "async_session", lambda: _FakeSession(db))
    monkeypatch.setattr(scheduler, "_delete_managed_path", lambda path: False)

    await scheduler.cleanup_files_task()

    assert db.deleted_records == []
