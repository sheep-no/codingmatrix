from flask import Blueprint, jsonify

# 创建一个蓝图
views_bp = Blueprint('views', __name__)

# 定义处理/hello请求的视图函数
@views_bp.route('/hello', methods=['GET'])
def hello_world():
    """
    处理/hello GET请求的视图函数。
    返回一个简单的问候消息。
    """
    try:
        # 添加简单的业务逻辑
        response_data = {
            "message": "Hello, World!",
            "status": "success",
            "timestamp": "2023-10-15T14:30:00Z"
        }
        return jsonify(response_data), 200
    
    except Exception as e:
        # 错误处理
        error_response = {
            "message": "An error occurred",
            "error": str(e),
            "status": "error"
        }
        return jsonify(error_response), 500

# 注意：在app/__init__.py中需要注册此蓝图
# 例如：app.register_blueprint(views_bp)