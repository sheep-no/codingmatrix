"""Versioned PPT outline workflow.

The store is intentionally isolated behind this service so database persistence
can be added without changing the HTTP contract or outline validation rules.
"""

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List, Optional
from uuid import uuid4

from app.schema.ppt_outline import (
    ContentBlock,
    OutlineCreateRequest,
    OutlineDraft,
    OutlineSlide,
    OutlineUpdateRequest,
)
from app.utils.pptx.commercial_content import build_commercial_page_blueprint
from app.utils.pptx.scenario import classify_scenario


class OutlineValidationError(ValueError):
    """Raised when an outline cannot be approved."""

    def __init__(self, message: str, slide_ids: Optional[List[str]] = None):
        super().__init__(message)
        self.slide_ids = slide_ids or []


class PPTOutlineService:
    """Manage user-scoped outline drafts and immutable approved versions."""

    def __init__(self) -> None:
        self._drafts: Dict[str, List[OutlineDraft]] = {}
        self._lock = RLock()

    def create(self, user_id: str, request: OutlineCreateRequest) -> OutlineDraft:
        now = datetime.now(timezone.utc).isoformat()
        topic = request.topic.strip()
        page_blueprint = build_commercial_page_blueprint(topic)
        slides = [
            OutlineSlide(
                id=f"slide-{index + 1}",
                position=index,
                title=page_blueprint[index % len(page_blueprint)]["title"],
                key_message=page_blueprint[index % len(page_blueprint)]["key_message"],
                slide_type=page_blueprint[index % len(page_blueprint)]["slide_type"],
                narrative_role=page_blueprint[index % len(page_blueprint)]["role"],
                content_blocks=[ContentBlock.model_validate(block) for block in page_blueprint[index % len(page_blueprint)]["blocks"]],
                asset_intent=page_blueprint[index % len(page_blueprint)]["asset_intent"],
            )
            for index in range(max(0, request.num_slides - 1))
        ]
        draft = OutlineDraft(
            id=str(uuid4()),
            user_id=str(user_id),
            version=1,
            title=topic,
            scenario=request.scenario or classify_scenario(f"{topic} {request.description}").scenario,
            template_id=request.template_id,
            slide_limit=request.num_slides,
            slides=slides,
            created_at=now,
        )
        with self._lock:
            self._drafts[draft.id] = [draft]
        return deepcopy(draft)

    def get(self, user_id: str, outline_id: str, version: Optional[int] = None) -> OutlineDraft:
        with self._lock:
            versions = self._drafts.get(outline_id, [])
            if not versions or versions[0].user_id != str(user_id):
                raise KeyError(outline_id)
            if version is None:
                return deepcopy(versions[-1])
            for draft in versions:
                if draft.version == version:
                    return deepcopy(draft)
        raise KeyError(f"{outline_id}:{version}")

    def update(self, user_id: str, outline_id: str, request: OutlineUpdateRequest) -> OutlineDraft:
        current = self.get(user_id, outline_id)
        changes = request.model_dump(exclude_unset=True)
        next_data = current.model_dump()
        next_data.update(changes)
        next_data["version"] = current.version + 1
        next_data["status"] = "draft"
        next_data["approved_at"] = None
        updated = OutlineDraft(**next_data)
        with self._lock:
            self._drafts[outline_id].append(updated)
        return deepcopy(updated)

    def approve(self, user_id: str, outline_id: str) -> OutlineDraft:
        current = self.get(user_id, outline_id)
        invalid_slides = [
            slide.id
            for slide in current.slides
            if not slide.title.strip()
            or not slide.key_message.strip()
            or not slide.content_blocks and not slide.asset_intent
        ]
        if invalid_slides:
            raise OutlineValidationError("大纲包含未完成页面", invalid_slides)

        approved = current.model_copy(
            update={
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        with self._lock:
            self._drafts[outline_id][-1] = approved
        return deepcopy(approved)

    def list_versions(self, user_id: str, outline_id: str) -> List[OutlineDraft]:
        self.get(user_id, outline_id)
        with self._lock:
            return deepcopy(self._drafts[outline_id])


ppt_outline_service = PPTOutlineService()
