"""AI 绘图历史 API 全分支回归：分页、详情、单删与清空。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import kolors_history as kh
from app.db.models import ImageGenerationHistory


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []
        self.deleted = []
        self.commits = 0

    async def execute(self, statement):
        self.executed.append(statement)
        return _ScalarResult(self._results.pop(0))

    async def delete(self, record):
        self.deleted.append(record)

    async def commit(self):
        self.commits += 1


def _record(image_id="img-1", user_id="u1", urls=None):
    return ImageGenerationHistory(
        image_id=image_id,
        user_id=user_id,
        prompt="p",
        image_urls=urls or [],
    )


@pytest.mark.asyncio
async def test_get_history_returns_page_payload():
    records = [_record("a"), _record("b")]
    db = _FakeDB([2, records])
    payload = await kh.get_image_history(
        token={"sub": "u1"}, db=db, page=2, page_size=1
    )
    assert payload["total"] == 2
    assert payload["page"] == 2
    assert payload["page_size"] == 1
    assert [item["image_id"] for item in payload["items"]] == ["a", "b"]
    assert db.commits == 0


@pytest.mark.asyncio
async def test_get_history_falls_back_to_user_id_and_zero_total():
    db = _FakeDB([None, []])
    payload = await kh.get_image_history(token={"user_id": "u2"}, db=db, page=1, page_size=20)
    assert payload["total"] == 0
    assert payload["items"] == []


@pytest.mark.asyncio
async def test_get_history_detail_found_and_missing():
    record = _record()
    payload = await kh.get_image_history_detail(
        image_id="img-1", token={"sub": "u1"}, db=_FakeDB([record])
    )
    assert payload["image_id"] == "img-1"

    with pytest.raises(HTTPException) as exc:
        await kh.get_image_history_detail(
            image_id="missing", token={"sub": "u1"}, db=_FakeDB([None])
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_history_removes_record_and_commits(monkeypatch):
    record = _record(urls=["a.png"])
    db = _FakeDB([record])
    calls = []
    monkeypatch.setattr(kh, "_delete_image_files", lambda urls: calls.append(urls))

    payload = await kh.delete_image_history(
        image_id="img-1", token={"user_id": "u1"}, db=db
    )
    assert payload["status"] == "deleted"
    assert calls == [["a.png"]]
    assert db.deleted == [record]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_history_missing_raises_404(monkeypatch):
    called = []
    monkeypatch.setattr(kh, "_delete_image_files", lambda urls: called.append(urls))
    with pytest.raises(HTTPException) as exc:
        await kh.delete_image_history(
            image_id="missing", token={"sub": "u1"}, db=_FakeDB([None])
        )
    assert exc.value.status_code == 404
    assert called == []


@pytest.mark.asyncio
async def test_delete_all_with_records(monkeypatch):
    records = [_record("a", urls=["a.png"]), _record("b", urls=["b.png"])]
    db = _FakeDB([records, None])
    calls = []
    monkeypatch.setattr(kh, "_delete_image_files", lambda urls: calls.append(urls))

    payload = await kh.delete_all_image_history(token={"sub": "u1"}, db=db)
    assert payload["deleted_count"] == 2
    assert calls == [["a.png"], ["b.png"]]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_all_without_records_skips_delete(monkeypatch):
    db = _FakeDB([[]])
    called = []
    monkeypatch.setattr(kh, "_delete_image_files", lambda urls: called.append(urls))

    payload = await kh.delete_all_image_history(token={"user_id": "u1"}, db=db)
    assert payload["deleted_count"] == 0
    assert called == []
    assert db.commits == 0


def test_delete_image_files_removes_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(kh, "OUTPUT_DIR", tmp_path)
    target = tmp_path / "keep.png"
    target.write_bytes(b"x")

    kh._delete_image_files(["keep.png", None, "https://remote/x.png", "evil/../../x.png"])
    assert not target.exists()


def test_delete_image_files_skips_missing_and_logs_oserror(tmp_path, monkeypatch):
    monkeypatch.setattr(kh, "OUTPUT_DIR", tmp_path)
    kh._delete_image_files(["missing.png", "data:image/png;base64,xxx"])

    warnings = []
    monkeypatch.setattr(
        kh.logger, "warning", lambda message, *a, **k: warnings.append(message)
    )

    class _BrokenPath:
        def exists(self):
            raise OSError("nope")

    monkeypatch.setattr(kh, "resolve_reference", lambda url, root: _BrokenPath())
    kh._delete_image_files(["boom.png"])
    assert any("删除图片文件失败" in w for w in warnings)


def test_delete_image_files_handles_none_and_non_list():
    kh._delete_image_files(None)
    kh._delete_image_files([])
