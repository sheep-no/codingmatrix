from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from typing import Optional, AsyncGenerator, Literal, List


class HistoryRequest(BaseModel):
    prompt_keyword: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class ConversationHistoryRequest(BaseModel):
    conversation_id: int
    last_history_id: Optional[int] = None
    limit: int = 20

    @field_validator('conversation_id', mode='before')
    @classmethod
    def coerce_conversation_id(cls, v):
        if isinstance(v, str):
            try:
                return int(v)
            except (ValueError, TypeError):
                pass
        return v

class HistoryResponse(BaseModel):
    items: List[dict]
    total: int
    limit: int
    offset: int
