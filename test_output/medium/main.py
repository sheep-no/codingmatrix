from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class OperationRequest(BaseModel):
    a: float
    b: float
    operation: str

class OperationResponse(BaseModel):
    result: Optional[float] = None

@app.post("/calculate/", response_model=OperationResponse)
async def calculate(request: OperationRequest):
    operation = request.operation.lower()
    a = request.a
    b = request.b
    
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise HTTPException(status_code=400, detail="Division by zero")
        result = a / b
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid operation. Supported operations: add, subtract, multiply, divide"
        )
        
    return {"result": round(result, 2)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)