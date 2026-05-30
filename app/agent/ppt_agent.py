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
from app.agent.architect_json_parser import ArchitectJsonParser

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

    # PPT 专用模型配置 (按优先级排序)
    # 使用 SiliconFlow 中可用的模型
    DEFAULT_MODEL = "Qwen/Qwen3.5-4B"
    MAX_RETRIES = 3

    def __init__(self, model: Optional[str] = None, quality: str = "balanced"):
        """
        初始化 PPT Agent
        
        Args:
            model: 自定义模型名称
            quality: 质量等级 (high_quality/balanced/fast/creative) - 保留用于未来扩展
        """
        self.model = model or self.DEFAULT_MODEL

    async def generate_outline(
        self,
        topic: str,
        description: str = "",
        num_slides: int = 10,
        api_key_token: Optional[str] = None,
    ) -> PresentationOutline:
        """根据自然语言输入生成 PPT 大纲"""
        prompt = self._build_prompt(topic, description, num_slides)
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                raw = await call_llm(
                    model=self.model,
                    prompt=prompt,
                    system_prompt="你是一个专业的 PPT 制作助手。请根据用户输入生成结构化的 PPT 大纲。只返回纯 JSON，不要任何额外文字。",
                    temperature=0.7,
                    api_key_token=api_key_token,
                )
                
                # 从响应中提取文本
                if isinstance(raw, dict):
                    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                else:
                    content = str(raw)
                
                # 尝试解析 JSON（含 LLM 兜底）
                outline = await self._parse_with_llm_fallback(content, topic, num_slides, api_key_token)
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

    async def _parse_with_llm_fallback(
        self, 
        raw: str, 
        topic: str, 
        num_slides: int,
        api_key_token: Optional[str] = None
    ) -> Optional[PresentationOutline]:
        """
        尝试解析 JSON，失败时使用 LLM 辅助提取
        
        Args:
            raw: 原始文本
            topic: PPT 主题
            num_slides: 页数
            api_key_token: API key
            
        Returns:
            PresentationOutline 或 None
        """
        try:
            # 第一步：使用强健的 JSON 解析器
            parser = ArchitectJsonParser()
            data = parser.safe_parse_json(raw)
            return self._validate_outline(data, topic, num_slides)
        except ValueError:
            logger.warning("JSON 解析失败，尝试 LLM 辅助提取")
            
            # 第二步：使用 LLM 辅助提取 JSON
            extracted = await self._extract_json_with_llm(raw, api_key_token)
            if extracted:
                return self._validate_outline(extracted, topic, num_slides)
            
            logger.warning("LLM 辅助提取失败")
            return None

    async def _extract_json_with_llm(
        self, 
        raw_text: str, 
        api_key_token: Optional[str] = None
    ) -> Optional[Dict]:
        """
        使用 LLM 从非标准输出中提取 JSON
        
        Args:
            raw_text: 原始文本
            api_key_token: API key
            
        Returns:
            解析后的 JSON 字典或 None
        """
        extract_prompt = f"""请将以下文本转换为标准 JSON 格式：

原始文本：
{raw_text[:3000]}

要求：
1. 只输出 JSON，不要包含其他内容
2. 确保 JSON 格式正确
3. 必须包含 title 和 slides 字段
4. slides 数组中的每个对象必须包含 type 和 title 字段
5. type 只能是：title, chapter, content, bullet, image, chart, end

JSON Schema：
{{
  "title": "PPT 标题",
  "slides": [
    {{
      "type": "title|chapter|content|bullet|image|chart|end",
      "title": "页面标题",
      "bullets": ["要点1", "要点2"],
      "image_keywords": ["关键词1"],
      "notes": "备注"
    }}
  ]
}}"""

        try:
            response = await call_llm(
                model=self.model,
                prompt=extract_prompt,
                system_prompt="你是一个 JSON 修复助手。只输出修复后的 JSON，不要任何额外文字。",
                stream=False,
                max_tokens=4096,
                temperature=0.3,
                api_key_token=api_key_token,
            )
            
            # 从响应中提取文本
            if isinstance(response, dict):
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                content = str(response)
            
            # 使用 ArchitectJsonParser 解析
            parser = ArchitectJsonParser()
            return parser.safe_parse_json(content)
        except Exception as e:
            logger.error(f"LLM 辅助提取 JSON 失败: {e}")
            return None

    def _parse_and_validate(self, raw: str, topic: str, num_slides: int) -> Optional[PresentationOutline]:
        try:
            # 使用强健的 JSON 解析器
            parser = ArchitectJsonParser()
            data = parser.safe_parse_json(raw)
            return self._validate_outline(data, topic, num_slides)
        except ValueError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return None

    def _validate_outline(self, data: Dict, topic: str, num_slides: int) -> Optional[PresentationOutline]:
        """验证并转换 JSON 数据为 PresentationOutline"""
        try:
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
            logger.warning(f"大纲验证失败: {e}")
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
