# test_add.py
import unittest
from typing import Any, Union
from add import add

class TestAddFunction(unittest.TestCase):
    """
    单元测试类，用于验证add函数的正确性
    测试范围：正常输入、边界值、负数、大数、非数字类型异常
    """

    def test_add_integers(self) -> None:
        """
        测试两个整数相加的正确性
        验证：正整数、零、负整数的加法
        """
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(0, 0), 0)
        self.assertEqual(add(-1, -2), -3)
        self.assertEqual(add(100, -50), 50)

    def test_add_floats(self) -> None:
        """
        测试两个浮点数相加的正确性
        验证：正浮点数、负浮点数、小数点后位数不同的情况
        """
        self.assertEqual(add(1.5, 2.5), 4.0)
        self.assertEqual(add(-0.1, 0.1), 0.0)
        self.assertEqual(add(3.14159, 2.71828), 5.85987)

    def test_add_large_numbers(self) -> None:
        """
        测试大数相加的正确性
        验证：超出常规数值范围的整数相加
        """
        self.assertEqual(add(10**18, 10**18), 2 * 10**18)
        self.assertEqual(add(10**20, -10**10), 99999999999999999990000000000000000000)

    def test_add_non_numeric_types(self) -> None:
        """
        测试非数字类型输入的异常处理
        验证：字符串、列表、字典等类型会抛出TypeError
        """
        with self.assertRaises(TypeError):
            add("a", 2)
        with self.assertRaises(TypeError):
            add([1, 2], 3)
        with self.assertRaises(TypeError):
            add({"a": 1}, 5)
        with self.assertRaises(TypeError):
            add(2, None)

    def test_add_mixed_types(self) -> None:
        """
        测试不同数字类型混合相加（整数与浮点数）
        验证：整数和浮点数相加的结果类型和数值正确性
        """
        self.assertEqual(add(2, 3.5), 5.5)
        self.assertEqual(add(-4.5, 5), 0.5)
        self.assertEqual(add(0.0, 0), 0.0)

    def test_add_edge_cases(self) -> None:
        """
        测试边缘情况
        验证：最小值、最大值、特殊数值的处理
        """
        self.assertEqual(add(-10**18, 10**18), 0)
        self.assertEqual(add(10**100, 10**100), 2 * 10**100)
        self.assertEqual(add(1.7976931348623157e+308, 1.7976931348623157e+308), 3.5953862697246314e+308)

if __name__ == '__main__':
    unittest.main()