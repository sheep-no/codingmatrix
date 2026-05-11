from fastapi import APIRouter, HTTPException

# 创建路由对象
router = APIRouter(prefix="/api/v1")

# 计算器路由
@router.get("/calculator/{operation}")
async def calculator(num1: float, num2: float, operation: str):
    """
    简单计算器API，支持基本的加减乘除运算
    
    Args:
        num1 (float): 第一个数字
        num2 (float): 第二个数字
        operation (str): 操作类型，支持 'add', 'subtract', 'multiply', 'divide'
    
    Returns:
        dict: 包含计算结果和操作信息
        
    Raises:
        HTTPException: 当除法时除数为零，或操作不支持时
    """
    try:
        if operation == "add":
            result = num1 + num2
        elif operation == "subtract":
            result = num1 - num2
        elif operation == "multiply":
            result = num1 * num2
        elif operation == "divide":
            if num2 == 0:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot divide by zero"
                )
            result = num1 / num2
        else:
            raise HTTPException(
                status_code=400, 
                detail="Unsupported operation"
            )
            
        return {
            "operation": operation,
            "result": result,
            "details": f"{num1} {operation} {num2} = {result}"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=str(e)
        )

# 将计算器路由添加到路由组
def get_routes():
    """返回所有API路由"""
    return [
        ("/api/v1/calculator/{operation}", "GET")
    ]