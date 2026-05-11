# tests/test_calculate.py
import pytest
from calculate import add

@pytest.mark.unit
def test_add_success():
    """
    测试add函数在正常输入情况下的正确性
    验证整数、浮点数和混合类型输入的加法运算
    """
    # 整数相加
    assert add(2, 3) == 5, "整数相加应返回正确结果"
    
    # 浮点数相加
    assert add(4.5, 3.2) == 7.7, "浮点数相加应返回正确结果"
    
    # 正数与负数相加
    assert add(-1, 2) == 1, "正负数相加应返回正确结果"
    
    # 零相加
    assert add(0, 0) == 0, "零相加应返回零"

@pytest.mark.unit
def test_add_failure_with_strings():
    """
    测试add函数在传入字符串参数时的异常处理
    验证字符串类型参数是否触发TypeError
    """
    with pytest.raises(TypeError):
        add("2", 3)
    with pytest.raises(TypeError):
        add(2, "3")
    with pytest.raises(TypeError):
        add("a", "b")

@pytest.mark.unit
def test_add_failure_with_non_numbers():
    """
    测试add函数在传入非数字类型参数时的异常处理
    验证列表、字典等非数字类型是否触发TypeError
    """
    with pytest.raises(TypeError):
        add([1, 2], 3)
    with pytest.raises(TypeError):
        add({"a": 1}, 5)
    with pytest.raises(TypeError):
        add(None, 0)

@pytest.mark.unit
def test_add_failure_with_bool():
    """
    测试add函数对布尔类型参数的处理
    验证布尔值是否被视为无效类型并触发TypeError
    """
    with pytest.raises(TypeError):
        add(True, 5)
    with pytest.raises(TypeError):
        add(5, True)
    with pytest.raises(TypeError):
        add(True, True)