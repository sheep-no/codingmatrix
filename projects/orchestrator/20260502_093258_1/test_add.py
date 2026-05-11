# test_add.py
# 单元测试文件，用于验证 add.py 中的 add 函数正确性
# 测试覆盖正常情况、边界情况和异常处理

import unittest
from add import add

class TestAdd(unittest.TestCase):
    """
    测试 add 函数的单元测试类
    验证两个数相加的功能是否符合预期
    """

    def test_add_integers(self) -> None:
        """
        测试两个整数相加的正常情况
        正数相加应返回正确结果
        """
        result = add(3, 5)
        self.assertEqual(result, 8, "整数相加结果应为 8")

    def test_add_floats(self) -> None:
        """
        测试两个浮点数相加的正常情况
        浮点数相加应返回正确结果
        """
        result = add(2.5, 3.7)
        self.assertAlmostEqual(result, 6.2, places=1, msg="浮点数相加结果应为 6.2")

    def test_add_negative_numbers(self) -> None:
        """
        测试两个负数相加的正常情况
        负数相加应返回正确结果
        """
        result = add(-4, -6)
        self.assertEqual(result, -10, "负数相加结果应为 -10")

    def test_add_zero(self) -> None:
        """
        测试与零相加的正常情况
        零与任意数相加应返回该数
        """
        self.assertEqual(add(0, 10), 10, "零与10相加应返回10")
        self.assertEqual(add(5, 0), 5, "5与零相加应返回5")

    def test_add_non_numeric(self) -> None:
        """
        测试非数字类型参数的异常处理
        非数字输入应引发 TypeError
        """
        with self.assertRaises(TypeError):
            add("a", 5)
        with self.assertRaises(TypeError):
            add(3, ["b", "c"])

if __name__ == "__main__":
    unittest.main(verbosity=2)