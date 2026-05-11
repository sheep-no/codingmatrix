# test_add.py
import unittest
from add import add

class TestAddFunction(unittest.TestCase):
    """
    测试add函数的单元测试类
    验证不同场景下两个数相加的正确性
    """

    def test_add_integers(self) -> None:
        """测试两个整数相加"""
        result = add(2, 3)
        self.assertEqual(result, 5, "整数相加应返回正确结果")

    def test_add_negative_numbers(self) -> None:
        """测试两个负数相加"""
        result = add(-1, -1)
        self.assertEqual(result, -2, "负数相加应返回正确结果")

    def test_add_zero(self) -> None:
        """测试零与零相加"""
        result = add(0, 0)
        self.assertEqual(result, 0, "零相加应返回零")

    def test_add_floats(self) -> None:
        """测试两个浮点数相加"""
        result = add(1.5, 2.5)
        self.assertEqual(result, 4.0, "浮点数相加应返回正确结果")

    def test_add_mixed_types(self) -> None:
        """测试整数与浮点数相加"""
        result = add(2, 3.0)
        self.assertEqual(result, 5.0, "整数与浮点数相加应返回浮点结果")

    def test_add_non_numbers(self) -> None:
        """测试非数字类型输入"""
        with self.assertRaises(TypeError):
            add("a", 3)  # 应该抛出TypeError异常

if __name__ == "__main__":
    unittest.main()