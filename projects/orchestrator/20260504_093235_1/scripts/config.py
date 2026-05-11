# scripts/config.py
# 配置文件，存储脚本运行参数

# 项目配置类，包含脚本运行所需的参数设置
class Config:
    # 应用名称，用于标识脚本身份
    APPLICATION_NAME: str = "hello_world_script"
    
    # 日志配置参数
    LOGGING_CONFIG = {
        # 日志文件存储路径
        "LOG_FILE_PATH": "logs/hello_world.log",
        # 日志记录级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        "LOG_LEVEL": "INFO",
        # 是否启用日志记录
        "ENABLE_LOGGING": True
    }
    
    # 环境配置参数
    ENVIRONMENT = {
        # 当前运行环境（开发/测试/生产）
        "ENV": "development",
        # 开发环境是否启用调试模式
        "DEBUG_MODE": True,
        # 生产环境的最大并发数
        "MAX_CONCURRENCY": 100
    }
    
    # API配置参数（虽然当前需求是简单脚本，但预留API相关配置）
    API_SETTINGS = {
        # API超时时间（秒）
        "REQUEST_TIMEOUT": 30,
        # API请求重试次数
        "MAX_RETRIES": 3,
        # 是否启用API验证
        "ENABLE_API_VALIDATION": True
    }
    
    # 数据库配置参数（当前需求无需数据库，但预留结构）
    DATABASE = {
        # 数据库类型（mysql/postgres/sqlite）
        "TYPE": "sqlite",
        # 数据库文件路径
        "FILE_PATH": "db/hello_world.db",
        # 连接参数
        "CONN_PARAMS": {
            "host": "localhost",
            "port": 5432,  # 默认PostgreSQL端口
            "user": "script_user",
            "password": "secure_password"
        }
    }

# 验证配置参数的辅助函数
def validate_config() -> None:
    """验证配置参数是否完整"""
    try:
        # 基础验证：确保所有必需的配置项都存在
        assert Config.APPLICATION_NAME, "应用名称不能为空"
        assert Config.LOGGING_CONFIG["LOG_FILE_PATH"], "日志路径不能为空"
        assert Config.ENVIRONMENT["ENV"], "环境配置不能为空"
        
        # 环境变量验证
        if Config.ENVIRONMENT["ENV"] not in ["development", "production", "testing"]:
            raise ValueError("环境配置必须是 development, production 或 testing")
            
        # 类型验证
        if not isinstance(Config.LOGGING_CONFIG["LOG_LEVEL"], str):
            raise TypeError("日志级别必须是字符串类型")
            
        # 数值类型验证
        if not isinstance(Config.DATABASE["CONN_PARAMS"].get("port"), int):
            raise TypeError("数据库端口必须是整数类型")
            
    except (AssertionError, TypeError, ValueError) as e:
        print(f"配置验证失败: {str(e)}")
        raise

# 在脚本运行时自动验证配置
if __name__ == "__main__":
    validate_config()
    print("配置验证通过")