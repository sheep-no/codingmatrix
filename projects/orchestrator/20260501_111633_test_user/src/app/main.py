import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_restx import Api, Resource, Namespace
from typing import Optional
from datetime import datetime

# 加载环境变量
load_dotenv()

# 创建 Flask 应用实例
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# 创建 API 实例
api = Api(app, version='1.0.0', title='Simple API', description='A simple Hello World API')

# 创建命名空间
ns_hello = Namespace('hello', description='Hello World operations')

# 定义 Hello World 资源
@ns_hello.route('/')
class HelloWorld(Resource):
    """Handles the root endpoint for Hello World"""
    
    @api.doc('hello_world')
    def get(self) -> dict:
        """Returns a greeting message"""
        return {
            'timestamp': str(datetime.utcnow()),
            'message': 'Hello, World!',
            'status': 'success'
        }

# 注册命名空间到 API
api.add_namespace(ns_hello)

# 错误处理
@app.errorhandler(404)
def not_found(error) -> tuple[dict[str, str], int]:
    """Handles 404 Not Found errors"""
    return jsonify({
        'timestamp': str(datetime.utcnow()),
        'status': 'error',
        'error': 'Not Found',
        'message': 'The requested resource was not found.'
    }), 404

@app.errorhandler(500)
def internal_server_error(error) -> tuple[dict[str, str], int]:
    """Handles 500 Internal Server Error"""
    return jsonify({
        'timestamp': str(datetime.utcnow()),
        'status': 'error',
        'error': 'Internal Server Error',
        'message': 'Something went wrong on our side.'
    }), 500

# 健康检查端点
@app.route('/health', methods=['GET'])
def health_check() -> dict:
    """Performs a health check of the API"""
    return jsonify({
        'status': 'healthy',
        'timestamp': str(datetime.utcnow())
    }), 200

# 主页面
@app.route('/', methods=['GET'])
def home() -> dict:
    """Home page with information about the API"""
    return jsonify({
        'status': 'success',
        'message': 'Welcome to the Simple API',
        'documentation': '/apidocs',
        'endpoints': {
            '/hello': 'Hello World endpoint',
            '/health': 'Health check endpoint'
        }
    }), 200

if __name__ == '__main__':
    # 获取环境变量中的端口，如果没有则使用默认端口 5000
    port = int(os.environ.get('PORT', 5000))
    # 获取环境变量中的调试模式，如果没有则默认关闭调试
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    
    # 运行应用
    app.run(host='0.0.0.0', port=port, debug=debug)