"""
视觉分析模块 - 多模态 AI 分析 PPT 内容并决策图片需求

功能：
1. 分析每页内容，判断是否需要图片
2. 确定图片类型（照片、图表、图标、装饰）
3. 描述图片内容需求
4. 规划图片位置和大小
5. 决策文字样式（字体、颜色、大小）
6. 支持多图片装饰
"""
import json
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ImageType(Enum):
    """图片类型枚举"""
    NONE = "none"           # 不需要图片
    PHOTO = "photo"         # 照片/真实图片
    ILLUSTRATION = "illustration"  # 插画/图解
    CHART = "chart"         # 图表
    ICON = "icon"           # 图标
    BACKGROUND = "background"  # 背景图
    DIAGRAM = "diagram"     # 流程图/示意图
    DECORATION = "decoration"  # 装饰图片


class ImagePosition(Enum):
    """图片位置枚举"""
    LEFT = "left"           # 左侧
    RIGHT = "right"         # 右侧
    CENTER = "center"       # 居中
    TOP = "top"             # 顶部
    TOP_RIGHT = "top-right"  # 右上
    TOP_LEFT = "top-left"   # 左上
    BOTTOM = "bottom"       # 底部
    BACKGROUND = "background"  # 背景
    CORNER = "corner"       # 角落
    INLINE = "inline"       # 行内嵌入


class FontStyle(Enum):
    """字体样式枚举"""
    HARMONYOS_SANS = "HarmonyOS Sans SC"      # 鸿蒙字体（默认）
    Microsoft_YaHei = "微软雅黑"
    SIMHEI = "黑体"
    SIMKAI = "楷体"
    SIMLI = "隶书"
    FANGZHENG = "方正舒体"
    YOUYUAN = "幼圆"
    Arial = "Arial"
    Times_New_Roman = "Times New Roman"
    Georgia = "Georgia"


class FontWeight(Enum):
    """字重枚举"""
    NORMAL = "normal"
    MEDIUM = "medium"
    BOLD = "bold"


class TextAlignment(Enum):
    """文字对齐枚举"""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass
class ImageDecision:
    """单张图片的决策"""
    image_type: ImageType = ImageType.NONE
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    position: ImagePosition = ImagePosition.RIGHT
    width_ratio: float = 0.4  # 占幻灯片宽度的比例
    opacity: float = 1.0  # 透明度
    is_decoration: bool = False  # 是否是装饰图片


@dataclass
class TextStyle:
    """文字样式"""
    font_family: str = "微软雅黑"
    font_size: int = 24
    font_color: str = "333333"  # 十六进制颜色
    font_weight: str = "normal"  # normal, medium, bold
    alignment: str = "left"  # left, center, right
    is_italic: bool = False
    underline: bool = False


@dataclass
class TitleStyle:
    """标题样式"""
    font_family: str = "微软雅黑"
    font_size: int = 44
    font_color: str = "004296"  # 主色
    font_weight: str = "bold"
    alignment: str = "left"


@dataclass
class BulletStyleConfig:
    """列表样式"""
    style: str = "circle"  # circle, square, number, icon, arrow
    color: str = "FF6600"  # 橙色
    indent_level1: int = 0  # 第一级缩进
    indent_level2: int = 30  # 第二级缩进


@dataclass
class SlideVisualDecision:
    """单页幻灯片的视觉决策"""
    slide_index: int
    title: str
    content_summary: str
    
    # 多图片决策
    images: List[ImageDecision] = field(default_factory=list)
    
    # 标题样式
    title_style: TitleStyle = field(default_factory=TitleStyle)
    
    # 内容文字样式
    content_style: TextStyle = field(default_factory=TextStyle)
    
    # 列表样式
    bullet_style: BulletStyleConfig = field(default_factory=BulletStyleConfig)
    
    # 布局
    text_layout: str = "right"  # left, right, center, full
    has_separator_line: bool = True  # 分隔线
    separator_color: str = "4A90D9"  # 分隔线颜色
    
    # 高亮词
    highlight_words: List[str] = field(default_factory=list)
    highlight_color: str = "FF6600"  # 高亮颜色
    
    # 装饰决策
    add_decoration: bool = False
    decoration_style: str = "minimal"  # minimal, rich, corporate
    corner_decoration: bool = True
    background_decoration: bool = False
    
    reasoning: str = ""  # 决策理由
    
    @property
    def need_image(self) -> bool:
        return len(self.images) > 0 and any(img.image_type != ImageType.NONE for img in self.images)
    
    def get_main_image(self) -> Optional[ImageDecision]:
        """获取主图片（第一张非装饰图片）"""
        for img in self.images:
            if img.image_type != ImageType.NONE and not img.is_decoration:
                return img
        return self.images[0] if self.images else None


