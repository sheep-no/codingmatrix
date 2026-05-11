from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

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

@app.post("/add")
async def add(request: AddRequest):
    try:
        result = request.a + request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred: {str(e)}"
        )

@app.post("/subtract")
async def subtract(request: SubtractRequest):
    try:
        result = request.a - request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred: {str(e)}"
        )

@app.post("/multiply")
async def multiply(request: MultiplyRequest):
    try:
        result = request.a * request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred: {str(e)}"
        )

@app.post("/divide")
async def divide(request: DivideRequest):
    try:
        if request.b == 0:
            raise HTTPException(
                status_code=400,
                detail="Division by zero is not allowed"
            )
        result = request.a / request.b
        return {"result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)