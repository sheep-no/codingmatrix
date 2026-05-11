# test_add.py
# 单元测试文件，验证 add.py 中的 add_numbers 函数正确性
# 项目结构：projects/orchestrator/20260502_085954_1

import unittest
from add import add_numbers

class TestAddNumbers(unittest.TestCase):
    """测试 add_numbers 函数的单元测试类"""
    
    def test_add_numbers(self):
        """测试正常数值相加的情况"""
        # 测试正数相加
        self.assertEqual(add_numbers(2, 3), 5, "正数相加应返回正确结果")
        # 测试负数相加
        self.assertEqual(add_numbers(-1, -4), -5, "负数相加应返回正确结果")
        # 测试零相加
        self.assertEqual(add_numbers(0, 0), 0, "零相加应返回零")
        # 测试浮点数相加
        self.assertEqual(add_numbers(2.5, 3.5), 6.0, "浮点数相加应返回正确结果")
        # 测试混合数值类型
        self.assertEqual(add_numbers(1, 2.5), 3.5, "整数和浮点数相加应返回正确结果")
    
    def test_add_strings(self):
        """测试字符串输入时应触发 ValueError 的情况"""
        with self.assertRaises(ValueError):
            add_numbers("2", "3")
    
    def test_add_none_values(self):
        """测试 None 输入时应触发 ValueError 的情况"""
        with self.assertRaises(ValueError):
            add_numbers(None, 5)
        with self.assertRaises(ValueError):
            add_numbers(5, None)
    
    def test_add_non_numeric(self):
        """测试非数字类型输入时应触发 ValueError 的情况"""
        with self.assertRaises(ValueError):
            add_numbers("abc", 5)
        with self.assertRaises(ValueError):
            add_numbers([1, 2], 3)
        with self.assertRaises(ValueError):
            add_numbers({4: 5}, 3)

if __name__ == "__main__":
    unittest.main()