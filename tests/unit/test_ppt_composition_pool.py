from app.utils.pptx.composition_pool import (
    LAYOUT_VARIANT_POOL,
    select_cover_variant,
    select_layout_variants,
)


def test_layout_selection_is_stable_and_avoids_adjacent_repetition():
    first = select_layout_variants("中西方神话", 20)
    second = select_layout_variants("中西方神话", 20)

    assert first == second
    assert len(first) == 20
    assert all(variant in LAYOUT_VARIANT_POOL for variant in first)
    assert all(left != right for left, right in zip(first, first[1:]))


def test_layout_selection_changes_with_topic():
    assert select_layout_variants("中西方神话", 12) != select_layout_variants("科技趋势", 12)


def test_cover_selection_is_stable_and_topic_sensitive():
    assert select_cover_variant("中西方神话") == select_cover_variant("中西方神话")
    assert select_cover_variant("中西方神话") != select_cover_variant("科技趋势")
