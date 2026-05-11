from pydantic import BaseModel
from typing import Optional

class CalculatorRequest(BaseModel):
    num1: float
    num2: float
    operation: str

class CalculatorResponse(BaseModel):
    result: Optional[float] = None
    error: Optional[str] = None