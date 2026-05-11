from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# 创建计算器路由
router = APIRouter(prefix="/calculator", tags=["calculator"])

class AddRequest(BaseModel):
    a: float
    b: float

class SubtractRequest(BaseModel):
    a: float
    b: float

class MultiplyRequest(BaseModel):
    a: float
    b: float

class DivideRequest(BaseModel):
    a: float
    b: float

# 加法端点
@router.post("/add")
async def add(request: AddRequest):
    """
    加法计算端点
    """
    try:
        result = request.a + request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 减法端点
@router.post("/subtract")
async def subtract(request: SubtractRequest):
    """
    减法计算端点
    """
    try:
        result = request.a - request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 乘法端点
@router.post("/multiply")
async def multiply(request: MultiplyRequest):
    """
    乘法计算端点
    """
    try:
        result = request.a * request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 除法端点
@router.post("/divide")
async def divide(request: DivideRequest):
    """
    除法计算端点，处理除零错误
    """
    try:
        if request.b == 0:
            raise HTTPException(status_code=400, detail="Division by zero is not allowed")
        result = request.a / request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))