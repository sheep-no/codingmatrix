from flask import Blueprint, jsonify

# 创建一个蓝图
bp = Blueprint('main', __name__)

@bp.route('/')
def hello_world():
    """
    返回一个简单的 Hello World JSON 响应
    包含状态码和消息
    """
    return jsonify({
        "message": "Hello, World!",
        "status": "success",
        "timestamp": "2023-10-01T12:00:00Z"
    }), 200

@bp.route('/health')
def health_check():
    """
    返回健康检查状态
    用于监控和负载均衡器
    """
    return jsonify({
        "status": "healthy",
        "uptime": "unknown",
        "dependencies": {
            "flask": "2.2.2",
            "python": "3.9.15"
        }
    }), 200

# 错误处理
@bp.errorhandler(404)
def not_found(error):
    """处理404错误"""
    return jsonify({
        "error": "Not Found",
        "message": "The requested resource was not found.",
        "status": 404
    }), 404

@bp.errorhandler(500)
def server_error(error):
    """处理500错误"""
    return jsonify({
        "error": "Internal Server Error",
        "message": "Something went wrong on our side.",
        "status": 500
    }), 500