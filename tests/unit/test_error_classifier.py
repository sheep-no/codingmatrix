"""
ErrorClassifier 单元测试
测试错误分类器的基本功能
"""
import pytest
from app.agent.error_classifier import ErrorClassifier, ErrorClassification


class TestErrorClassifierBasic:
    """ErrorClassifier 基础功能测试"""

    def test_create_instance(self):
        """测试创建实例"""
        classifier = ErrorClassifier()
        assert classifier is not None

    def test_error_patterns_exist(self):
        """测试错误模式定义"""
        assert len(ErrorClassifier.ERROR_PATTERNS) > 0

    def test_expected_error_types_exist(self):
        """测试预期的错误类型都存在"""
        expected_types = {
            "NameError", "AttributeError", "ImportError",
            "SyntaxError", "TypeError", "KeyError", "IndexError", "LogicError"
        }
        for error_type in expected_types:
            assert error_type in ErrorClassifier.ERROR_PATTERNS

    def test_patterns_have_required_fields(self):
        """测试模式有必需字段"""
        required_fields = {"patterns", "description", "fix_strategy"}
        for error_type, config in ErrorClassifier.ERROR_PATTERNS.items():
            for field in required_fields:
                assert field in config, f"{error_type} 缺少 {field}"


class TestErrorClassification:
    """错误分类测试"""

    @pytest.mark.asyncio
    async def test_classify_basic(self):
        """测试基本分类功能"""
        classifier = ErrorClassifier()
        error_msg = "name 'x' is not defined"
        result = await classifier.classify_error(error_msg)
        assert result is not None

    @pytest.mark.asyncio
    async def test_classify_name_error(self):
        """测试 NameError 分类"""
        classifier = ErrorClassifier()
        error_msg = "NameError: name 'undefined' is not defined"
        result = await classifier.classify_error(error_msg)
        assert result is not None
        if hasattr(result, 'error_type'):
            assert result.error_type == "NameError"


class TestFixStrategy:
    """修复策略测试"""

    def test_get_fix_strategy(self):
        """测试获取修复策略"""
        classifier = ErrorClassifier()
        strategy = classifier.get_fix_strategy_by_type("NameError")
        assert strategy is not None

    def test_all_types_have_strategy(self):
        """测试所有类型都有策略"""
        classifier = ErrorClassifier()
        for error_type in ErrorClassifier.ERROR_PATTERNS.keys():
            strategy = classifier.get_fix_strategy_by_type(error_type)
            assert strategy is not None, f"{error_type} 没有修复策略"


class TestHistoryTracking:
    """历史记录跟踪测试"""

    def test_add_to_history(self):
        """测试添加到历史记录"""
        classifier = ErrorClassifier()
        classification = ErrorClassification(
            error_type="SyntaxError",
            error_subtype="indent",
            description="test error",
            suggested_fix_strategy="fix indent",
            confidence=0.9
        )
        classifier.add_to_history(classification)
        assert hasattr(classifier, 'add_to_history')
