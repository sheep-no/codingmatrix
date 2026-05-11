# projects/orchestrator/20260503_083118_1/main.py

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 定义应用生命周期钩子
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动中... 初始化资源")
    # 这里可以添加初始化数据库、加载配置等操作
    yield
    logger.info("应用关闭... 释放资源")
    # 这里可以添加清理资源、关闭数据库连接等操作

# 创建FastAPI应用实例
app = FastAPI(lifespan=lifespan, title="增量生成服务", version="0.1.0")

# 健康检查端点
@app.get("/")
async def root():
    """
    根路径接口，用于验证服务是否运行
    返回状态信息和当前时间
    """
    return JSONResponse(content={"status": "running", "message": "增量生成服务已启动"})

# 异常处理中间件
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理中间件
    捕获所有未处理的异常并返回统一格式的错误响应
    """
    logger.error(f"发生未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "服务器内部错误", "message": str(exc), "type": "unknown"}
    )

# 主启动函数
def main():
    """
    主启动函数
    启动FastAPI应用并配置服务器参数
    """
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False,
            workers=1
        )
    except Exception as e:
        logger.error(f"启动服务器时发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()