from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class CalculationRequest(BaseModel):
    a: float
    b: float
    operation: str

@app.post("/calculate")
async def calculate(request: CalculationRequest):
    a = request.a
    b = request.b
    operation = request.operation.lower()
    
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
        raise HTTPException(status_code=400, detail="Invalid operation. Supported operations: add, subtract, multiply, divide")
    
    return {"result": result}