"""PPT outline contracts used by the outline review workflow."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ContentBlock(BaseModel):
    """A single editable content block on a slide."""

    type: str = Field(default="text", min_length=1, max_length=40)
    content: str = Field(default="", max_length=5000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetIntent(BaseModel):
    """Optional description of visual material requested by a slide."""

    description: str = Field(default="", max_length=1000)
    keywords: List[str] = Field(default_factory=list, max_length=12)
    asset_type: str = Field(default="none", min_length=1, max_length=40)


class OutlineSlide(BaseModel):
    """Editable semantic slide outline."""

    id: str = Field(..., min_length=1, max_length=80)
    position: int = Field(..., ge=0)
    slide_type: str = Field(default="key_points", min_length=1, max_length=40)
    narrative_role: str = Field(default="opportunity_map", min_length=1, max_length=40)
    evidence_sources: List[Dict[str, Any]] = Field(default_factory=list, max_length=6)
    title: str = Field(default="", max_length=300)
    key_message: str = Field(default="", max_length=1000)
    content_blocks: List[ContentBlock] = Field(default_factory=list, max_length=24)
    asset_intent: Optional[AssetIntent] = None
    speaker_notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def require_content(self) -> "OutlineSlide":
        if not self.content_blocks and not self.asset_intent:
            raise ValueError("页面必须包含内容块或素材意图")
        return self


class OutlineDraft(BaseModel):
    """Versioned outline draft returned to the client."""

    id: str
    user_id: str
    version: int = Field(..., ge=1)
    status: str = Field(default="draft", pattern="^(draft|approved)$")
    title: str = Field(..., min_length=1, max_length=300)
    scenario: str = Field(default="general", min_length=1, max_length=40)
    template_id: str = Field(default="modern", min_length=1, max_length=80)
    slide_limit: int = Field(..., ge=1, le=50)
    slides: List[OutlineSlide] = Field(..., max_length=49)
    created_at: str
    approved_at: Optional[str] = None


class OutlineCreateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=5000)
    description: str = Field(default="", max_length=5000)
    num_slides: int = Field(default=10, ge=1, le=50)
    scenario: Optional[Literal[
        "business", "data_report", "product_pitch", "academic", "education", "general"
    ]] = None
    template_id: str = Field(default="modern", min_length=1, max_length=80)
    model: str = Field(default="", max_length=200)
    api_key_token: Optional[str] = None
    material_file_ids: List[int] = Field(default_factory=list, max_length=50)


class OutlineUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    scenario: Optional[str] = Field(default=None, min_length=1, max_length=40)
    template_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    slides: Optional[List[OutlineSlide]] = Field(default=None, max_length=49)


class OutlineGenerateRequest(BaseModel):
    quality_mode: str = Field(default="standard", pattern="^(standard|refined)$")
    outline_version: Optional[int] = Field(default=None, ge=1)


class SlideRegenerateRequest(BaseModel):
    quality_mode: str = Field(default="standard", pattern="^(standard|refined)$")
    slide: Optional[OutlineSlide] = None
