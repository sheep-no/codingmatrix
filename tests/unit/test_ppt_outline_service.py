from app.schema.ppt_outline import ContentBlock, OutlineCreateRequest, OutlineUpdateRequest
from app.services.ppt_outline_service import PPTOutlineService, OutlineValidationError


def _request():
    return OutlineCreateRequest(topic="季度业务汇报", num_slides=2)


def test_create_returns_version_one_draft_with_editable_slides():
    draft = PPTOutlineService().create("user-1", _request())

    assert draft.version == 1
    assert draft.status == "draft"
    assert [slide.position for slide in draft.slides] == [0, 1]
    assert draft.slides[0].content_blocks[0].content


def test_outline_slide_accepts_narrative_role():
    draft = PPTOutlineService().create("user-1", OutlineCreateRequest(topic="季度业务汇报", num_slides=2))

    assert draft.slides[0].narrative_role == "opportunity_map"


def test_default_outline_contains_role_specific_commercial_metadata():
    draft = PPTOutlineService().create(
        "user-1", OutlineCreateRequest(topic="季度业务汇报", num_slides=5)
    )

    assert draft.slides[0].content_blocks[3].metadata == {
        "roi": "≥3.0",
        "priority": "P0",
        "validation_period": "2 周",
    }
    assert draft.slides[2].content_blocks[0].metadata["risk"] == "需求扩散"
    assert draft.slides[3].content_blocks[0].metadata["deliverable"] == "试点闭环"
    assert draft.slides[4].content_blocks[1].metadata["owner"] == "项目负责人"


def test_default_outline_cycles_distinct_roles_for_long_decks():
    draft = PPTOutlineService().create(
        "user-1", OutlineCreateRequest(topic="季度业务汇报", num_slides=7)
    )

    assert [slide.narrative_role for slide in draft.slides] == [
        "opportunity_map",
        "evidence_story",
        "strategic_choice",
        "execution_roadmap",
        "decision_close",
        "opportunity_map",
        "evidence_story",
    ]


def test_update_creates_new_unapproved_version():
    service = PPTOutlineService()
    draft = service.create("user-1", _request())

    updated = service.update(
        "user-1",
        draft.id,
        OutlineUpdateRequest(
            title="更新后的汇报",
            slides=[
                draft.slides[0].model_copy(
                    update={"content_blocks": [ContentBlock(content="新的内容")]} 
                ),
            ],
        ),
    )

    assert updated.version == 2
    assert updated.status == "draft"
    assert service.get("user-1", draft.id, version=1).status == "draft"


def test_approve_locks_current_version():
    service = PPTOutlineService()
    draft = service.create("user-1", _request())

    approved = service.approve("user-1", draft.id)

    assert approved.status == "approved"
    assert approved.approved_at
    assert service.get("user-1", draft.id).status == "approved"


def test_approve_rejects_incomplete_slide():
    service = PPTOutlineService()
    draft = service.create("user-1", _request())
    service.update(
        "user-1",
        draft.id,
        OutlineUpdateRequest(
            slides=[draft.slides[0].model_copy(update={"key_message": ""})]
        ),
    )

    try:
        service.approve("user-1", draft.id)
    except OutlineValidationError as exc:
        assert exc.slide_ids == ["slide-1"]
    else:
        raise AssertionError("不完整大纲应该无法批准")


def test_user_cannot_read_another_users_outline():
    service = PPTOutlineService()
    draft = service.create("user-1", _request())

    try:
        service.get("user-2", draft.id)
    except KeyError:
        pass
    else:
        raise AssertionError("跨用户读取应该被拒绝")
