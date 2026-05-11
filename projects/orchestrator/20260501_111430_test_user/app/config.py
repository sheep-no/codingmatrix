# app/config.py
class Config:
    """Flask应用配置类
    
    存储Flask应用的配置项，包括：
    - 应用名称
    - 调试模式
    - 运行端口
    - 数据库配置
    
    使用类属性访问配置项，遵循Flask最佳实践
    """
    
    # 应用配置
    APPLICATION_NAME = "Hello World API"
    DEBUG = False  # 默认关闭调试模式
    TESTING = False  # 默认不启用测试模式
    
    # 服务器配置
    SERVER_PORT = 5000  # 默认运行端口
    SERVER_HOST = "0.0.0.0"  # 默认监听所有网络接口
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"  # 默认SQLite数据库
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 关闭SQLAlchemy模型修改跟踪
    
    # 安全配置
    SECRET_KEY = "development-key"  # 开发密钥，用于会话安全
    
    # 请求配置
    JSON_AS_ASCII = False  # JSON响应使用Unicode字符
    ERROR_404_HELP = False  # 关闭404错误帮助信息
    
    # 日志配置
    LOG_LEVEL = "INFO"  # 默认日志级别
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class ProductionConfig(Config):
    """生产环境配置
    
    继承基础配置，添加生产环境特定设置
    """
    
    DEBUG = False
    TESTING = False
    SERVER_PORT = 80  # 生产环境通常使用80端口
    SQLALCHEMY_DATABASE_URI = "postgresql://user:password@localhost/helloworld"  # 示例PostgreSQL配置


class DevelopmentConfig(Config):
    """开发环境配置
    
    继承基础配置，添加开发环境特定设置
    """
    
    DEBUG = True  # 启用调试模式
    ERROR_404_HELP = True  # 开启404错误帮助信息
    SERVER_PORT = 5000  # 默认开发端口


class TestingConfig(Config):
    """测试环境配置
    
    继承基础配置，添加测试环境特定设置
    """
    
    TESTING = True  # 启用测试模式
    DEBUG = True  # 开启调试模式以便于测试
    SERVER_PORT = 5000  # 测试端口
    SQLALCHEMY_DATABASE_URI = "sqlite:///test.db"  # 测试专用数据库


# 导出配置类
__all__ = ["Config", "ProductionConfig", "DevelopmentConfig", "TestingConfig"]