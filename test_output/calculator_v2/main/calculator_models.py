from pydantic import BaseModel
from typing import Optional


class AddRequest(BaseModel):
    """Pydantic model for addition request"""
    a: float
    b: float


class SubtractRequest(BaseModel):
    """Pydantic model for subtraction request"""
    a: float
    b: float


class MultiplyRequest(BaseModel):
    """Pydantic model for multiplication request"""
    a: float
    b: float


class DivideRequest(BaseModel):
    """Pydantic model for division request"""
    a: float
    b: float


class CalculationResponse(BaseModel):
    """Common response model for all calculator operations"""
    result: Optional[float] = None
    error: Optional[str] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class CalculatorRequest(BaseModel):
    """Base class for all calculator operations"""
    operation: str
    a: float
    b: float


class AddRequest(CalculatorRequest):
    """Pydantic model for addition request"""
    operation: str = "add"
    a: float
    b: float


class SubtractRequest(CalculatorRequest):
    """Pydantic model for subtraction request"""
    operation: str = "subtract"
    a: float
    b: float


class MultiplyRequest(CalculatorRequest):
    """Pydantic model for multiplication request"""
    operation: str = "multiply"
    a: float
    b: float


class DivideRequest(CalculatorRequest):
    """Pydantic model for division request"""
    operation: str = "divide"
    a: float
    b: float