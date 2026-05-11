"""
Pytest 通用配置和 Fixtures
"""

import pytest
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.security import create_access_token
from app.db.database import engine, async_session
from app.models.base import Base
from app.models.user import User
from app.models.Permission import Permission


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def timeout():
    """默认超时时间（秒）"""
    return 30


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return 1


@pytest.fixture
def test_super_user_id():
    """超级管理员用户 ID"""
    return 1


@pytest.fixture
def auth_token():
    """生成有效的 JWT token（普通用户）"""
    return create_access_token(
        sub="1",
        permission_level="normal",
        expires_delta=None
    )


@pytest.fixture
def super_auth_token():
    """生成有效的 JWT token（超级管理员）"""
    return create_access_token(
        sub="1",
        permission_level="super",
        expires_delta=None
    )


@pytest.fixture
def user_token():
    """生成有效的 JWT token（数字 sub）"""
    return create_access_token(
        sub="1",
        permission_level="normal",
        expires_delta=None
    )


@pytest.fixture
def super_user_token():
    """生成有效的 JWT token（数字 sub，超级管理员）"""
    return create_access_token(
        sub="1",
        permission_level="super",
        expires_delta=None
    )


@pytest.fixture
def auth_headers(user_token):
    """认证请求头"""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def super_auth_headers(super_user_token):
    """超级管理员认证请求头"""
    return {"Authorization": f"Bearer {super_user_token}"}


@pytest.fixture
def api_base_url():
    """API 基础 URL"""
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture
def api_v1_base_url(api_base_url):
    """API v1 基础 URL"""
    return f"{api_base_url}/api/v1"


@pytest.fixture
def api_v2_base_url(api_base_url):
    """API v2 基础 URL"""
    return f"{api_base_url}/api/v2"


@pytest.fixture
async def db_session():
    """数据库会话"""
    async with async_session() as session:
        yield session


@pytest.fixture
async def test_db_setup():
    """创建测试数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Selenium 配置
def pytest_addoption(parser):
    """添加命令行选项"""
    parser.addoption(
        "--selenium-base-url",
        action="store",
        default="http://127.0.0.1:5173",
        help="前端服务地址"
    )
    parser.addoption(
        "--api-base-url",
        action="store",
        default="http://127.0.0.1:8000",
        help="后端 API 地址"
    )
    parser.addoption(
        "--headless",
        action="store_true",
        default=False,
        help="Selenium 无头模式"
    )
    parser.addoption(
        "--browser",
        action="store",
        default="chrome",
        choices=["chrome", "firefox"],
        help="Selenium 浏览器类型"
    )


@pytest.fixture
def selenium_base_url(request):
    """获取前端服务地址"""
    return request.config.getoption("--selenium-base-url")


@pytest.fixture
def api_base_url_option(request):
    """获取后端 API 地址"""
    return request.config.getoption("--api-base-url")


@pytest.fixture(scope="session")
def chrome_options():
    """Selenium Chrome 配置"""
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    return options


@pytest.fixture(scope="session")
def firefox_options():
    """Selenium Firefox 配置"""
    from selenium.webdriver.firefox.options import Options
    options = Options()
    options.add_argument('--headless')
    return options


@pytest.fixture(scope="session")
def driver(request, chrome_options, firefox_options):
    """Selenium WebDriver"""
    browser = request.config.getoption("--browser")
    headless = request.config.getoption("--headless")

    if browser == "chrome":
        from selenium import webdriver
        options = chrome_options
        if not headless:
            options = Options()
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
        driver = webdriver.Chrome(options=options)
    else:
        from selenium import webdriver
        driver = webdriver.Firefox(options=firefox_options)

    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


@pytest.fixture
def test_project_data():
    """测试项目数据"""
    return {
        "name": "测试项目",
        "description": "这是一个测试项目",
        "requirement": "创建一个简单的 Python Web 应用",
        "projectType": "web"
    }


@pytest.fixture
def test_chat_message():
    """测试聊天消息"""
    return {
        "prompt": "你好，请介绍一下 Python",
        "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    }


@pytest.fixture
def test_file_content():
    """测试文件内容"""
    return b"print('Hello, World!')"


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "username": f"testuser_{datetime.now().timestamp()}",
        "email": f"test_{datetime.now().timestamp()}@example.com",
        "password": "TestPassword123!",
        "permission_level": "normal"
    }


@pytest.fixture
def sample_admin_user_data():
    """示例管理员用户数据"""
    return {
        "username": f"admin_{datetime.now().timestamp()}",
        "email": f"admin_{datetime.now().timestamp()}@example.com",
        "password": "AdminPassword123!",
        "permission_level": "super"
    }
