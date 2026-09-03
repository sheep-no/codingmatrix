from app.schema.ppt_outline import ContentBlock, OutlineDraft, OutlineSlide
from app.utils.pptx.semantic_planner import plan_outline, split_content_blocks


def make_outline(slides):
    return OutlineDraft(
        id="outline-1", user_id="1", version=1, title="测试", scenario="general",
        template_id="modern", slide_limit=10, slides=slides, created_at="2026-01-01T00:00:00Z",
    )


def test_planner_maps_legacy_types_and_preserves_order():
    slides = [
        OutlineSlide(id="a", position=1, slide_type="chart", title="数据", key_message="趋势", content_blocks=[ContentBlock(content="A")]),
        OutlineSlide(id="b", position=0, slide_type="content", title="要点", key_message="结论", content_blocks=[ContentBlock(content="B")]),
    ]
    plans = plan_outline(make_outline(slides))
    assert [plan.slide_id for plan in plans] == ["b", "a"]
    assert [plan.slide_type for plan in plans] == ["key_points", "data"]
    assert plans[0].content_blocks[0]["content"] == "B"


def test_planner_reports_capacity_overflow():
    slide = OutlineSlide(
        id="a", position=0, slide_type="key_points", title="标题",
        key_message="结论", content_blocks=[ContentBlock(content=str(index)) for index in range(7)],
    )
    assert plan_outline(make_outline([slide]))[0].capacity.exceeded is True


def test_split_content_blocks_keeps_source_order():
    blocks = [{"content": str(index)} for index in range(7)]
    chunks = split_content_blocks(blocks, 3)
    assert [[item["content"] for item in chunk] for chunk in chunks] == [["0", "1", "2"], ["3", "4", "5"], ["6"]]
