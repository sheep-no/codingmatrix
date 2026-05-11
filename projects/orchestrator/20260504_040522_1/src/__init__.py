# src/__init__.py
# 初始化模块，负责创建Flask应用实例并配置基础功能

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from typing import Optional

# 创建Flask应用实例
app: Optional[Flask] = None

# 初始化SQLAlchemy数据库对象
db: Optional[SQLAlchemy] = None

def create_app() -> Flask:
    """
    创建并配置Flask应用实例
    返回: 配置完成的Flask应用对象
    """
    try:
        # 初始化应用
        app = Flask(__name__)
        
        # 加载数据库配置（从db_config.py导入）
        app.config.from_pyfile('db_config.py')
        
        # 初始化SQLAlchemy
        db.init_app(app)
        
        # 注册核心API蓝图（从api.py导入）
        from .api import api_blueprint
        app.register_blueprint(api_blueprint)
        
        # 返回配置完成的应用实例
        return app
    
    except Exception as e:
        # 捕获并处理初始化过程中的异常
        app = Flask(__name__)
        app.logger.error(f"应用初始化失败: {str(e)}")
        return app

# 应用初始化逻辑
if __name__ == "__main__":
    try:
        # 创建数据库连接
        db = SQLAlchemy()
        
        # 配置应用
        app = create_app()
        
        # 创建所有数据库表（如果不存在）
        with app.app_context():
            db.create_all()
        
        # 启动开发服务器
        app.run(debug=True)
    
    except Exception as e:
        # 处理致命错误
        print(f"应用启动失败: {str(e)}")
        raise