@dataclass
class PPTVisualPlan:
    """整体 PPT 的视觉规划"""
    title: str
    theme: str  # 主题风格：education, business, creative, minimal
    
    # 每页决策
    slides: List[SlideVisualDecision] = field(default_factory=list)
    
    # 整体风格
    color_scheme: str = "blue"  # blue, green, orange, purple, gray
    font_preference: str = "modern"  # modern, classic, playful
    
    # 视觉一致性
    maintain_consistency: bool = True
    use_same_layout_pattern: bool = True
    
    # 元信息
    total_slides: int = 0
    slides_needing_images: int = 0
    
    def __post_init__(self):
        self.total_slides = len(self.slides)
        self.slides_needing_images = sum(1 for s in self.slides if s.need_image)


class VisualAnalyzer:
    """视觉分析器 - 使用多模态 AI 分析内容并做出视觉决策"""
    
    # 可用的多模态模型（内置模型）
    MULTIMODAL_MODELS = [
        "Qwen/Qwen3.5-4B",  # 主力视觉模型
    ]
    
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self.MULTIMODAL_MODELS[0]
    
    async def analyze_ppt_content(
        self, 
        title: str, 
        slides_content: List[Dict[str, Any]],
        theme: str = "education"
    ) -> PPTVisualPlan:
        """
        分析 PPT 内容，生成视觉规划
        
        Args:
            title: PPT 标题
            slides_content: 每页幻灯片内容，格式为 [{"title": "...", "content": [...]}, ...]
            theme: 主题风格
        
        Returns:
            PPTVisualPlan: 视觉规划对象
        """
        # 构建分析提示词
        prompt = self._build_analysis_prompt(title, slides_content, theme)
        
        # 调用多模态模型进行分析
        from app.utils import call_llm
        
        try:
            response = await call_llm(
                model=self.model_name,
                prompt=prompt,
                stream=False,
                max_tokens=4096,
                temperature=0.3
            )
            
            # 解析模型返回
            analysis_result = self._parse_analysis_response(response)
            
            # 构建视觉规划
            visual_plan = self._build_visual_plan(title, slides_content, analysis_result, theme)
            
            logger.info(f"视觉分析完成 | slides={len(slides_content)} | need_images={visual_plan.slides_needing_images}")
            
            return visual_plan
            
        except Exception as e:
            logger.error(f"视觉分析失败: {str(e)}")
            # 返回默认规划（不使用图片）
            return self._create_default_plan(title, slides_content, theme)
    
    def _build_analysis_prompt(
        self, 
        title: str, 
        slides_content: List[Dict[str, Any]],
        theme: str
    ) -> str:
        """构建分析提示词"""
        
        slides_text = ""
        for i, slide in enumerate(slides_content, 1):
            slide_title = slide.get("title", f"第{i}页")
            content = slide.get("content", [])
            if isinstance(content, list):
                content_text = "\n".join(f"- {c}" for c in content[:5])  # 最多5条
            else:
                content_text = str(content)[:200]
            
            slides_text += f"""
幻灯片 {i}: {slide_title}
内容:
{content_text}
---
"""
        
        prompt = f"""你是一个专业的 PPT 视觉设计师。请分析以下 PPT 内容，为每页决定最优的视觉呈现方式。

## PPT 信息
标题: {title}
主题风格: {theme}

## 幻灯片内容
{slides_text}

## 重要规则

### 1. 图片决策
- **可以有0-N张图片**，包括：
  - 主图片：配合内容的主题图片
  - 装饰图片：角落、边缘的装饰元素
  - 图标：列表项前面的图标
- 每张图片需要指定：type、position、width_ratio
- 图片类型：photo/illustration/chart/icon/diagram/decoration
- 图片位置：left/right/center/top/top-right/top-left/bottom/corner/inline

### 2. 文字样式决策
- **标题**：font_family（字体）、font_size（44左右）、font_color（主色）、font_weight（bold）
- **正文**：font_family、font_size（20-28）、font_color（深灰色）
- **字体可选**：微软雅黑、黑体、楷体、隶书、幼圆、Arial
- **颜色可选**：主色004296、辅色4A90D9、橙色FF6600、深灰333333

### 3. 列表样式
- bullet_style：circle（圆点）、arrow（箭头）、number（数字）、icon
- 缩进层级

### 4. 装饰决策
- corner_decoration：角落装饰
- separator_line：分隔线
- background_decoration：背景装饰

## 输出格式（**严格 JSON - 必须遵循以下格式，禁止尾随逗号**）

请返回纯 JSON，不要包含任何解释：
{{
  "slides_analysis": [
    {{
      "slide_index": 1,
      "images": [
        {{
          "image_type": "illustration",
          "description": "英文图片描述",
          "keywords": ["关键词1", "关键词2"],
          "position": "left",
          "width_ratio": 0.45,
          "is_decoration": false
        }}
      ],
      "title_style": {{
        "font_family": "微软雅黑",
        "font_size": 44,
        "font_color": "004296",
        "font_weight": "bold"
      }},
      "content_style": {{
        "font_family": "微软雅黑",
        "font_size": 22,
        "font_color": "333333"
      }},
      "bullet_style": {{
        "style": "circle",
        "color": "FF6600"
      }},
      "text_layout": "right",
      "has_separator_line": true,
      "separator_color": "4A90D9",
      "highlight_words": ["重点词1"],
      "highlight_color": "FF6600",
      "add_decoration": true,
      "decoration_style": "minimal",
      "corner_decoration": true,
      "reasoning": "因为...所以..."
    }}
  ],
  "overall_style": {{
    "color_scheme": "blue",
    "layout_pattern": "alternating"
  }}
}}

**严格遵守以下规则**：
1. **禁止尾随逗号**：`{{"a": 1, "b": 2,}}` 错误，应为 `{{"a": 1, "b": 2}}`
2. **禁止多余逗号**：`[1, 2, 3,]` 错误，应为 `[1, 2, 3]`
3. **使用双引号**：所有字符串必须用双引号包裹
4. **布尔值小写**：true/false（不是 True/False）
5. **数组和对象正确闭合**：所有 `{{` 对应 `}}`，所有 `[` 对应 `]`"""
        
        return prompt
    
    def _parse_analysis_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """解析模型返回的响应"""
        try:
            # 处理不同的响应格式
            if isinstance(response, dict):
                # SiliconFlow 标准格式
                if "choices" in response:
                    content = response["choices"][0]["message"]["content"]
                elif "text" in response:
                    content = response["text"]
                else:
                    content = str(response)
            else:
                content = str(response)

            # 尝试提取 JSON
            # 可能包含在 markdown 代码块中
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            # 尝试解析 JSON，如果失败则尝试修复常见格式错误
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 直接解析失败，尝试修复格式: {e}")
                # 修复常见的 JSON 格式错误
                fixed_content = self._fix_json_format(content)
                try:
                    result = json.loads(fixed_content)
                except json.JSONDecodeError:
                    # 如果仍然失败，尝试用正则提取关键数据
                    logger.warning("JSON 修复也失败，尝试正则提取")
                    result = self._extract_json_by_regex(content)
            return result

        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            return {"slides_analysis": [], "overall_style": {}}

    def _fix_json_format(self, content: str) -> str:
        """修复常见的 JSON 格式错误"""
        import re

        # 移除尾随逗号（在 } 或 ] 前的逗号）
        content = re.sub(r',(\s*[}\]])', r'\1', content)

        # 修复 Python 布尔值 (True/False -> true/false)
        content = content.replace('True', 'true')
        content = content.replace('False', 'false')

        # 移除单引号改为双引号（字符串内部）
        # 先保护已经正确的双引号字符串
        content = re.sub(r'"[^"]*"', lambda m: m.group(0).replace("'", "\\'"), content)
        content = content.replace("'", '"')

        # 移除注释（如果 AI 返回了 JavaScript 风格注释）
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

        # 移除多余的逗号（如 [1, 2, 3,,]）
        content = re.sub(r',+,', ',', content)

        # 修复键名没有引号的情况（如 {key: "value"}）
        content = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', content)

        # 确保数字值正确（如 1. 而不是 1.0）
        # 修复 null -> null（已经是标准）
        content = content.replace('Null', 'null')

        return content.strip()

    def _extract_json_by_regex(self, content: str) -> Dict[str, Any]:
        """使用正则表达式提取关键 JSON 数据"""
        import re
        result = {"slides_analysis": [], "overall_style": {}}

        # 尝试提取 slides_analysis 数组
        slides_match = re.search(r'"slides_analysis"\s*:\s*\[(.*?)\]', content, re.DOTALL)
        if slides_match:
            slides_str = slides_match.group(1)
            # 简单解析每个 slide 对象
            slide_matches = re.findall(r'\{[^{}]*\}', slides_str)
            for slide_str in slide_matches:
                slide_data = {}
                # 提取 slide_index
                idx_match = re.search(r'"slide_index"\s*:\s*(\d+)', slide_str)
                if idx_match:
                    slide_data["slide_index"] = int(idx_match.group(1))
                # 提取 images
                images_match = re.search(r'"images"\s*:\s*\[(.*?)\]', slide_str, re.DOTALL)
                if images_match:
                    slide_data["images"] = self._extract_images(images_match.group(1))
                # 提取 title_style
                title_style_match = re.search(r'"title_style"\s*:\s*\{([^{}]*)\}', slide_str)
                if title_style_match:
                    slide_data["title_style"] = self._extract_style(title_style_match.group(1))
                # 提取 content_style
                content_style_match = re.search(r'"content_style"\s*:\s*\{([^{}]*)\}', slide_str)
                if content_style_match:
                    slide_data["content_style"] = self._extract_style(content_style_match.group(1))
                # 提取 bullet_style
                bullet_style_match = re.search(r'"bullet_style"\s*:\s*\{([^{}]*)\}', slide_str)
                if bullet_style_match:
                    slide_data["bullet_style"] = self._extract_style(bullet_style_match.group(1))
                # 提取其他字段
                for field in ["text_layout", "has_separator_line", "separator_color", "highlight_words", "highlight_color", "add_decoration", "decoration_style", "corner_decoration", "reasoning"]:
                    field_match = re.search(rf'"{field}"\s*:\s*([^,}}]+)', slide_str)
                    if field_match:
                        val = field_match.group(1).strip()
                        if val.lower() == 'true':
                            slide_data[field] = True
                        elif val.lower() == 'false':
                            slide_data[field] = False
                        elif val.startswith('['):
                            try:
                                slide_data[field] = json.loads(val)
                            except:
                                slide_data[field] = []
                        else:
                            slide_data[field] = val.strip('"')
                if slide_data:
                    result["slides_analysis"].append(slide_data)

        return result

    def _extract_images(self, images_str: str) -> List[Dict]:
        """从字符串中提取图片数据"""
        import re
        images = []
        image_matches = re.findall(r'\{([^{}]*)\}', images_str)
        for img_str in image_matches:
            img_data = {}
            for field in ["image_type", "description", "keywords", "position", "width_ratio", "is_decoration"]:
                field_match = re.search(rf'"{field}"\s*:\s*([^,}}]+)', img_str)
                if field_match:
                    val = field_match.group(1).strip()
                    if field in ["width_ratio"]:
                        try:
                            img_data[field] = float(val)
                        except:
                            img_data[field] = 0.4
                    elif field in ["is_decoration"]:
                        img_data[field] = val.lower() == 'true'
                    else:
                        img_data[field] = val.strip('"')
            if img_data:
                images.append(img_data)
        return images

    def _extract_style(self, style_str: str) -> Dict:
        """从字符串中提取样式数据"""
        import re
        style = {}
        for field in ["font_family", "font_size", "font_color", "font_weight", "style", "color"]:
            field_match = re.search(rf'"{field}"\s*:\s*([^,}}]+)', style_str)
            if field_match:
                val = field_match.group(1).strip()
                if field in ["font_size", "width_ratio"]:
                    try:
                        style[field] = int(float(val))
                    except:
                        style[field] = 24
                else:
                    style[field] = val.strip('"')
        return style
    
    def _build_visual_plan(
        self,
        title: str,
        slides_content: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
        theme: str
    ) -> PPTVisualPlan:
        """构建视觉规划对象"""

        slides_analysis = analysis_result.get("slides_analysis", [])
        overall_style = analysis_result.get("overall_style", {})

        visual_slides = []
        for i, slide_data in enumerate(slides_content):
            # 找到对应的分析结果
            analysis = None
            for a in slides_analysis:
                if a.get("slide_index") == i + 1:
                    analysis = a
                    break

            if analysis:
                # 解析多图片
                images = []
                for img_data in analysis.get("images", []):
                    try:
                        img_type = ImageType(img_data.get("image_type", "none"))
                    except ValueError:
                        img_type = ImageType.NONE

                    try:
                        img_pos = ImagePosition(img_data.get("position", "right"))
                    except ValueError:
                        img_pos = ImagePosition.RIGHT

                    images.append(ImageDecision(
                        image_type=img_type,
                        description=img_data.get("description", ""),
                        keywords=img_data.get("keywords", []),
                        position=img_pos,
                        width_ratio=img_data.get("width_ratio", 0.4),
                        opacity=img_data.get("opacity", 1.0),
                        is_decoration=img_data.get("is_decoration", False)
                    ))

                # 解析标题样式
                title_style_data = analysis.get("title_style", {})
                title_style = TitleStyle(
                    font_family=title_style_data.get("font_family", "微软雅黑"),
                    font_size=title_style_data.get("font_size", 44),
                    font_color=title_style_data.get("font_color", "004296"),
                    font_weight=title_style_data.get("font_weight", "bold")
                )

                # 解析内容样式
                content_style_data = analysis.get("content_style", {})
                content_style = TextStyle(
                    font_family=content_style_data.get("font_family", "微软雅黑"),
                    font_size=content_style_data.get("font_size", 22),
                    font_color=content_style_data.get("font_color", "333333")
                )

                # 解析列表样式
                bullet_style_data = analysis.get("bullet_style", {})
                bullet_style = BulletStyleConfig(
                    style=bullet_style_data.get("style", "circle"),
                    color=bullet_style_data.get("color", "FF6600")
                )

                visual_slide = SlideVisualDecision(
                    slide_index=i + 1,
                    title=slide_data.get("title", f"第{i+1}页"),
                    content_summary=self._summarize_content(slide_data.get("content", [])),
                    images=images,
                    title_style=title_style,
                    content_style=content_style,
                    bullet_style=bullet_style,
                    text_layout=analysis.get("text_layout", "right"),
                    has_separator_line=analysis.get("has_separator_line", True),
                    separator_color=analysis.get("separator_color", "4A90D9"),
                    highlight_words=analysis.get("highlight_words", []),
                    highlight_color=analysis.get("highlight_color", "FF6600"),
                    add_decoration=analysis.get("add_decoration", True),
                    decoration_style=analysis.get("decoration_style", "minimal"),
                    corner_decoration=analysis.get("corner_decoration", True),
                    reasoning=analysis.get("reasoning", "")
                )
            else:
                # 没有分析结果，使用默认
                visual_slide = SlideVisualDecision(
                    slide_index=i + 1,
                    title=slide_data.get("title", f"第{i+1}页"),
                    content_summary=self._summarize_content(slide_data.get("content", []))
                )

            visual_slides.append(visual_slide)

        # 构建整体规划
        plan = PPTVisualPlan(
            title=title,
            theme=theme,
            slides=visual_slides,
            color_scheme=overall_style.get("color_scheme", "blue"),
            font_preference=overall_style.get("font_preference", "modern"),
            maintain_consistency=overall_style.get("maintain_consistency", True),
            use_same_layout_pattern=overall_style.get("layout_pattern", "alternating") == "same"
        )

        return plan
    
    def _summarize_content(self, content: Any) -> str:
        """总结内容为短文本"""
        if isinstance(content, list):
            text = " ".join(str(c) for c in content[:3])
        else:
            text = str(content)
        return text[:100]
    
    def _create_default_plan(
        self,
        title: str,
        slides_content: List[Dict[str, Any]],
        theme: str
    ) -> PPTVisualPlan:
        """创建默认视觉规划（不使用图片）"""

        visual_slides = []
        for i, slide_data in enumerate(slides_content, 1):
            visual_slide = SlideVisualDecision(
                slide_index=i,
                title=slide_data.get("title", f"第{i}页"),
                content_summary=self._summarize_content(slide_data.get("content", [])),
                images=[],  # 默认无图片
                title_style=TitleStyle(
                    font_family="微软雅黑",
                    font_size=44,
                    font_color="004296",
                    font_weight="bold"
                ),
                content_style=TextStyle(
                    font_family="微软雅黑",
                    font_size=22,
                    font_color="333333"
                ),
                bullet_style=BulletStyleConfig(
                    style="circle",
                    color="FF6600"
                ),
                add_decoration=True,
                decoration_style="minimal",
                corner_decoration=True
            )
            visual_slides.append(visual_slide)

        return PPTVisualPlan(
            title=title,
            theme=theme,
            slides=visual_slides
        )


# 全局实例
visual_analyzer = VisualAnalyzer()
