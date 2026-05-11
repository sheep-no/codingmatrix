from pydantic import BaseModel
from typing import Optional

class OperationHistory(BaseModel):
    id: Optional[int] = None
    operation: str
    operand1: float
    operand2: float
    result: float
    timestamp: str

class CalculatorRequest(BaseModel):
    operation1: float
    operation2: float
    operator: str

class CalculatorResponse(BaseModel):
    result: float
    history: OperationHistory

class ErrorDetails(BaseModel):
    error: str
    details: Optional[str] = None