from datetime import datetime

from pydantic import BaseModel, field_validator
from typing import Optional, AsyncGenerator, Literal, List


class HistoryRequest(BaseModel):
    prompt_keyword: Optional[str] = None
    limit: int = 20
    offset: int = 0

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
