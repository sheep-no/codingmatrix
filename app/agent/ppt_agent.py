"""
PPT Agent - 自然语言到 PPT 大纲

功能:
- 接收自然语言描述，调用 LLM 生成结构化 JSON 大纲
- 输出符合现有 PPTX 引擎消费格式的 Schema
- 支持重试、校验、格式化回退
"""

import json
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any

from app.utils import call_llm

logger = logging.getLogger(__name__)


class SlideType(str, Enum):
    """幻灯片类型枚举"""
    TITLE = "title"
    CHAPTER = "chapter"
    CONTENT = "content"
    BULLET = "bullet"
    IMAGE = "image"
    CHART = "chart"
    END = "end"


@dataclass
class SlideOutline:
    """单页幻灯片大纲"""
    type: str
    title: str
    bullets: List[str] = field(default_factory=list)
    image_keywords: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PresentationOutline:
    """完整演示文稿大纲"""
    title: str
    slides: List[SlideOutline] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "slides": [s.to_dict() for s in self.slides],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class PPTAgent:
    """PPT Agent - 自然语言到 PPT 大纲"""

    DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
    MAX_RETRIES = 3

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.DEFAULT_MODEL

    async def generate_outline(
        self,
        topic: str,
        description: str = "",
        num_slides: int = 10,
    ) -> PresentationOutline:
        """根据自然语言输入生成 PPT 大纲"""
        prompt = self._build_prompt(topic, description, num_slides)
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                raw = await call_llm(
                    model=self.model, 
                    messages=[{"role": "system", "content": prompt}], 
                    temperature=0.7
                )
                
                outline = self._parse_and_validate(raw, topic, num_slides)
                if outline:
                    return outline
                    
            except Exception as e:
                logger.warning(f"LLM 调用失败 (尝试 {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
        
        return self._fallback_outline(topic, num_slides)

    def _build_prompt(self, topic: str, description: str, num_slides: int) -> str:
        return f"""你是一个专业的 PPT 制作助手。请根据用户输入生成结构化的 PPT 大纲。

要求:
1. 返回纯 JSON，不要任何额外文字
2. 第一页必须是 "title" 类型 (封面页)
3. 最后一页必须是 "end" 类型 (结束页)
4. 总页数必须等于 {num_slides}
5. 每頁 bullets 数量不超过 6 条，每条不超过 40 字

JSON Schema:
{{
  "title": "PPT 标题",
  "slides": [
    {{
      "type": "title|chapter|content|bullet|image|chart|end",
      "title": "页面标题",
      "bullets": ["要点1", "要点2"],
      "image_keywords": ["关键词1", "关键词2"],
      "notes": "备注 (可选)"
    }}
  ]
}}

用户输入:
主题: {topic}
描述: {description or '自由发挥'}
页数: {num_slides}

请返回 JSON:"""

    def _parse_and_validate(self, raw: str, topic: str, num_slides: int) -> Optional[PresentationOutline]:
        try:
            if "```" in raw:
                raw = raw.split("```")[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            
            data = json.loads(raw)
            
            slides_data = data.get("slides", [])
            slides = []
            valid_types = {e.value for e in SlideType}
            
            for s in slides_data:
                slide = SlideOutline(
                    type=s.get("type", "content"),
                    title=s.get("title", ""),
                    bullets=s.get("bullets", [])[:6],
                    image_keywords=s.get("image_keywords", [])[:3],
                    notes=s.get("notes", ""),
                )
                if slide.type not in valid_types:
                    slide.type = "content"
                slides.append(slide)
            
            if len(slides) < 2:
                return None
            
            if slides[0].type != "title":
                slides.insert(0, SlideOutline(type="title", title=topic or "PPT", bullets=[]))
            
            if slides[-1].type != "end":
                slides.append(SlideOutline(type="end", title="谢谢", bullets=[]))
            
            while len(slides) > num_slides:
                slides.pop(-2)
                
            return PresentationOutline(title=data.get("title", topic), slides=slides)
            
        except Exception as e:
            logger.warning(f"JSON 解析/校验失败: {e}")
            return None

    def _fallback_outline(self, topic: str, num_slides: int) -> PresentationOutline:
        slides = [
            SlideOutline(type="title", title=topic, bullets=[]),
            SlideOutline(type="chapter", title="目录", bullets=["引言", "主体", "总结"])
        ]
        
        for i in range(2, num_slides - 1):
            slides.append(SlideOutline(
                type="content",
                title=f"第 {i} 章",
                bullets=[f"要点 {i}-1", f"要点 {i}-2"]
            ))
            
        slides.append(SlideOutline(type="end", title="谢谢", bullets=[]))
        return PresentationOutline(title=topic, slides=slides)

    @staticmethod
    def adapt_for_pptx_engine(outline: PresentationOutline) -> Dict[str, Any]:
        """将 PPTAgent 输出适配为 pptx 引擎格式"""
        slides = []
        for slide in outline.slides:
            slides.append({
                "title": slide.title,
                "content": slide.bullets if slide.bullets else [slide.title],
                "slide_type": slide.type,
                "type": slide.type,
                "bullets": slide.bullets,
                "image_keywords": slide.image_keywords,
                "notes": slide.notes,
            })
        return {"title": outline.title, "slides": slides}
