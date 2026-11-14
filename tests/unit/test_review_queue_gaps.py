"""review_queue 审查记录创建、审批与拒绝分支补测。"""

from unittest.mock import AsyncMock, MagicMock

from app.models.aicloud import AicloudReview
from app.utils.aicloud import review_queue


async def test_create_review_without_details():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    review = await review_queue.create_review(
        db, "read", "/sandbox/a.txt", None, 1, True
    )

    assert isinstance(review, AicloudReview)
    assert review.details is None
    assert review.status == "pending"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


async def test_create_review_serializes_details():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    review = await review_queue.create_review(
        db, "write", "/sandbox/a.txt", "content", 1, False, {"reason": "x"}
    )

    assert review.details == '{"reason": "x"}'
    assert review.ai_filter_passed is False


async def test_get_review_returns_scalar():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "review"
    db.execute.return_value = result
    assert await review_queue.get_review(db, "r1") == "review"


async def test_approve_review_missing_returns_none(monkeypatch):
    monkeypatch.setattr(review_queue, "get_review", AsyncMock(return_value=None))
    db = AsyncMock()
    assert await review_queue.approve_review(db, "r1", 1) is None
    db.commit.assert_not_awaited()


async def test_approve_review_updates_status(monkeypatch):
    review = MagicMock()
    monkeypatch.setattr(review_queue, "get_review", AsyncMock(return_value=review))
    db = AsyncMock()

    result = await review_queue.approve_review(db, "r1", 9)

    assert result is review
    assert review.status == "approved"
    assert review.reviewed_by == 9
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


async def test_reject_review_missing_returns_none(monkeypatch):
    monkeypatch.setattr(review_queue, "get_review", AsyncMock(return_value=None))
    db = AsyncMock()
    assert await review_queue.reject_review(db, "r1", 1) is None
    db.commit.assert_not_awaited()


async def test_reject_review_without_reason(monkeypatch):
    review = MagicMock()
    review.details = None
    monkeypatch.setattr(review_queue, "get_review", AsyncMock(return_value=review))
    db = AsyncMock()

    result = await review_queue.reject_review(db, "r1", 9)

    assert result is review
    assert review.status == "rejected"
    assert review.reviewed_by == 9
    db.commit.assert_awaited_once()


async def test_reject_review_records_reason(monkeypatch):
    review = MagicMock()
    review.details = '{"existing": 1}'
    monkeypatch.setattr(review_queue, "get_review", AsyncMock(return_value=review))
    db = AsyncMock()

    await review_queue.reject_review(db, "r1", 9, "unsafe")

    assert review.details == '{"existing": 1, "reject_reason": "unsafe"}'
