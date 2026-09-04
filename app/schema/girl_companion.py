"""Structured contracts for the GirlAI companion turn."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


EmotionLabel = Literal[
    "neutral",
    "happy",
    "sad",
    "anxious",
    "stressed",
    "tired",
    "angry",
    "overwhelmed",
    "focused",
]
IntentLabel = Literal[
    "unknown",
    "chat",
    "acknowledge",
    "task_planning",
    "task_execution",
    "task_review",
    "task_blocked",
    "rest_request",
    "help_request",
    "remember_preference",
]


class CompanionTurnRequest(BaseModel):
    """Request body for a structured companion turn."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    character_id: str = Field(default="gentle", min_length=1, max_length=128)
    turn_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.5)
    max_tokens: Optional[int] = Field(default=None, ge=50, le=1000)


class EmotionState(BaseModel):
    """Normalized emotion state returned by the companion pipeline."""

    label: EmotionLabel = "neutral"
    intensity: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_label: Optional[str] = Field(default=None, max_length=64)
    low_confidence: bool = False


class IntentState(BaseModel):
    """Normalized work intent returned by the companion pipeline."""

    label: IntentLabel = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_label: Optional[str] = Field(default=None, max_length=64)
    low_confidence: bool = False


class MemoryCandidate(BaseModel):
    """A memory suggestion awaiting explicit user confirmation."""

    id: Optional[str] = Field(default=None, max_length=36)
    key: str = Field(..., min_length=1, max_length=50)
    value: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="conversation", min_length=1, max_length=64)


class CompanionMemoryConfirmRequest(BaseModel):
    """User confirmation and optional revision for a memory candidate."""

    key: Optional[str] = Field(default=None, min_length=1, max_length=50)
    value: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    visibility: Literal["conversation_only", "companion_allowed"] = "companion_allowed"


class CompanionMemoryResponse(BaseModel):
    """User-owned memory record exposed by the management API."""

    id: str
    key: str
    value: str
    confidence: int = Field(ge=0, le=100)
    source: str
    status: Literal["candidate", "confirmed", "rejected", "deleted"]
    consent_source: Literal["user_confirmed", "imported", "system_derived"]
    visibility: Literal["conversation_only", "companion_allowed"]
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanionMemoryPage(BaseModel):
    """Paginated memory records for the authenticated user."""

    memories: List[CompanionMemoryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ToolRequest(BaseModel):
    """A proposed tool call before policy and authorization checks."""

    name: str = Field(..., min_length=1, max_length=128)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = Field(default=None, max_length=500)


class ModelContext(BaseModel):
    """Safe model execution metadata; credentials are excluded by contract."""

    current_model: Optional[str] = Field(default=None, max_length=256)
    classification_model: Optional[str] = Field(default=None, max_length=256)
    current_agent: Optional[str] = Field(default=None, max_length=128)
    calls: int = Field(default=0, ge=0)
    fallback_used: bool = False
    fallback_history: List[str] = Field(default_factory=list)


class CompanionTurn(BaseModel):
    """Versioned structured output for one GirlAI companion turn."""

    turn_id: Optional[str] = Field(default=None, max_length=128)
    conversation_id: Optional[str] = Field(default=None, max_length=128)
    assistant_text: str = Field(..., min_length=1, max_length=20000)
    emotion: EmotionState = Field(default_factory=EmotionState)
    intent: IntentState = Field(default_factory=IntentState)
    care_required: bool = False
    response_style: Literal["standard", "neutral", "care"] = "standard"
    work_options: List[str] = Field(default_factory=list, max_length=3)
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
    tool_requests: List[ToolRequest] = Field(default_factory=list)
    task_suggestion: Optional[Dict[str, Any]] = None
    model_context: ModelContext = Field(default_factory=ModelContext)
    degraded_capabilities: List[str] = Field(default_factory=list)
    schema_version: int = Field(default=1, ge=1)


class CompanionTurnResponse(CompanionTurn):
    """API response with persisted conversation state metadata."""

    model: str = Field(..., max_length=256)
    tokens_used: int = Field(default=0, ge=0)
    state_revision: int = Field(default=0, ge=0)
