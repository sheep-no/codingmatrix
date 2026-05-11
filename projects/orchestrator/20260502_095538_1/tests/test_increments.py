import unittest
from typing import List
from src.increment_generator import generate_increments

class TestIncrementGenerator(unittest.TestCase):
    """测试增量生成功能的单元测试类
    
    验证不同参数情况下增量生成的正确性，包括正常流程、边界条件和异常处理
    """

    def test_normal_increment(self):
        """测试正常增量生成场景"""
        result = generate_increments(1, 2, 5)
        self.assertEqual(result, [1, 3, 5, 7, 9])
        # 验证等差数列生成逻辑的正确性，步长为正数

    def test_negative_start(self):
        """测试起始值为负数的增量生成场景"""
        result = generate_increments(-2, 3, 3)
        self.assertEqual(result, [-2, 1, 4])
        # 验证负数起始点的处理逻辑

    def test_negative_step(self):
        """测试步长为负数的逆向增量生成场景"""
        result = generate_increments(10, -2, 4)
        self.assertEqual(result, [10, 8, 6, 4])
        # 验证逆向数列生成逻辑的正确性

    def test_zero_count(self):
        """测试count为0时的边界情况"""
        result = generate_increments(1, 2, 0)
        self.assertEqual(result, [])
        # 验证当需要生成0个元素时返回空列表

    def test_negative_count(self):
        """测试count为负数时的异常处理"""
        with self.assertRaises(ValueError):
            generate_increments(1, 2, -1)
        # 验证负数count参数的异常捕获

    def test_zero_step(self):
        """测试步长为0时的异常处理"""
        with self.assertRaises(ValueError):
            generate_increments(1, 0, 5)
        # 验证步长为0时的异常捕获，避免无限循环

    def test_single_element(self):
        """测试生成单个元素的场景"""
        result = generate_increments(5, 2, 1)
        self.assertEqual(result, [5])
        # 验证count=1时的特殊处理

    def test_large_count(self):
        """测试大数量生成场景"""
        result = generate_increments(0, 1, 100)
        self.assertListEqual(result, list(range(100)))
        # 验证大数量生成时的性能边界

    def test_type_validation(self):
        """测试参数类型验证"""
        with self.assertRaises(TypeError):
            generate_increments("1", 2, 5)
        with self.assertRaises(TypeError):
            generate_increments(1, "2", 5)
        with self.assertRaises(TypeError):
            generate_increments(1, 2, "5")
        # 验证参数类型校验逻辑

if __name__ == '__main__':
    unittest.main()