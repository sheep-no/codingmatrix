import pytest
from flask.testing import FlaskClient
from projects.orchestrator.app import create_app

# 导入需要测试的视图函数
from projects.orchestrator.app.views import hello

# 创建测试客户端
@pytest.fixture
def client() -> FlaskClient:
    """创建测试客户端"""
    app = create_app(testing=True)
    app.config.update({
        'TESTING': True,
        'DEBUG': False,
        'SERVER_NAME': 'localhost:5000'
    })
    yield app.test_client()
    app.config['TESTING'] = False

# 测试/hello端点的基本功能
def test_hello_endpoint(client: FlaskClient) -> None:
    """测试/hello端点返回正确的响应"""
    # 发送GET请求到/hello端点
    response = client.get('/hello')
    
    # 验证状态码为200 OK
    assert response.status_code == 200
    
    # 验证响应内容包含"Hello World"
    assert 'Hello World' in response.get_data(as_text=True)

# 测试/hello端点的响应格式
def test_hello_content_type(client: FlaskClient) -> None:
    """测试/hello端点响应格式为JSON"""
    response = client.get('/hello')
    
    # 验证响应内容类型为JSON
    assert response.content_type == 'application/json; charset=utf-8'

# 测试/hello端点的响应结构
def test_hello_response_structure(client: FlaskClient) -> None:
    """测试/hello端点响应JSON结构"""
    response = client.get('/hello')
    response_data = response.get_json()
    
    # 验证响应是一个字典
    assert isinstance(response_data, dict)
    
    # 验证字典包含'message'键
    assert 'message' in response_data
    
    # 验证消息内容
    assert response_data['message'] == 'Hello World'

# 验证路由注册成功
def test_route_registered(client: FlaskClient) -> None:
    """测试/hello路由是否正确注册"""
    # 尝试访问/hello端点
    client.get('/hello')
    
    # 这个测试是间接的，但可以确保路由存在
    # 如果路由未注册，这里不会抛出404错误，说明路由已注册
    
    # 如果需要，可以添加更直接的路由注册测试，但通常在测试中会依赖应用上下文
    # 这里使用更直接的方式验证路由注册
    with client.application.app_context():
        assert '/hello' in client.application.url_map.rules