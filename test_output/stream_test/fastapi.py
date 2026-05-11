from fastapi import FastAPI
from typing import Optional, Dict, Any

# 创建FastAPI应用实例
app = FastAPI()

# 定义根路由，返回欢迎信息
@app.get("/")
async def root() -> Dict[str, str]:
    """返回API的欢迎消息"""
    return {"message": "欢迎使用FastAPI示例API"}

# 定义一个简单的问候API，接受name参数
@app.get("/hello/{name}")
async def hello(name: str, age: Optional[int] = None) -> Dict[str, Any]:
    """返回问候消息，可选的年龄信息"""
    message = f"Hello, {name}!"
    
    if age is not None:
        message += f" You are {age} years old."
    
    return {
        "status": "success",
        "message": message,
        "api_version": "1.0.0"
    }

# 定义一个POST端点示例
@app.post("/items/")
async def create_item(name: str, quantity: int = 1) -> Dict[str, str]:
    """创建项目，返回确认消息"""
    return {"item_name": name, "quantity": quantity, "message": "Item created"}

# 定义一个简单的异常处理中间件
@app.exception_handler(Exception)
async def global_exception_handler(request, exc) -> Dict[str, str]:
    """全局异常处理"""
    return {
        "status": "error",
        "message": f"服务器内部错误: {str(exc)}",
        "request": f"{request.method} {request.url}",
        "time": import time
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return {"status": "error", "message": f"服务器内部错误: {str(exc)}", "timestamp": current_time}
    }

# 定义API文档自定义信息
@app.get("/docs")
async def custom_docs() -> Dict[str, str]:
    """自定义文档端点"""
    return {
        "api_info": "这是一个简单的FastAPI示例",
        "author": "FastAPI团队",
        "version": "1.0.0",
        "description": "演示FastAPI的基本路由和异常处理"
    }

# 定义API元数据
@app.get("/meta")
async def api_meta() -> Dict[str, str]:
    """API元数据信息"""
    import sys
    return {
        "framework": "FastAPI",
        "python_version": sys.version.split()[0],
        "server": "uvicorn",
        "status": "running"
    }