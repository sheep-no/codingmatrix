import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 创建FastAPI应用实例
app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定义简单的请求模型
class HelloRequest(BaseModel):
    name: str

# 根路由，返回欢迎信息
@app.get("/")
async def read_root():
    """返回欢迎信息"""
    return {"message": "Welcome to the FastAPI Hello World API!"}

# 获取hello信息
@app.get("/hello")
async def read_hello():
    """返回简单的hello信息"""
    return {"message": "Hello World!"}

# 带参数的hello路由
@app.get("/hello/{name}")
async def read_hello_name(name: str):
    """返回带名字的hello信息
    
    Args:
        name (str): 用户名
        
    Returns:
        dict: 包含hello信息的字典
    """
    return {"message": f"Hello, {name}!"}

# 接收JSON格式的hello请求
@app.post("/hello")
async def read_hello_json(request: HelloRequest):
    """接收JSON格式的hello请求
    
    Args:
        request (HelloRequest): 包含name字段的请求体
        
    Returns:
        dict: 包含hello信息的字典
    """
    return {"message": f"Hello, {request.name}!"}

# 错误处理测试路由
@app.get("/error")
async def trigger_error():
    """触发自定义错误"""
    raise ValueError("This is a test error")

# 运行服务器的入口点
if __name__ == "__main__":
    """主入口点，运行FastAPI应用
    
    使用uvicorn运行服务器，默认在localhost:8000
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Run FastAPI server')
    parser.add_argument('--host', type=str, default='localhost', 
                        help='Host to serve on')
    parser.add_argument('--port', type=int, default=8000, 
                        help='Port to serve on')
    
    args = parser.parse_args()
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=True,
        workers=1
    )