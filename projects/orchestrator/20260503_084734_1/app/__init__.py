# app/__init__.py
# 应用初始化文件，创建Flask应用实例并配置基础功能

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from .models import IncrementalData  # 导入数据库模型

# 创建Flask应用实例
app = Flask(__name__)

# 配置SQLite数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///incremental_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化SQLAlchemy
db = SQLAlchemy(app)

# 在应用上下文中创建数据库表
with app.app_context():
    db.create_all()

# 注册路由蓝图
from .routes import main as main_routes
app.register_blueprint(main_routes)

# 全局错误处理
@app.errorhandler(404)
def not_found_error(error: Exception) -> tuple:
    """
    处理404错误，返回统一的JSON错误响应格式。
    
    返回:
        tuple: (JSON响应, HTTP状态码)
    """
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_server_error(error: Exception) -> tuple:
    """
    处理500内部服务器错误，返回统一的JSON错误响应格式。
    
    返回:
        tuple: (JSON响应, HTTP状态码)
    """
    return jsonify({"error": "Internal server error"}), 500

# 导入并注册路由
from .routes import main as main_routes
app.register_blueprint(main_routes)

# 确保应用可运行
if __name__ == "__main__":
    app.run(debug=True)