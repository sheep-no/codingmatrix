# __init__.py
# 初始化模块文件，无实际业务逻辑

# 可以添加包初始化代码，例如：
from . import fastapi
from . import apimiddleware
from . import tests

# 如果需要设置包的元数据，可以添加如下内容：
"""
__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"
__license__ = "MIT"
__description__ = "FastAPI example project"
"""

# 导入错误类
from fastapi import HTTPException

# 导入基础数据模型
from pydantic import BaseModel

# 导入类型注解
from typing import Optional, List, Dict, Any

# 可以添加一些全局配置（示例）
class ProjectConfig:
    """项目配置类"""
    
    def __init__(self):
        self.environment = "development"
        self.debug = True
        self.use_cache = False
        
    def get_config(self):
        """获取配置信息"""
        return {
            "environment": self.environment,
            "debug": self.debug,
            "cache": self.use_cache
        }

# 初始化配置
config = ProjectConfig()

# 导入业务模块（示例）
from .fastapi import router as fastapi_router
from .apimiddleware import (
    RequestMiddleware,
    ResponseMiddleware
)

# 导入异常处理
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 自定义异常处理（示例）
def custom_error_handler(exc: Exception, request: Request):
    """自定义异常处理函数"""
    return JSONResponse(
        status_code=400,
        content={"detail": f"发生错误: {str(exc)}"}
    )