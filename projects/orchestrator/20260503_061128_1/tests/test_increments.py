# tests/test_increments.py
import pytest
from src.data_generator import generate_increments
from src.config import Config

def test_normal_case():
    """
    测试正常增量生成场景：验证标准参数生成的序列正确性
    """
    config = Config(start=10, step=5, count=3)
    result = generate_increments(config)
    assert result == [10, 15, 20], "正常场景生成结果不符合预期"

def test_zero_count():
    """
    测试数量为零的边界情况：验证返回空列表的逻辑
    """
    config = Config(start=5, step=2, count=0)
    result = generate_increments(config)
    assert result == [], "数量为零时未返回空列表"

def test_negative_step():
    """
    测试负数步长场景：验证倒序生成逻辑
    """
    config = Config(start=20, step=-3, count=4)
    result = generate_increments(config)
    assert result == [20, 17, 14, 11], "负数步长生成结果不符合预期"

def test_step_zero():
    """
    测试步长为零的异常情况：验证是否抛出ValueError
    """
    config = Config(start=5, step=0, count=3)
    with pytest.raises(ValueError, match="步长不能为零"):
        generate_increments(config)

def test_invalid_count():
    """
    测试非法数量参数：验证是否抛出ValueError
    """
    config = Config(start=5, step=2, count=-3)
    with pytest.raises(ValueError, match="生成数量必须为非负整数"):
        generate_increments(config)

def test_config_defaults():
    """
    测试配置文件默认参数：验证默认值的使用
    """
    config = Config()
    result = generate_increments(config)
    assert result == [0, 1, 2, 3, 4], "默认配置生成结果不符合预期"

def test_custom_config():
    """
    测试自定义配置参数：验证参数覆盖功能
    """
    config = Config(start=100, step=10, count=5)
    result = generate_increments(config)
    assert result == [100, 110, 120, 130, 140], "自定义配置生成结果不符合预期"

def test_type_validation():
    """
    测试参数类型验证：验证非整数参数的处理
    """
    config = Config(start="20", step=5, count=3)
    with pytest.raises(TypeError, match="起始值必须为整数"):
        generate_increments(config)

    config = Config(start=5, step="10", count=3)
    with pytest.raises(TypeError, match="步长必须为整数"):
        generate_increments(config)

    config = Config(start=5, step=10, count="3")
    with pytest.raises(TypeError, match="生成数量必须为整数"):
        generate_increments(config)