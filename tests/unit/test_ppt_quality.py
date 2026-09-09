from app.utils.pptx.quality import AutoReflowEngine, QualityReport, check_deck, contrast_ratio


def test_contrast_ratio_meets_body_text_threshold():
    assert contrast_ratio("#000000", "#FFFFFF") >= 4.5


def test_quality_checker_detects_overflow_overlap_and_distortion():
    report = check_deck([{
        "id": "slide-1", "layout": "content_only", "elements": [
            {"id": "title", "type": "text", "left": 1, "top": 1, "width": 4, "height": 1, "measured_height": 2},
            {"id": "body", "type": "text", "left": 1.1, "top": 1.1, "width": 4, "height": 2},
            {"id": "image", "type": "image", "left": 6, "top": 1, "width": 3, "height": 3, "source_width": 16, "source_height": 9},
        ],
    }])
    assert {issue.issue_type for issue in report.issues} >= {"text_overflow", "element_overlap", "image_distortion"}
    assert report.overall_score < 100


def test_reflow_is_bounded_and_marks_manual_review():
    slide = {"id": "slide-1", "elements": []}
    report = QualityReport()
    engine = AutoReflowEngine()
    engine.reflow(slide, [], report)
    engine.reflow(slide, [], report)
    engine.reflow(slide, [], report)
    assert report.reflow_attempts["slide-1"] == 2
    assert "slide-1" in report.manual_review_slides


def test_quality_checker_detects_capacity_and_font_floor():
    report = check_deck([{
        "id": "slide-1",
        "layout": "content_only",
        "capacity": {"max_items": 2},
        "content_block_count": 3,
        "elements": [{"id": "title", "type": "text", "font_size": 20, "left": 1, "top": 1, "width": 3, "height": 1}],
    }])
    assert {issue.issue_type for issue in report.issues} >= {"content_density", "font_size_floor"}


def test_layout_repetition_only_starts_after_two_consecutive_pages():
    report = check_deck([
        {"id": "s1", "layout": "content_only", "elements": []},
        {"id": "s2", "layout": "content_only", "elements": []},
        {"id": "s3", "layout": "content_only", "elements": []},
    ])
    assert not any(issue.slide_id == "s2" and issue.issue_type == "layout_repetition" for issue in report.issues)
    assert any(issue.slide_id == "s3" and issue.issue_type == "layout_repetition" for issue in report.issues)
