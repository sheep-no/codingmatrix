"""
constants/constants.py
计算器API常量配置文件
"""

# HTTP状态码
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_400_BAD_REQUEST = 400
HTTP_401_UNAUTHORIZED = 401
HTTP_403_FORBIDDEN = 403
HTTP_404_NOT_FOUND = 404
HTTP_500_INTERNAL_SERVER_ERROR = 500

# 自定义错误码
ERROR_CODE_INVALID_INPUT = 1001
ERROR_CODE_DIVISION_BY_ZERO = 1002
ERROR_CODE_NEGATIVE_SQUARE = 1003

# 默认值配置
DEFAULT_VALUE = 0
DECIMAL_PRECISION = 10  # 小数精度控制

# 超时配置
ASYNC_TIMEOUT = 30  # 秒

# 日志配置
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# API版本
API_VERSION = "v1"
API_DESCRIPTION = "计算器服务API"

# 验证配置
MAX_NUMBER_LIMIT = 1000000  # 数字上限
MIN_NUMBER_LIMIT = -1000000  # 数字下限
OPERATION_TYPES = ["add", "subtract", "multiply", "divide"]

# 返回结果配置
SUCCESS_MESSAGE = "操作成功"
ERROR_MESSAGE = "操作失败"

# 测试相关配置
TEST_TIMEOUT = 5  # 秒
TEST_RETRY = 3  # 重试次数

# 性能阈值
CONCURRENCY_THRESHOLD = 1000  # 并发阈值
MEMORY_USAGE_THRESHOLD = 70  # 内存使用百分比阈值

# 安全配置
MAX_REQUEST_RATE = 100  # 每秒最大请求数
SECURE_COOKIE = True

# 环境配置
ENV_DEV = "development"
ENV_PROD = "production"

# 版本控制
PROJECT_NAME = "FastAPI Calculator"
PROJECT_VERSION = "1.0.0"
LAST_UPDATED = "2023-04-15"

# 数据库配置
DB_MAX_CONNECTIONS = 20
DB_RETRY_ATTEMPTS = 3
DB_TIMEOUT = 5  # 秒

# 缓存配置
CACHE_EXPIRY = 3600  # 秒
CACHE_MAX_SIZE = 1000