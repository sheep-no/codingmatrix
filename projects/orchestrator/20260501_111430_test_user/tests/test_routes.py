import pytest
from flask.testing import FlaskClient
from app import create_app
from unittest.mock import patch

# 创建测试类
class TestRoutes:

    # 测试初始化方法，设置测试客户端
    def setup_method(self, method):
        self.app = create_app('testing')
        self.client: FlaskClient = self.app.test_client()
        self.app.config['TESTING'] = True

    # 测试根路径的GET请求
    def test_hello_world_route(self):
        response = self.client.get('/')
        assert response.status_code == 200
        assert response.json == {"message": "Hello, World!"}

    # 测试未实现的路由
    def test_unimplemented_route_404(self):
        response = self.client.get('/unimplemented')
        assert response.status_code == 404
        assert response.json == {"error": "Route not found"}

    # 测试异常处理
    def test_error_handler(self):
        with patch('app.routes.buggy_function') as mock_buggy:
            mock_buggy.side_effect = ValueError("Test error")
            response = self.client.get('/test-error')
            assert response.status_code == 500
            assert "Test error" in response.json["error"]

    # 测试参数验证
    def test_invalid_params(self):
        response = self.client.get('/hello?name=')  # 空参数
        assert response.status_code == 400
        assert "name must be a non-empty string" in response.json["error"]
        
        response = self.client.get('/hello?name=123')  # 非字符串
        assert response.status_code == 400
        assert "name must be a string" in response.json["error"]