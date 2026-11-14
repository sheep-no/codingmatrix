"""pptx quality 校验分支与 AutoReflowEngine 动作补测。"""

import pytest

from app.utils.pptx.quality import (
    AutoReflowEngine,
    QualityIssue,
    QualityReport,
    _rgb,
    check_deck,
    check_slide,
    contrast_ratio,
)


def test_overall_score_empty_and_average():
    assert QualityReport().overall_score == 100.0
    report = QualityReport(slide_scores={"a": 90.0, "b": 80.0})
    assert report.overall_score == 85.0


def test_rgb_invalid_and_short_values():
    assert _rgb("xyz") == (0.0, 0.0, 0.0)
    assert _rgb("#fff") == (0.0, 0.0, 0.0)
    assert _rgb("#000000") == (0.0, 0.0, 0.0)


def test_rgb_bright_channel_uses_gamma_curve():
    value = _rgb("#FFFFFF")
    assert all(abs(c - 1.0) < 1e-9 for c in value)


def test_contrast_ratio_hex_prefix_optional():
    assert contrast_ratio("000000", "FFFFFF") == contrast_ratio("#000000", "#FFFFFF")


def test_check_slide_safe_margin_and_contrast():
    issues = check_slide({
        "id": "s1",
        "elements": [
            {"id": "a", "type": "shape", "left": 0, "top": 1, "width": 1, "height": 1},
            {"id": "t", "type": "text", "left": 1, "top": 1, "width": 2, "height": 1,
             "foreground": "#777777", "background": "#888888", "font_size": 30},
        ],
    })
    kinds = {i.issue_type for i in issues}
    assert "unsafe_margin" in kinds
    assert "low_contrast" in kinds


def test_contrast_threshold_is_stricter_for_small_text():
    issue = check_slide({
        "id": "s1",
        "elements": [{
            "id": "t", "type": "text", "left": 1, "top": 1, "width": 2, "height": 1,
            "foreground": "#888888", "background": "#FFFFFF", "font_size": 12,
        }],
    })
    assert any(i.issue_type == "low_contrast" for i in issue)


def test_small_text_at_large_size_passes_threshold():
    issues = check_slide({
        "id": "s1",
        "elements": [{
            "id": "t", "type": "text", "left": 1, "top": 1, "width": 2, "height": 1,
            "foreground": "#767676", "background": "#FFFFFF", "font_size": 30,
        }],
    })
    assert not any(i.issue_type == "low_contrast" for i in issues)


def test_font_floor_heading_role_and_default():
    issues = check_slide({
        "id": "s1",
        "elements": [
            {"id": "h1", "type": "text", "role": "heading", "font_size": 20,
             "left": 1, "top": 1, "width": 3, "height": 1},
            {"id": "body", "type": "text", "font_size": 10,
             "left": 1, "top": 3, "width": 3, "height": 1},
        ],
    })
    floors = [i for i in issues if i.issue_type == "font_size_floor"]
    assert {i.element_ids for i in floors} == {("h1",), ("body",)}


def test_font_floor_default_size_passes():
    issues = check_slide({
        "id": "s1",
        "elements": [{
            "id": "body", "type": "text",
            "left": 1, "top": 1, "width": 3, "height": 1,
        }],
    })
    assert not any(i.issue_type == "font_size_floor" for i in issues)


def test_image_distortion_skipped_when_cropped():
    issues = check_slide({
        "id": "s1",
        "elements": [{
            "id": "img", "type": "image", "left": 1, "top": 1,
            "width": 3, "height": 3, "source_width": 16, "source_height": 9,
            "cropped": True,
        }],
    })
    assert not any(i.issue_type == "image_distortion" for i in issues)


def test_image_without_source_dimensions_ignored():
    issues = check_slide({
        "id": "s1",
        "elements": [{
            "id": "img", "type": "image", "left": 1, "top": 1,
            "width": 3, "height": 3,
        }],
    })
    assert not any(i.issue_type == "image_distortion" for i in issues)


def test_image_zero_height_uses_epsilon():
    issues = check_slide({
        "id": "s1",
        "elements": [{
            "id": "img", "type": "image", "left": 1, "top": 1,
            "width": 3, "height": 0, "source_width": 4, "source_height": 3,
        }],
    })
    assert any(i.issue_type == "image_distortion" for i in issues)


def test_overlap_skips_decorative_and_zero_area():
    issues = check_slide({
        "id": "s1",
        "elements": [
            {"id": "deco", "type": "shape", "decorative": True, "left": 1, "top": 1, "width": 2, "height": 2},
            {"id": "a", "type": "shape", "left": 1, "top": 1, "width": 2, "height": 2},
            {"id": "b", "type": "shape", "decorative": True, "left": 1, "top": 1, "width": 2, "height": 2},
            {"id": "zero", "type": "shape", "left": 1, "top": 1, "width": 0, "height": 0},
        ],
    })
    assert not any(i.issue_type == "element_overlap" for i in issues)


def test_overlap_detected_for_non_decorative():
    issues = check_slide({
        "id": "s1",
        "elements": [
            {"id": "a", "type": "shape", "left": 1, "top": 1, "width": 2, "height": 2},
            {"id": "b", "type": "shape", "left": 1, "top": 1, "width": 2, "height": 2},
        ],
    })
    assert any(i.issue_type == "element_overlap" for i in issues)


def test_capacity_and_layout_repetition():
    issues = check_slide(
        {"id": "s1", "layout": "x", "capacity": {"max_items": 1},
         "content_blocks": [{}, {}], "elements": []},
        previous_layout="x",
        repeated_layouts=3,
    )
    kinds = {i.issue_type for i in issues}
    assert "content_density" in kinds
    assert "layout_repetition" in kinds


