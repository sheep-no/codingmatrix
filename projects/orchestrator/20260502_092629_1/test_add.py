# test_add.py
import unittest
from add import add_function

class TestAddFunction(unittest.TestCase):
    """
    单元测试类，用于验证 add_function 函数的正确性
    测试场景覆盖：
    - 正确输入（整数、浮点数）
    - 边界值（零、负数）
    - 异常处理（非数字类型输入）
    """

    def test_add_ints(self) -> None:
        """
        测试两个整数相加的情况
        验证正数相加结果是否正确
        """
        self.assertEqual(add_function(3, 5), 8)
        self.assertEqual(add_function(-2, -3), -5)
        self.assertEqual(add_function(0, 0), 0)
        self.assertEqual(add_function(100, 200), 300)

    def test_add_floats(self) -> None:
        """
        测试两个浮点数相加的情况
        验证浮点数相加结果是否正确
        """
        self.assertAlmostEqual(add_function(2.5, 3.5), 6.0)
        self.assertAlmostEqual(add_function(-1.2, 3.7), 2.5)
        self.assertAlmostEqual(add_function(0.0, 5.5), 5.5)
        self.assertAlmostEqual(add_function(1.1111111111, 2.2222222222), 3.3333333333)

    def test_add_mixed_types(self) -> None:
        """
        测试整数和浮点数混合相加的情况
        验证类型兼容性及结果正确性
        """
        self.assertEqual(add_function(4, 2.5), 6.5)
        self.assertEqual(add_function(-3, 1.5), -1.5)
        self.assertEqual(add_function(0, 0.0), 0.0)

    def test_add_type_errors(self) -> None:
        """
        测试非数字类型输入的异常处理
        验证是否正确抛出 TypeError
        """
        with self.assertRaises(TypeError):
            add_function("string", 5)
        with self.assertRaises(TypeError):
            add_function(3, "string")
        with self.assertRaises(TypeError):
            add_function("string", "string")

    def test_add_large_numbers(self) -> None:
        """
        测试大整数相加的情况
        验证数值范围是否处理正确
        """
        self.assertEqual(add_function(1_000_000_000_000, 2_000_000_000_000), 3_000_000_000_000)
        self.assertEqual(add_function(-999_999_999_999, -1), -1_000_000_000_000)

if __name__ == '__main__':
    unittest.main()