# tests/test_calculate.py
import pytest
from calculate.calculate import add

def test_add_normal_cases():
    """测试正常数值输入情况"""
    # 整数相加
    assert add(2, 3) == 5
    
    # 浮点数相加
    assert add(1.5, 2.5) == 4.0
    
    # 负数相加
    assert add(-1, -2) == -3
    
    # 零相加
    assert add(0, 0) == 0
    
    # 正负数相加
    assert add(-1, 1) == 0

def test_add_boundary_values():
    """测试边界值和特殊数值情况"""
    # 大整数相加
    assert add(10**20, 10**20) == 2*10**20
    
    # 浮点数边界值
    assert add(1.7976931348623157e308, 1.0) == 1.7976931348623157e308
    
    # 非常小的浮点数
    assert add(1.0e-324, 1.0e-324) == 2.0e-324

def test_add_type_errors():
    """测试类型验证异常情况"""
    with pytest.raises(TypeError):
        add("2", 3)  # 字符串和整数相加
    
    with pytest.raises(TypeError):
        add([1, 2], 3)  # 列表和整数相加
    
    with pytest.raises(TypeError):
        add(3, {"a": 1})  # 整数和字典相加
    
    with pytest.raises(TypeError):
        add("abc", "def")  # 字符串和字符串相加
    
    with pytest.raises(TypeError):
        add(None, 5)  # None和整数相加

def test_add_edge_cases():
    """测试特殊边界情况"""
    # 最大整数相加（Python的int没有最大值限制，但测试大数处理）
    assert add(10**1000, 1) == 10**1000 + 1
    
    # 浮点数精度测试
    result = add(0.1, 0.2)
    assert round(result, 10) == 0.3  # 浮点数精度误差处理
    
    # 0和正数相加
    assert add(0, 5) == 5
    
    # 0和负数相加
    assert add(0, -5) == -5

def test_add_invalid_types():
    """测试无效类型输入"""
    with pytest.raises(TypeError):
        add(True, 5)  # 布尔值会被视为整数，但应触发类型检查
    
    with pytest.raises(TypeError):
        add(5, True)  # 布尔值和整数相加
    
    with pytest.raises(TypeError):
        add(5, 3.14)  # 整数和浮点数相加
    
    with pytest.raises(TypeError):
        add(5, complex(1, 2))  # 整数和复数相加
    
    with pytest.raises(TypeError):
        add(5, (1, 2))  # 整数和元组相加