def _issue(action, element_ids=(), fault=None):
    return QualityIssue("t", "s1", "high", "m", tuple(element_ids), action)


def test_reflow_reduce_content_blocks():
    engine = AutoReflowEngine()
    report = QualityReport()
    slide = {
        "id": "s1", "preserve_content": False,
        "capacity": {"max_items": 2},
        "content_blocks": [1, 2, 3, 4],
    }
    fixed = engine.reflow(slide, [_issue("reduce_content_blocks")], report)
    assert fixed["content_blocks"] == [1, 2]
    assert fixed["content_block_count"] == 2


def test_reflow_reduce_content_respects_preserve_flag():
    engine = AutoReflowEngine()
    report = QualityReport()
    slide = {"id": "s1", "preserve_content": True, "content_blocks": [1, 2, 3]}
    fixed = engine.reflow(slide, [_issue("reduce_content_blocks")], report)
    assert fixed["content_blocks"] == [1, 2, 3]
    assert "s1" in report.manual_review_slides


def test_reflow_switch_layout_uses_fallback():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "fallback_layout": "two_column"},
        [_issue("switch_layout")],
        QualityReport(),
    )
    assert fixed["layout"] == "two_column"


def test_reflow_switch_layout_default():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1"}, [_issue("switch_layout")], QualityReport()
    )
    assert fixed["layout"] == "content_only"


def test_reflow_raise_font_size_title_and_others():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": [
            {"id": "title", "font_size": 10},
            {"id": "body", "font_size": 12},
            {"id": "other", "font_size": 30},
        ]},
        [_issue("raise_font_size", ("title", "body", "missing"))],
        QualityReport(),
    )
    by_id = {e["id"]: e for e in fixed["elements"]}
    assert by_id["title"]["font_size"] == 24
    assert by_id["body"]["font_size"] == 14
    assert by_id["other"]["font_size"] == 30


def test_reflow_move_into_safe_area():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "safe_margin": 1.0, "elements": [
            {"id": "a", "left": 0.1, "top": 0.2},
            {"id": "b", "left": 5, "top": 5},
        ]},
        [_issue("move_into_safe_area", ("a",))],
        QualityReport(),
    )
    by_id = {e["id"]: e for e in fixed["elements"]}
    assert (by_id["a"]["left"], by_id["a"]["top"]) == (1.0, 1.0)
    assert (by_id["b"]["left"], by_id["b"]["top"]) == (5, 5)


def test_reflow_adjust_text_color_light_and_dark_background():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": [
            {"id": "light", "background": "#FFFFFF"},
            {"id": "plain", "background": "FFFFFF"},
            {"id": "dark", "background": "#123456"},
            {"id": "missing"},
        ]},
        [_issue("adjust_text_color", ("light", "plain", "dark", "missing"))],
        QualityReport(),
    )
    by_id = {e["id"]: e for e in fixed["elements"]}
    assert by_id["light"]["foreground"] == "#000000"
    assert by_id["plain"]["foreground"] == "#000000"
    assert by_id["dark"]["foreground"] == "#FFFFFF"
    assert by_id["missing"]["foreground"] == "#000000"


def test_reflow_preserve_aspect_ratio_marks_cropped():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": [{"id": "img"}]},
        [_issue("preserve_aspect_ratio", ("img",))],
        QualityReport(),
    )
    assert fixed["elements"][0]["cropped"] is True


def test_reflow_unknown_action_is_noop():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": []},
        [_issue("unknown_action")],
        QualityReport(),
    )
    assert fixed["elements"] == []


def test_reflow_does_not_mutate_original_slide():
    slide = {"id": "s1", "elements": [{"id": "a", "left": 0, "top": 0}]}
    AutoReflowEngine().reflow(
        slide, [_issue("move_into_safe_area", ("a",))], QualityReport()
    )
    assert slide["elements"][0]["left"] == 0


def test_reflow_manual_review_added_only_once_at_limit():
    report = QualityReport(reflow_attempts={"s1": 2})
    AutoReflowEngine().reflow({"id": "s1"}, [], report)
    AutoReflowEngine().reflow({"id": "s1"}, [], report)
    assert report.manual_review_slides.count("s1") == 1


def test_check_deck_uses_slide_id_fallback():
    report = check_deck([{"slide_id": "legacy", "elements": []}])
    assert "legacy" in report.slide_scores


def test_reflow_preserve_content_already_flagged_skips_duplicate():
    report = QualityReport(manual_review_slides=["s1"])
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "preserve_content": True, "content_blocks": [1]},
        [_issue("reduce_content_blocks")],
        report,
    )
    assert fixed["content_blocks"] == [1]
    assert report.manual_review_slides.count("s1") == 1


def test_reflow_adjust_text_color_skips_non_matching_between_matches():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": [
            {"id": "a", "background": "#FFFFFF"},
            {"id": "skip", "background": "#FFFFFF"},
            {"id": "b", "background": "#000000"},
        ]},
        [_issue("adjust_text_color", ("a", "b"))],
        QualityReport(),
    )
    by_id = {e["id"]: e for e in fixed["elements"]}
    assert "foreground" not in by_id["skip"]
    assert by_id["a"]["foreground"] == "#000000"
    assert by_id["b"]["foreground"] == "#FFFFFF"


def test_reflow_preserve_aspect_ratio_skips_non_matching_between_matches():
    fixed = AutoReflowEngine().reflow(
        {"id": "s1", "elements": [
            {"id": "a"}, {"id": "skip"}, {"id": "b"},
        ]},
        [_issue("preserve_aspect_ratio", ("a", "b"))],
        QualityReport(),
    )
    by_id = {e["id"]: e for e in fixed["elements"]}
    assert "cropped" not in by_id["skip"]
    assert by_id["a"]["cropped"] is True
