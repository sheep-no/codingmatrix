# projects/orchestrator/20260503_084342_1/main.py
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import sys

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动中...")
    # 这里可以添加初始化代码，如数据库连接等
    yield
    logger.info("应用关闭...")

# 创建 FastAPI 应用实例
app = FastAPI(lifespan=lifespan)

# 根路由 - 测试增量生成的健康检查
@app.get("/")
def read_root():
    """
    根路由，返回应用健康状态
    示例响应: {"status": "healthy", "message": "Orchestrator service is running"}
    """
    return {
        "status": "healthy",
        "message": "Orchestrator service is running",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    try:
        logger.info("尝试启动服务...")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"服务启动失败: {str(e)}")
        sys.exit(1)