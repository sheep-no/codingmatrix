# projects/orchestrator/20260502_100203_1/incremental_generator/test_generator.py
import pytest
from typing import List, Dict, Any
from incremental_generator.generator import generate_increments, IncrementGenerator


def test_generate_increments_normal_case() -> None:
    """
    测试generate_increments函数在正常情况下的行为：
    - start=0, step=1, max_value=10
    - 应该生成0到9的序列（包含start，不包含max_value）
    """
    result = generate_increments(start=0, step=1, max_value=10)
    assert result == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], "正常情况应生成完整递增序列"


def test_generate_increments_negative_start() -> None:
    """
    测试generate_increments函数处理负数起始值的情况：
    - start=-5, step=3, max_value=5
    - 应该从-5开始，每次加3，直到不超过5
    """
    result = generate_increments(start=-5, step=3, max_value=5)
    assert result == [-5, -2, 1, 4], "负数起始值应正确计算递增序列"


def test_generate_increments_zero_step() -> None:
    """
    测试generate_increments函数当step为0时的异常处理：
    - step=0应触发ValueError
    """
    with pytest.raises(ValueError, match="Step cannot be zero"):
        generate_increments(start=5, step=0, max_value=10)


def test_generate_increments_start_greater_than_max() -> None:
    """
    测试generate_increments函数当start大于max_value时的行为：
    - 应该返回空列表
    """
    result = generate_increments(start=15, step=2, max_value=10)
    assert result == [], "起始值超过最大值时应返回空列表"


def test_generate_increments_with_custom_step() -> None:
    """
    测试generate_increments函数处理非1步长的情况：
    - start=2, step=2, max_value=8
    - 应该生成2,4,6,8（包含max_value）
    """
    result = generate_increments(start=2, step=2, max_value=8)
    assert result == [2, 4, 6, 8], "非1步长应正确生成序列（包含max_value）"


def test_increment_generator_initialization() -> None:
    """
    测试IncrementGenerator类初始化时的参数验证：
    - 验证start, step, max_value的类型和范围
    """
    with pytest.raises(TypeError, match="start must be an integer"):
        IncrementGenerator(start="0", step=1, max_value=10)
    
    with pytest.raises(ValueError, match="start cannot be negative"):
        IncrementGenerator(start=-1, step=1, max_value=10)
    
    with pytest.raises(ValueError, match="step cannot be zero"):
        IncrementGenerator(start=0, step=0, max_value=10)


def test_increment_generator_generate_method() -> None:
    """
    测试IncrementGenerator类的generate方法：
    - 验证生成的序列是否符合预期
    - 验证状态管理是否正确（不重复生成）
    """
    generator = IncrementGenerator(start=0, step=1, max_value=5)
    
    # 第一次生成
    result1 = generator.generate()
    assert result1 == [0, 1, 2, 3, 4], "首次生成应包含完整序列"
    
    # 第二次生成（状态应继续）
    result2 = generator.generate()
    assert result2 == [5], "第二次生成应继续剩余的值"
    
    # 第三次生成（超过max_value）
    result3 = generator.generate()
    assert result3 == [], "超出范围后应返回空列表"


def test_increment_generator_reset_method() -> None:
    """
    测试IncrementGenerator类的reset方法：
    - 验证生成器能否正确重置状态
    """
    generator = IncrementGenerator(start=0, step=1, max_value=5)
    
    # 第一次生成
    result1 = generator.generate()
    assert result1 == [0, 1, 2, 3, 4], "首次生成应包含完整序列"
    
    # 重置生成器
    generator.reset()
    
    # 第二次生成
    result2 = generator.generate()
    assert result2 == [0, 1, 2, 3, 4], "重置后应重新生成完整序列"


def test_increment_generator_invalid_max_value() -> None:
    """
    测试IncrementGenerator类当max_value为负数时的异常处理：
    - max_value=-10应触发ValueError
    """
    with pytest.raises(ValueError, match="max_value cannot be negative"):
        IncrementGenerator(start=0, step=1, max_value=-10)


def test_increment_generator_step_negative() -> None:
    """
    测试IncrementGenerator类处理负数步长的情况：
    - start=10, step=-2, max_value=0
    - 应该生成10, 8, 6, 4, 2, 0
    """
    generator = IncrementGenerator(start=10, step=-2, max_value=0)
    result = generator.generate()
    assert result == [10, 8, 6, 4, 2, 0], "负数步长应正确生成递减序列"


def test_increment_generator_with_duplicate_values() -> None:
    """
    测试IncrementGenerator类处理包含重复值的输入数据：
    - 输入数据包含重复项时应去重
    """
    generator = IncrementGenerator(start=0, step=1, max_value=5)
    generator.add_data([0, 1, 0, 2, 3, 1])
    
    # 第一次生成
    result1 = generator.generate()
    assert result1 == [0, 1, 2, 3, 4], "重复数据应被正确去重"
    
    # 第二次生成（状态继续）
    result2 = generator.generate()
    assert result2 == [5], "去重后应继续剩余的值"


def test_increment_generator_non_integer_parameters() -> None:
    """
    测试IncrementGenerator类对非整数参数的类型验证：
    - 参数类型错误时应触发TypeError
    """
    with pytest.raises(TypeError, match="start must be an integer"):
        IncrementGenerator(start="0", step=1, max_value=5)
    
    with pytest.raises(TypeError, match="step must be an integer"):
        IncrementGenerator(start=0, step="1", max_value=5)
    
    with pytest.raises(TypeError, match="max_value must be an integer"):
        IncrementGenerator(start=0, step=1, max_value="5")