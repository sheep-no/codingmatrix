"""
app/__init__.py
初始化应用上下文，加载配置和路由
"""

import os
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# 初始化数据库
db = SQLAlchemy()
# 初始化密码加密工具
bcrypt = Bcrypt()
# 初始化数据库迁移工具
migrate = Migrate()
# 初始化登录管理器
login_manager = LoginManager()
login_manager.login_view = 'main.login'  # 设置登录页面的端点

def create_app(test_config=None):
    """
    创建并配置Flask应用实例
    :param test_config: 测试配置字典（可选）
    :return: 配置好的Flask应用实例
    """
    app = Flask(__name__)
    
    # 加载配置
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    
    # 初始化扩展
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    # 设置静态文件缓目录
    app.static_folder = 'static'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB文件上传限制
    
    # 设置应用上下文处理程序
    @app.context_processor
    def inject_config():
        """
        注入全局配置到模板
        :return: 包含配置的字典
        """
        return dict(config=app.config)
    
    # 注册蓝本
    from .main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    
    from .api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # 设置自定义错误页面
    from .errors import not_found, internal_error
    
    # 错误处理程序
    app.register_error_handler(404, not_found)
    app.register_error_handler(500, internal_error)
    
    # 创建初始数据库表（在生产环境中通常通过迁移处理）
    with app.app_context():
        try:
            db.create_all()
            # 可选的数据库初始化代码
        except Exception as e:
            app.logger.warning(f"Database initialization error: {str(e)}")
    
    # 返回配置好的应用实例
    return app

class Config:
    """
    应用基础配置类
    """
    # 调试模式
    DEBUG = os.environ.get('FLASK_DEBUG', False)
    
    # 密钥，用于会话和JWT签名
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key')
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        'postgresql://postgres:postgres@localhost/flask_app'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = os.environ.get(
        'SQLALCHEMY_TRACK_MODIFICATIONS', False
    )
    
    # 会话配置
    SESSION_COOKIE_NAME = 'flask_session'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB最大上传
    UPLOAD_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.pdf']
    
    # 邮件配置（可选）
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', True)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # 安全配置
    SECURITY_PASSWORD_SALT = os.environ.get(
        'SECURITY_PASSWORD_SALT', 
        'default-password-salt'
    )
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'app.log')
    
    # API配置
    API_VERSION = 'v1'
    API_PREFIX = '/api'
    
    # 率限制配置
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', False)
    RATE_LIMIT_PER_IP = os.environ.get('RATE_LIMIT_PER_IP', 100)
    RATE_LIMIT_WINDOW = os.environ.get('RATE_LIMIT_WINDOW', 'minute')
    
    # 安全域配置
    CSP_ENABLED = os.environ.get('CSP_ENABLED', False)
    CSP_POLICY = os.environ.get(
        'CSP_POLICY', 
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    )

# 导入模型（确保在应用上下文中导入）
from .models import User, Product, Order, Transaction

# 导入路由蓝本
from .main import main
from .auth import auth
from .api import api
from .errors import errors_bp as errors_bp
from . import api_bp