"""
测试缓存审查闸门功能
"""
import pytest
from app.agent.fix_pattern_cache import FixPattern as CacheFixPattern


class TestCacheReviewGateLogic:
    """测试缓存审查闸门核心逻辑"""

    def test_is_anti_pattern_check(self):
        """测试反模式判定逻辑"""
        # 反模式：失败 >= 3 且成功率 < 0.3
        pattern1 = CacheFixPattern(
            error_signature='abc',
            error_type='syntax',
            error_subtype='indent',
            project_type='web',
            file_type='.py',
            fix_strategy='fix indent',
            model_used='qwen',
            fixed_code_snippet='pass',
            success_rate=0.2,
            usage_count=5,
            failed_count=4
        )
        assert pattern1.is_anti_pattern() is True

        # 正常模式：失败少
        pattern2 = CacheFixPattern(
            error_signature='abc',
            error_type='syntax',
            error_subtype='indent',
            project_type='web',
            file_type='.py',
            fix_strategy='fix indent',
            model_used='qwen',
            fixed_code_snippet='pass',
            success_rate=0.8,
            usage_count=5,
            failed_count=1
        )
        assert pattern2.is_anti_pattern() is False

        # 正常模式：成功率高
        pattern3 = CacheFixPattern(
            error_signature='abc',
            error_type='syntax',
            error_subtype='indent',
            project_type='web',
            file_type='.py',
            fix_strategy='fix indent',
            model_used='qwen',
            fixed_code_snippet='pass',
            success_rate=0.9,
            usage_count=10,
            failed_count=3
        )
        assert pattern3.is_anti_pattern() is False


class TestFixPatternCacheAntiPattern:
    """测试 FixPatternCache 反模式排除"""

    @pytest.fixture
    def cache(self):
        """创建 FixPatternCache 实例"""
        from app.agent.fix_pattern_cache import FixPatternCache
        import tempfile
        from pathlib import Path

        temp_file = Path(tempfile.mktemp())
        cache = FixPatternCache(cache_file=temp_file)
        yield cache
        if temp_file.exists():
            temp_file.unlink()

    def test_update_pattern_records_failure(self, cache):
        """测试 update_pattern_success 记录失败"""
        # 先记录成功创建模式
        cache.patterns['test_sig'] = CacheFixPattern(
            error_signature='test_sig',
            error_type='syntax',
            error_subtype='indent',
            project_type='web',
            file_type='.py',
            fix_strategy='fix indent',
            model_used='qwen',
            fixed_code_snippet='pass',
            success_rate=0.8,
            usage_count=5,
            failed_count=0
        )

        # 记录失败
        cache.update_pattern_success(signature='test_sig', success=False, failure_reason='修复后仍然失败')

        # 查找模式
        pattern = cache.patterns.get('test_sig')

        assert pattern is not None
        assert pattern.failed_count >= 1
        assert pattern.failure_reason == '修复后仍然失败'


class TestFeedbackLearnerAntiPattern:
    """测试 FeedbackLearner 反模式排除"""

    def test_pattern_has_failed_count_field(self):
        """测试 FixPattern 有 failed_count 字段"""
        from app.agent.feedback_learner import FixPattern

        pattern = FixPattern(
            error_type='syntax',
            error_message='test',
            error_pattern='test',
            fix_description='test',
            fix_example='',
            file_types=['.py'],
            failed_count=5,
            success_rate=0.2
        )

        assert pattern.failed_count == 5
        assert pattern.is_anti_pattern() is True


class _FakeCached:
    requirement = "生成一个待办应用"
    architecture = {"project_type": "web"}


class _RaisingReviewer:
    async def review_code(self, *_args, **_kwargs):
        raise RuntimeError("审查服务不可用")


class _HighRiskReviewer:
    async def review_code(self, *_args, **_kwargs):
        return {"risk_level": "high"}


class _LowRiskReviewer:
    async def review_code(self, *_args, **_kwargs):
        return {"risk_level": "low"}


def _gate_orchestrator(reviewer):
    from app.agent.orchestrator_utils import UtilsMixin

    class _Harness(UtilsMixin):
        def __init__(self, reviewer):
            self.reviewer = reviewer
            self.feedback_learner = None

    return _Harness(reviewer)


class TestCacheReviewGateFailClosed:
    """TG5: 审查不可用时不放行未经校验的缓存"""

    @pytest.mark.asyncio
    async def test_exception_blocks_cache(self):
        orch = _gate_orchestrator(_RaisingReviewer())
        assert await orch._cache_review_gate(_FakeCached()) is False

    @pytest.mark.asyncio
    async def test_high_risk_blocks_cache(self):
        orch = _gate_orchestrator(_HighRiskReviewer())
        assert await orch._cache_review_gate(_FakeCached()) is False

    @pytest.mark.asyncio
    async def test_low_risk_allows_cache(self):
        orch = _gate_orchestrator(_LowRiskReviewer())
        assert await orch._cache_review_gate(_FakeCached()) is True

    @pytest.mark.asyncio
    async def test_missing_reviewer_allows_cache(self):
        orch = _gate_orchestrator(None)
        assert await orch._cache_review_gate(_FakeCached()) is True
