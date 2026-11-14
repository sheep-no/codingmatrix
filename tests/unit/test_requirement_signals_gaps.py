"""requirement_signals 空输入与正关键词补测。"""

from app.agent.requirement_signals import (
    find_keyword_spans,
    first_positive_span,
    has_positive_keyword,
    positive_keywords,
)


def test_empty_inputs_return_no_spans():
    assert find_keyword_spans("", "vue") == []
    assert find_keyword_spans("vue", "") == []


def test_cjk_keyword_found_repeatedly():
    spans = find_keyword_spans("用React，不用React", "React")
    assert len(spans) == 2


def test_positive_keywords_filters_negated():
    assert positive_keywords("不要 Vue，使用 React", ["Vue", "React"]) == ["React"]


def test_positive_keywords_empty_iterable():
    assert positive_keywords("anything", []) == []


def test_has_positive_keyword_false_for_negated_only():
    assert has_positive_keyword("不要 Vue", ["Vue"]) is False


def test_first_positive_span_skips_negated_hit():
    span = first_positive_span("不要 Vue，使用 Vue", "Vue")
    assert span is not None
    assert span[0] > 3


def test_non_ascii_keyword_uses_substring_match():
    spans = find_keyword_spans("café au lait", "café")
    assert spans == [(0, 4)]


def test_keyword_at_start_is_not_negated():
    from app.agent.requirement_signals import is_span_negated

    assert is_span_negated("Vue is required", 0) is False
