import logging
import time
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import Response

logger = logging.getLogger("apimiddleware")
logger.setLevel(logging.INFO)


class APIRequestMiddleware:
    """API请求响应中间件，用于处理请求和响应的通用逻辑。

    功能包括：
    - 请求计时
    - 请求参数记录
    - 响应处理
    - 错误处理
    - 请求验证
    """

    def __init__(self) -> None:
        """初始化中间件"""
        self.request_start_time: Optional[float] = None
        self.route_path: Optional[str] = None
        self.error_occurred: bool = False
        self.error_message: Optional[str] = None

    def __call__(
        self, app: Any, scope: Any, receive: Any, send: Any
    ) -> Callable[..., None]:
        """中间件调用方法

        Args:
            app: FastAPI应用实例
            scope: 请求作用域
            receive: 接收请求数据的异步方法
            send: 发送响应数据的异步方法

        Returns:
            Callable: 请求处理完成后的回调函数
        """
        async def handle(request: Request) -> None:
            """请求处理函数

            Args:
                request: FastAPI请求对象

            Returns:
                None
            """
            # 记录请求开始时间
            self.request_start_time = time.time()
            self.route_path = request.url.path
            self.error_occurred = False

            # 记录请求信息
            self.log_request(request)

            # 处理请求
            try:
                # 在这里可以添加请求验证、身份验证等逻辑
                await request.body()  # 确保请求体已读取
                
                # 调用原应用的send方法
                await send(request)
                
                # 记录响应信息
                self.log_response(request)
                
            except Exception as e:
                self.error_occurred = True
                self.error_message = str(e)
                logger.error(f"Request processing error: {e}")
                raise e

        return handle

    def log_request(self, request: Request) -> None:
        """记录请求信息

        Args:
            request: FastAPI请求对象

        Returns:
            None
        """
        if self.request_start_time is None:
            self.request_start_time = time.time()

        request_info = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "method": request.method,
            "path": self.route_path,
            "client": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown"),
        }
        
        logger.info(f"Incoming request: {request_info}")

    def log_response(self, request: Request) -> None:
        """记录响应信息

        Args:
            request: FastAPI请求对象

        Returns:
            None
        """
        if self.request_start_time is not None:
            process_time = time.time() - self.request_start_time
            
            response_info = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "method": request.method,
                "path": self.route_path,
                "process_time_ms": round(process_time * 1000, 2),
                "status": "OK" if not self.error_occurred else "ERROR",
                "error": self.error_message if self.error_occurred else None,
            }
            
            if self.error_occurred:
                logger.error(f"Request processing error: {self.error_message}")
            else:
                logger.info(f"Request processed: {response_info}")

    def handle_error(self, request: Request, error: Exception) -> None:
        """全局错误处理

        Args:
            request: FastAPI请求对象
            error: 发生的异常

        Returns:
            None
        """
        self.error_occurred = True
        self.error_message = str(error)
        logger.error(f"Error in request {request.url.path}: {error}")
        
        # 在实际应用中，这里可以添加自定义错误处理逻辑
        # 例如返回特定的错误响应或记录到数据库


# 示例用法（在main.py或fastapi.py中注册中间件）
if __name__ == "__main__":
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()

    # 允许跨域请求
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册API中间件
    middleware = APIRequestMiddleware()
    app.middleware("http").add(middleware)

    @app.get("/")
    async def read_root():
        """示例API端点"""
        return {"message": "Hello World", "status": "success"}

    @app.get("/items/{item_id}")
    async def read_item(item_id: int, q: Optional[str] = None):
        """示例API端点"""
        return {"item_id": item_id, "q": q}

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)