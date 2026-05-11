# tests/__init__.py
# 初始化测试包

# 导入必要的测试框架
import pytest

# 导入测试配置
from .conftest import *  # 导入测试配置和 fixture

# 导入测试用例
from .test_views import *  # 导入视图测试用例

# 导入测试客户端
from flask.testing import FlaskClient

# 导入测试数据库
from flask_sqlalchemy import SQLAlchemy


# 测试包的初始化函数
def pytest_initplugin() -> None:
    """初始化测试插件"""
    pass


# 导出测试相关类和函数
__all__ = [
    'pytest_initplugin',
    'FlaskClient',
    'SQLAlchemy',
    'test_views'
]

# 注册测试钩子
pytestmark = pytest.mark.usefixtures('test_client')


# 简单的测试函数示例
def test_package_import() -> bool:
    """验证测试包导入功能"""
    try:
        from . import test_views
        return True
    except ImportError:
        return False


# 测试包元数据
__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"
__description__ = "测试包初始化文件"
__email__ = "your.email@example.com"
__url__ = "https://example.com"
__status__ = "Development"