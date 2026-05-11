# scripts/test_script.py
import pytest
from typing import List, Dict, Any
from scripts.main import add, process_data, calculate_stats  # 假设main.py中存在这些函数

"""
测试用例文件，使用pytest框架进行单元测试
包含正常流程测试、异常处理测试和参数化测试
"""


# 测试 add 函数
def test_add_success() -> None:
    """
    测试 add 函数的正常流程
    验证两个整数相加的正确性
    """
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_add_type_error() -> None:
    """
    测试 add 函数的类型错误处理
    验证非整数参数会引发TypeError
    """
    with pytest.raises(TypeError):
        add("2", 3)
    with pytest.raises(TypeError):
        add(2, "3")


# 测试 process_data 函数
def test_process_data_success() -> None:
    """
    测试 process_data 函数的正常流程
    验证字符串处理和数据转换的正确性
    """
    input_data = "1,2,3,4,5"
    expected_output = {"numbers": [1, 2, 3, 4, 5], "count": 5, "sum": 15, "avg": 3.0}
    
    # 使用类型注解进行参数化测试
    assert process_data(input_data) == expected_output


def test_process_data_invalid_input() -> None:
    """
    测试 process_data 函数的异常处理
    验证无效输入会引发ValueError
    """
    with pytest.raises(ValueError):
        process_data("invalid, data")
    with pytest.raises(ValueError):
        process_data("1,2,three,4,5")


# 测试 calculate_stats 函数
def test_calculate_stats_success() -> None:
    """
    测试 calculate_stats 函数的正常流程
    验证统计计算的正确性
    """
    sample_data = [1, 2, 3, 4, 5]
    expected_output = {
        "mean": 3.0,
        "median": 3,
        "mode": [1, 2, 3, 4, 5],  # 假设所有数字出现次数相同
        "std_dev": pytest.approx(1.4142, 0.0001)
    }
    
    # 参数化测试不同数据集
    assert calculate_stats(sample_data) == expected_output


@pytest.mark.parametrize("input_data, expected", [
    ([], {"mean": None, "median": None, "mode": None, "std_dev": None}),
    ([1, 1, 2, 2], {"mean": 1.5, "median": 1.5, "mode": [1, 2], "std_dev": pytest.approx(0.5, 0.0001)})
])
def test_calculate_stats_edge_cases(input_data: List[int], expected: Dict[str, Any]) -> None:
    """
    测试 calculate_stats 函数的边界情况
    验证空列表和重复数据的处理
    """
    result = calculate_stats(input_data)
    assert result == expected


# 测试异常处理逻辑
def test_division_by_zero() -> None:
    """
    测试除以零的异常处理（假设main.py中存在相关逻辑）
    验证是否正确处理零除错误
    """
    with pytest.raises(ValueError, match="division by zero is not allowed"):
        add(10, 0)  # 假设此处存在除以零的逻辑


# 参数化测试多组数据
@pytest.mark.parametrize("a, b, expected", [
    (2, 3, 5),
    (-1, 1, 0),
    (0, 0, 0),
    (10, 5, 15)
])
def test_add_parametrized(a: int, b: int, expected: int) -> None:
    """
    参数化测试 add 函数
    验证不同输入组合的正确性
    """
    assert add(a, b) == expected


# 测试自定义异常
def test_custom_exception() -> None:
    """
    测试自定义异常的抛出（假设main.py中存在自定义异常类）
    验证是否正确触发业务逻辑异常
    """
    with pytest.raises(ValueError, match="Invalid input"):  # 假设存在自定义异常信息
        process_data("invalid_data")