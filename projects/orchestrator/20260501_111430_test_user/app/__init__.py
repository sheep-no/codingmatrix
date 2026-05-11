import os
from flask import Flask
from dotenv import load_dotenv

def create_app(test_config=None):
    """应用工厂函数，创建并配置Flask应用"""
    # 创建Flask应用实例
    app = Flask(__name__)
    
    # 加载环境变量
    load_dotenv()
    
    # 应用配置
    if test_config is None:
        # 加载默认配置
        app.config.from_pyfile('config.py', silent=True)
    else:
        # 加载测试配置
        app.config.update(test_config)
    
    # 确保上传目录存在
    app.config['UPLOAD_FOLDER'] = 'uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # 确保静态文件目录存在
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    os.makedirs(static_dir, exist_ok=True)
    
    # 注册API路由
    from .routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    # 错误处理
    @app.errorhandler(404)
    def not_found(error):
        """处理404错误"""
        return {
            "error": "Not found",
            "message": "The requested resource could not be found"
        }, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """处理500错误"""
        return {
            "error": "Internal server error",
            "message": "Something went wrong on our end"
        }, 500
    
    return app