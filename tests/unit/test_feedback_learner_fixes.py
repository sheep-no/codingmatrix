"""回归：feedback_learner FL1（错误正则 OR 拆词误伤）与反模式拦截健壮性。"""

import re

import pytest

from app.agent.feedback_learner import FeedbackLearner, FixPattern
from app.agent.orchestrator_utils import UtilsMixin


@pytest.fixture
def learner(tmp_path):
    return FeedbackLearner(learning_dir=tmp_path)


class _StubLearner:
    def __init__(self, patterns):
        self._fix_patterns = {str(i): p for i, p in enumerate(patterns)}


class _Harness(UtilsMixin):
    def __init__(self, learner):
        self.feedback_learner = learner


def _anti_pattern(error_message: str, error_pattern: str) -> FixPattern:
    return FixPattern(
        error_type="validation_error",
        error_message=error_message,
        error_pattern=error_pattern,
        fix_description="修复",
        fix_example="",
        file_types=[".py"],
        failed_count=4,
        success_rate=0.0,
    )


class TestBuildErrorRegex:
    """FL1: 关键词应转义并串成「同时包含」，而非裸的分支关键字"""

    def test_regex_is_always_valid(self, learner):
        pattern = learner._build_error_regex("list index (out of) range [x]")

        # 未转义时 "(out of)" 会被当成分组、"[x]" 会被当成字符集
        assert re.search(pattern, "list index (out of) range [x]")

    def test_single_keyword_no_longer_blocks_requirement(self, learner):
        pattern = learner._build_error_regex("module 'flask' has no attribute 'Foo'")

        assert not re.search(pattern, "用 flask 写一个用户系统", re.IGNORECASE)

    def test_full_signature_still_matches(self, learner):
        pattern = learner._build_error_regex("module 'flask' has no attribute 'Foo'")

        assert re.search(
            pattern,
            "再次出现 module 'flask' has no attribute 'Foo'",
            re.IGNORECASE,
        )


class TestIsAntiPattern:
    """反模式拦截：单词级命中的误伤消除，非法持久化正则被跳过"""

    def test_common_word_requirement_is_not_blocked(self, learner):
        pattern = learner._build_error_regex("module 'flask' has no attribute 'Foo'")
        harness = _Harness(_StubLearner([_anti_pattern("err", pattern)]))

        assert harness._is_anti_pattern("用 flask 写一个用户系统") is False

    def test_invalid_persisted_regex_is_skipped(self):
        harness = _Harness(_StubLearner([_anti_pattern("err", "broken (pattern")]))

        # 不应抛 re.error，也不应拦截
        assert harness._is_anti_pattern("任意需求") is False

    def test_matching_requirement_is_blocked(self, learner):
        pattern = learner._build_error_regex("module 'flask' has no attribute 'Foo'")
        harness = _Harness(_StubLearner([_anti_pattern("err", pattern)]))

        assert harness._is_anti_pattern("module 'flask' has no attribute 'Foo'")


class TestDeadCodeRemoved:
    """FL3/FL4: 同步重复实现与异步包装零消费，已删除"""

    def test_sync_duplicate_and_async_wrappers_are_gone(self):
        assert not hasattr(FeedbackLearner, "_find_relevant_patterns")
        assert not hasattr(FeedbackLearner, "async_record_fix")
        assert not hasattr(FeedbackLearner, "async_save_patterns")
