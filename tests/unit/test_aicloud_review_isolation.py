"""aicloud 审查队列用户隔离回归测试

覆盖已建档缺陷 RQ1：
- GET /reviews 未按 requested_by 过滤，泄露其他用户的待审内容
- approve/reject 不校验归属，可跨用户审批
- approve 直接用 open() 写 review.file_path，绕过沙箱路径校验
"""

import pytest
from fastapi import HTTPException

from app.api.v1 import aicloud as aicloud_api
from app.models.aicloud import AicloudReview
from app.schema.aicloud import ReviewActionRequest


@pytest.fixture(autouse=True)
async def _clean_reviews(test_db):
    from sqlalchemy import delete

    await test_db.execute(delete(AicloudReview))
    await test_db.commit()
    yield


async def _allow(*args, **kwargs):
    return True


def _review(review_id: str, requested_by: int, file_path: str = "/sandbox/1/workspace/a.txt"):
    return AicloudReview(
        id=review_id,
        operation_type="write",
        file_path=file_path,
        content="hello",
        status="pending",
        requested_by=requested_by,
        ai_filter_passed=True,
    )


async def test_get_reviews_only_returns_own(monkeypatch, test_db):
    """RQ1：审查列表只返回当前用户自己的记录。"""
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)
    test_db.add_all([_review("r1", requested_by=1), _review("r2", requested_by=2)])
    await test_db.commit()

    reviews = await aicloud_api.get_reviews(status_filter="pending", db=test_db, user_id=1)

    assert [review.id for review in reviews] == ["r1"]


async def test_approve_rejects_other_users_review(monkeypatch, test_db):
    """RQ1：不能审批他人的审查记录。"""
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)
    test_db.add(_review("r2", requested_by=2))
    await test_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await aicloud_api.approve_review_endpoint(
            ReviewActionRequest(review_id="r2"), db=test_db, user_id=1
        )

    assert exc_info.value.status_code == 403


async def test_reject_rejects_other_users_review(monkeypatch, test_db):
    """RQ1：不能拒绝他人的审查记录。"""
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)
    test_db.add(_review("r2", requested_by=2))
    await test_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await aicloud_api.reject_review_endpoint(
            ReviewActionRequest(review_id="r2"), db=test_db, user_id=1
        )

    assert exc_info.value.status_code == 403


async def test_approve_writes_own_review_through_sandbox(monkeypatch, test_db, tmp_path):
    """RQ1：审批通过后经沙箱文件操作器落盘。"""
    from app.utils.aicloud.sandbox_operator import SandboxFileOperator

    monkeypatch.setattr(SandboxFileOperator, "SANDBOX_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    target = tmp_path / "1" / "workspace" / "a.txt"
    test_db.add(_review("r1", requested_by=1, file_path=str(target)))
    await test_db.commit()

    result = await aicloud_api.approve_review_endpoint(
        ReviewActionRequest(review_id="r1"), db=test_db, user_id=1
    )

    assert result["status"] == "approved"
    assert target.read_text(encoding="utf-8") == "hello"


async def test_approve_rejects_review_path_outside_sandbox(monkeypatch, test_db, tmp_path):
    """RQ1：被篡改到沙箱外的 file_path 必须被拒绝。"""
    from app.utils.aicloud.sandbox_operator import SandboxFileOperator

    monkeypatch.setattr(SandboxFileOperator, "SANDBOX_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    outside = tmp_path.parent / "outside.txt"
    test_db.add(_review("r1", requested_by=1, file_path=str(outside)))
    await test_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await aicloud_api.approve_review_endpoint(
            ReviewActionRequest(review_id="r1"), db=test_db, user_id=1
        )

    assert exc_info.value.status_code == 403
    assert not outside.exists()
