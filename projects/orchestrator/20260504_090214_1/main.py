import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class OperationRequest(BaseModel):
    operation: str
    num1: float
    num2: float

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Calculator API"}

@app.post("/calculate")
async def calculate(request: OperationRequest):
    """
    Perform a mathematical operation on two numbers.
    
    Args:
        operation (str): The operation to perform. Supported operations: "add", "subtract", "multiply", "divide"
        num1 (float): First number
        num2 (float): Second number
    
    Returns:
        dict: Result of the operation or error message if invalid operation or division by zero
        
    Raises:
        HTTP 400: If operation is invalid or division by zero occurs
    """
    try:
        if request.operation == "add":
            result = request.num1 + request.num2
        elif request.operation == "subtract":
            result = request.num1 - request.num2
        elif request.operation == "multiply":
            result = request.num1 * request.num2
        elif request.operation == "divide":
            if request.num2 == 0:
                return {"error": "Division by zero is not allowed"}
            result = request.num1 / request.num2
        else:
            return {"error": "Invalid operation specified"}
            
        return {"result": result}
    
    except ValueError:
        return {"error": "Invalid input values"}
    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)