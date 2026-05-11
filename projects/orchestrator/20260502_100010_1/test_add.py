# test_add.py
# 单元测试文件，用于验证 add.py 中 add_numbers 函数的正确性

import unittest
from add import add_numbers

class TestAdd(unittest.TestCase):
    """测试 add_numbers 函数的单元测试类"""
    
    def test_add_positive_numbers(self) -> None:
        """测试两个正数相加的情况"""
        result = add_numbers(3, 5)
        self.assertEqual(result, 8, "正数相加应返回正确结果")

    def test_add_negative_numbers(self) -> None:
        """测试两个负数相加的情况"""
        result = add_numbers(-3, -5)
        self.assertEqual(result, -8, "负数相加应返回正确结果")

    def test_add_zero(self) -> None:
        """测试两个零相加的情况"""
        result = add_numbers(0, 0)
        self.assertEqual(result, 0, "零相加应返回零")

    def test_add_mixed_types(self) -> None:
        """测试不同类型参数（整数和浮点数）相加的情况"""
        result = add_numbers(2, 3.5)
        self.assertEqual(result, 5.5, "整数和浮点数相加应返回正确结果")

    def test_add_non_numeric_inputs(self) -> None:
        """测试非数字类型参数时是否抛出 TypeError"""
        with self.assertRaises(TypeError):
            add_numbers("3", 5)
        with self.assertRaises(TypeError):
            add_numbers([1, 2], 3)
        with self.assertRaises(TypeError):
            add_numbers(3, {"key": "value"})

if __name__ == "__main__":
    unittest.main()