from datetime import datetime

from pydantic import BaseModel
from typing import Optional, AsyncGenerator, Literal, List


class HistoryRequest(BaseModel):
    prompt_keyword: Optional[str] = None
    limit: int = 20
    offset: int = 0

class ConversationHistoryRequest(BaseModel):
    conversation_id: int
    last_history_id: Optional[int] = None
    limit: int = 20

class HistoryResponse(BaseModel):
    items: List[dict]
    total: int
    limit: int
    offset: int
