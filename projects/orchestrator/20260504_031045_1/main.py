# main.py
# 主程序入口文件，启动FastAPI应用并定义基础路由

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import logging
import sys

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建FastAPI应用实例
app = FastAPI(title="Incremental Generation Orchestrator", version="0.1.0")

# 示例：模拟增量生成的健康检查端点
@app.get("/health")
async def health_check():
    """
    健康检查端点，验证服务是否正常运行。
    返回状态码200和基本服务信息。
    """
    try:
        # 模拟简单的服务状态验证
        return JSONResponse(
            content={"status": "healthy", "message": "Orchestrator service is running"},
            status_code=200
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Service health check failed")

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(exc: Exception):
    """
    全局异常处理器，捕获所有未处理的异常。
    返回统一格式的错误响应。
    """
    logger.error(f"Uncaught exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        content={
            "error": "Internal server error",
            "message": str(exc),
            "status_code": 500
        },
        status_code=500
    )

# 示例：模拟增量生成的测试端点
@app.get("/test-incremental")
async def test_incremental_generation():
    """
    测试增量生成功能的端点。
    模拟返回分页数据或增量处理结果。
    """
    try:
        # 模拟分页数据
        page = 1
        page_size = 10
        
        # 返回示例数据（实际应替换为真实业务逻辑）
        return {
            "page": page,
            "page_size": page_size,
            "total_items": 100,
            "data": [{"id": i, "value": f"item_{i}"} for i in range(page_size)]
        }
    except Exception as e:
        logger.error(f"Test endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail="Test incremental generation failed")

# 主程序入口
if __name__ == "__main__":
    try:
        # 启动FastAPI应用
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        logger.critical(f"Failed to start orchestrator service: {str(e)}")
        sys.exit(1)