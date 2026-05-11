# hello_world_project/main.py
import uvicorn
from fastapi import FastAPI
from typing import Dict, Any
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base

# 定义数据库模型（未实际使用，但按架构设计保留）
Base = declarative_base()

class HelloMessage(Base):
    """数据库模型定义（用于示例，未实际操作数据库）"""
    __tablename__ = 'hello_messages'
    id = Column(Integer, primary_key=True)
    message = Column(String, nullable=False)

# 创建FastAPI应用
app = FastAPI(description="简单问候语服务")

@app.get("/api/v1/hello")
def get_hello() -> Dict[str, Any]:
    """
    GET接口：获取Hello World响应
    
    返回:
        包含问候语的JSON响应
    """
    try:
        return {"message": "Hello, World!"}
    except Exception as e:
        # 捕获并返回任何可能发生的异常
        return {"error": str(e)}

# 主程序入口
if __name__ == "__main__":
    """
    启动FastAPI服务
    
    默认配置:
        - 主机: 0.0.0.0
        - 端口: 8000
        - 无需额外参数启动
    """
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"服务启动失败: {str(e)}")