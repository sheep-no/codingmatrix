# tests/test_add_function.py
import unittest
from unittest import TestCase
from src.add_function import add_function

class TestAddFunction(unittest.TestCase):
    """
    单元测试类，用于验证add_function的正确性和异常处理
    覆盖正常输入、边界值、非法输入等场景
    """

    def setUp(self):
        """测试用例初始化"""
        self.add_func = add_function
    
    def test_add_integers(self):
        """测试两个整数相加"""
        result = self.add_func(3, 5)
        self.assertEqual(result, 8, "整数相加应返回正确结果")
    
    def test_add_floats(self):
        """测试两个浮点数相加"""
        result = self.add_func(2.5, 3.7)
        self.assertEqual(result, 6.2, "浮点数相加应返回正确结果")
    
    def test_add_negative_numbers(self):
        """测试负数相加"""
        result = self.add_func(-1, -2)
        self.assertEqual(result, -3, "负数相加应返回正确结果")
    
    def test_add_zero(self):
        """测试与零相加"""
        result = self.add_func(0, 0)
        self.assertEqual(result, 0, "零相加应返回零")
        result = self.add_func(5, 0)
        self.assertEqual(result, 5, "零与数字相加应返回原数字")
    
    def test_add_mixed_types(self):
        """测试不同类型混合输入"""
        with self.assertRaises(TypeError):
            self.add_func(3, "5")  # 整数与字符串
        with self.assertRaises(TypeError):
            self.add_func("3", 5)  # 字符串与整数
        with self.assertRaises(TypeError):
            self.add_func(3.0, "5")  # 浮点数与字符串
    
    def test_add_invalid_types(self):
        """测试非法类型输入"""
        with self.assertRaises(ValueError):
            self.add_func([1, 2], 3)  # 列表与整数
        with self.assertRaises(ValueError):
            self.add_func({"a": 1}, 2)  # 字典与整数
        with self.assertRaises(ValueError):
            self.add_func(None, 4)  # None类型
    
    def test_add_with_large_numbers(self):
        """测试大整数相加"""
        result = self.add_func(10**18, 10**18)
        self.assertEqual(result, 2*10**18, "大整数相加应返回正确结果")
    
    def test_add_with_one_zero(self):
        """测试单参数为零的情况"""
        result = self.add_func(0, 5)
        self.assertEqual(result, 5, "零与数字相加应返回原数字")

if __name__ == "__main__":
    unittest.main()