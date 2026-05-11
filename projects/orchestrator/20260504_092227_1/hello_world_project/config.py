# hello_world_project/config.py
# 配置文件（占位符）

# API配置
API_VERSION = "v1"
HELLO_ROUTE = f"/api/{API_VERSION}/hello"
HELLO_MESSAGE = "Hello, World!"

# 数据库配置
DATABASE_URL = "sqlite:///./hello.db"  # 示例数据库URL，SQLite用于开发环境
DB_ECHO = False  # 是否启用SQL日志输出，生产环境应设为False

# 环境配置
ENVIRONMENT = "development"  # 可能的值: development, testing, production
DEBUG_MODE = ENVIRONMENT == "development"

# 错误处理配置
ERROR_LOG_PATH = "logs/errors.log"  # 错误日志文件路径
MAX_RETRIES = 3  # 数据库连接最大重试次数
RETRY_DELAY = 5  # 重试间隔时间（秒）

# 其他配置
# 可根据需要扩展更多配置项，例如认证设置、缓存配置等