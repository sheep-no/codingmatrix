from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class OperationRequest(BaseModel):
    a: float
    b: float

@app.get("/")
async def read_root():
    return {"message": "Welcome to the FastAPI Calculator"}

@app.post("/add")
async def add(request: OperationRequest):
    """Add two numbers"""
    result = request.a + request.b
    return {"result": result}

@app.post("/subtract")
async def subtract(request: OperationRequest):
    """Subtract two numbers"""
    result = request.a - request.b
    return {"result": result}

@app.post("/multiply")
async def multiply(request: OperationRequest):
    """Multiply two numbers"""
    result = request.a * request.b
    return {"result": result}

@app.post("/divide")
async def divide(request: OperationRequest):
    """Divide two numbers"""
    if request.b == 0:
        raise HTTPException(status_code=400, detail="Division by zero")
    result = request.a / request.b
    return {"result": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)