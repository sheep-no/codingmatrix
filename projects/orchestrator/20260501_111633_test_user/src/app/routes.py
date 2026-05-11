from flask import Blueprint
from flask_restx import Namespace, Resource

# 创建命名空间
api_namespace = Namespace('api', description='Simple API namespace')

# 定义问候API
@api_namespace.route('/hello')
class HelloWorld(Resource):
    """返回简单的问候消息"""
    
    def get(self):
        """处理GET请求，返回问候消息"""
        return {
            'message': 'Hello World!',
            'status': 'success',
            'timestamp': '2023-05-01T12:00:00Z'
        }