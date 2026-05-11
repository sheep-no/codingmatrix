# projects/orchestrator/20260502_100451_1/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
import logging
import sys

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，用于初始化资源"""
    logging.info("Starting up application")
    # 这里可以添加初始化数据库连接等操作
    yield
    logging.info("Shutting down application")

# 创建FastAPI应用实例
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    """
    根路由
    返回简单的欢迎信息
    """
    try:
        return JSONResponse(content={"message": "Welcome to the Concurrent API!"})
    except Exception as e:
        logging.error(f"Error in root endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/concurrent")
async def concurrent_endpoint():
    """
    并发测试端点
    模拟高并发场景下的处理逻辑
    """
    try:
        # 模拟并发处理的业务逻辑
        return JSONResponse(content={"status": "Processing concurrent request", "concurrent": True})
    except Exception as e:
        logging.error(f"Error in concurrent endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Concurrent processing error")

if __name__ == "__main__":
    """
    主启动入口
    使用uvicorn运行FastAPI应用
    支持并发处理，通过workers参数配置并发数量
    """
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False,
            workers=4  # 配置并发工作进程数量
        )
    except Exception as e:
        logging.critical(f"Failed to start application: {str(e)}")
        sys.exit(1)