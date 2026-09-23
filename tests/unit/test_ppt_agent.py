"""PPTAgent 单元测试

覆盖 PPT1：`modify_outline` 不再把修改前的页数当作目标页数强制裁剪/补齐，
增删页修改请求能真正生效且不丢失原有内容页。
"""
import json
from unittest.mock import AsyncMock, patch

from app.agent.ppt_agent import PPTAgent


def _slide(title, slide_type="content"):
    return {"type": slide_type, "title": title, "bullets": [f"{title}-要点"]}


def _llm_response(slides):
    payload = {"title": "演示", "slides": slides}
    return {
        "choices": [
            {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        ]
    }


EXISTING_OUTLINE = {
    "title": "演示",
    "slides": [
        _slide("封面", "title"),
        _slide("一"),
        _slide("二"),
        _slide("谢谢", "end"),
    ],
}


class TestModifyOutlinePageCount:

    async def test_add_page_preserves_existing_slides(self):
        modified = [
            _slide("封面", "title"),
            _slide("一"),
            _slide("新增页"),
            _slide("二"),
            _slide("谢谢", "end"),
        ]
        with patch(
            "app.agent.ppt_agent.call_llm",
            new=AsyncMock(return_value=_llm_response(modified)),
        ) as mock_llm:
            outline = await PPTAgent().modify_outline(EXISTING_OUTLINE, "加一页")

        assert mock_llm.await_count == 1
        assert len(outline.slides) == 5
        assert [s.title for s in outline.slides] == ["封面", "一", "新增页", "二", "谢谢"]

    async def test_delete_page_not_padded_back(self):
        modified = [_slide("封面", "title"), _slide("谢谢", "end")]
        with patch(
            "app.agent.ppt_agent.call_llm",
            new=AsyncMock(return_value=_llm_response(modified)),
        ):
            outline = await PPTAgent().modify_outline(EXISTING_OUTLINE, "只保留封面和结束页")

        assert [s.title for s in outline.slides] == ["封面", "谢谢"]

    async def test_falls_back_to_existing_outline_when_llm_fails(self):
        with patch(
            "app.agent.ppt_agent.call_llm",
            new=AsyncMock(side_effect=RuntimeError("llm down")),
        ), patch.object(PPTAgent, "MAX_RETRIES", 1):
            outline = await PPTAgent().modify_outline(EXISTING_OUTLINE, "改一下")

        assert [s.title for s in outline.slides] == ["封面", "一", "二", "谢谢"]


class TestFallbackOutlineBounds:

    def test_single_slide(self):
        outline = PPTAgent()._fallback_outline("主题", 1)
        assert len(outline.slides) == 1
        assert outline.slides[0].type == "title"

    def test_two_slides(self):
        outline = PPTAgent()._fallback_outline("主题", 2)
        assert [s.type for s in outline.slides] == ["title", "end"]
