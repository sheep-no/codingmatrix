"""PPT 动画效果引擎 - 通过 XML 操作实现基础动画效果支持

python-pptx 不直接支持动画 API，本模块通过操作底层 Open XML 标准
为 PPT 添加页面切换效果和元素进入动画。
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from lxml import etree


logger = logging.getLogger(__name__)

# Open XML 命名空间
NS_MAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
}


class TransitionEffect(Enum):
    """页面切换效果"""
    FADE = "fade"
    PUSH = "push"
    WIPE = "wipe"
    SPLIT = "split"
    COVER = "cover"
    RANDOM = "random"


class EntranceEffect(Enum):
    """元素进入效果"""
    FADE_IN = "fade_in"
    FLY_IN = "fly_in"
    ZOOM = "zoom"
    WIPE_ENTRANCE = "wipe_entrance"
    NONE = "none"


@dataclass
class AnimationConfig:
    """动画配置"""
    transition: TransitionEffect = TransitionEffect.FADE
    duration: float = 1.0
    delay: float = 0.0
    entrance: EntranceEffect = EntranceEffect.NONE
    trigger: str = "on_click"


class AnimationEngine:
    """动画引擎 - 通过 XML 操作为 PPT 添加动画效果"""

    # 切换效果到 XML 标签的映射
    _TRANSITION_MAP = {
        TransitionEffect.FADE: "fadeIn",
        TransitionEffect.PUSH: "push",
        TransitionEffect.WIPE: "wipe",
        TransitionEffect.SPLIT: "split",
        TransitionEffect.COVER: "cover",
        TransitionEffect.RANDOM: "transition8rand",
    }

    # 进入效果到动画模板 ID 的映射
    _ENTRANCE_MAP = {
        EntranceEffect.FADE_IN: "animFading",
        EntranceEffect.FLY_IN: "animFly",
        EntranceEffect.ZOOM: "animZoom",
        EntranceEffect.WIPE_ENTRANCE: "animWipe",
        EntranceEffect.NONE: None,
    }

    # 触发方式映射
    _TRIGGER_MAP = {
        "on_click": "afterClick",
        "auto": "withTm",
        "with_previous": "withTm",
    }

    def __init__(self) -> None:
        """初始化动画引擎"""
        self._default_config = AnimationConfig()
        logger.debug("AnimationEngine initialized")

    def apply_slide_transition(
        self, slide, effect: TransitionEffect, duration: float = 1.0
    ) -> bool:
        """应用页面切换效果

        通过修改幻灯片 XML 的 <p:transition> 元素添加切换效果。

        Args:
            slide: python-pptx Slide 对象
            effect: 切换效果类型
            duration: 动画持续时间（秒）

        Returns:
            是否成功应用
        """
        try:
            transition_tag = self._TRANSITION_MAP.get(effect)
            if not transition_tag:
                logger.error(f"Unknown transition effect: {effect}")
                return False

            p_namespace = NS_MAP["p"]
            slide_element = slide._element

            # 查找或创建 <p:transition> 元素
            transition_elem = slide_element.find(
                f"{{{p_namespace}}}transition"
            )
            if transition_elem is None:
                transition_elem = etree.SubElement(
                    slide_element, f"{{{p_namespace}}}transition"
                )

            # 清除旧的切换效果子元素
            for child in list(transition_elem):
                local_name = etree.QName(child.tag).localname
                if local_name in self._TRANSITION_MAP.values():
                    transition_elem.remove(child)

            # 添加新的切换效果元素
            duration_ms = int(duration * 1000)
            effect_elem = etree.SubElement(
                transition_elem, f"{{{p_namespace}}}{transition_tag}"
            )
            effect_elem.set("advTm", str(duration_ms))

            # 添加全局持续时间属性
            transition_elem.set("advClick", "1")
            transition_elem.set("spd", self._speed_from_duration(duration))

            logger.info(f"Applied transition '{effect.value}' with duration {duration}s")
            return True
        except Exception as e:
            logger.error(f"Failed to apply slide transition: {e}")
            return False

    def apply_shape_entrance(
        self, shape, effect: EntranceEffect, delay: float = 0.5
    ) -> bool:
        """应用元素进入动画

        通过修改 shape 的时间树 XML 添加进入动画。

        Args:
            shape: python-pptx Shape 对象
            effect: 进入效果类型
            delay: 延迟时间（秒）

        Returns:
            是否成功应用
        """
        if effect == EntranceEffect.NONE:
            return True

        template_id = self._ENTRANCE_MAP.get(effect)
        if not template_id:
            logger.error(f"Unknown entrance effect: {effect}")
            return False

        try:
            p_namespace = NS_MAP["p"]

            # 获取或创建 timing 元素
            shape_element = shape._element
            ctn = self._get_or_create_timing_ctn(shape_element)

            # 构建动画序列
            delay_ms = int(delay * 1000)
            seq_id = self._generate_seq_id()

            # 创建 seq 元素
            seq = etree.SubElement(ctn, f"{{{p_namespace}}}seq")
            seq.set("id", seq_id)
            seq.set("presetClass", "entrance")
            seq.set("presetID", self._get_preset_id(effect))

            # 添加触发条件
            cond = etree.SubElement(seq, f"{{{p_namespace}}}cond")
            cond.set("delay", str(delay_ms))
            cond.set("evt", "begin")

            # 添加子容器用于实际动画
            child_ctn = etree.SubElement(
                seq, f"{{{p_namespace}}}ctn"
            )
            child_ctn.set("id", f"{seq_id}_child")

            # 添加具体的动画效果
            self._add_animation_effect(child_ctn, effect, shape.shape_id)

            logger.info(f"Applied entrance '{effect.value}' with delay {delay}s")
            return True
        except Exception as e:
            logger.error(f"Failed to apply shape entrance: {e}")
            return False

    def apply_title_animation(self, slide, delay: float = 0.3) -> bool:
        """为幻灯片标题应用动画

        查找幻灯片的标题形状并应用渐入动画。

        Args:
            slide: python-pptx Slide 对象
            delay: 延迟时间（秒）

        Returns:
            是否成功应用
        """
        try:
            title_shape = slide.shapes.title
            if title_shape is None:
                logger.warning("Slide has no title shape, skipping title animation")
                return False

            result = self.apply_shape_entrance(
                title_shape, EntranceEffect.FADE_IN, delay
            )
            if result:
                logger.info(f"Applied title animation with delay {delay}s")
            return result
        except Exception as e:
            logger.error(f"Failed to apply title animation: {e}")
            return False

    def apply_content_animation(
        self, slide, content_items: List, stagger: float = 0.2
    ) -> bool:
        """为幻灯片内容应用交错过画

        为内容元素依次添加进入动画，形成交错效果。

        Args:
            slide: python-pptx Slide 对象
            content_items: 形状列表
            stagger: 交错延迟时间（秒）

        Returns:
            是否成功应用
        """
        if not content_items:
            logger.warning("No content items provided for animation")
            return False

        try:
            success_count = 0
            for idx, item in enumerate(content_items):
                delay = idx * stagger
                result = self.apply_shape_entrance(item, EntranceEffect.FADE_IN, delay)
                if result:
                    success_count += 1

            logger.info(
                f"Applied content animation to {success_count}/{len(content_items)} items"
            )
            return success_count > 0
        except Exception as e:
            logger.error(f"Failed to apply content animation: {e}")
            return False

    def apply_template_animations(self, prs, template_name: str) -> bool:
        """根据模板名称应用全局动画预设

        Args:
            prs: python-pptx Presentation 对象
            template_name: 模板名称（如 "professional", "creative", "minimal"）

        Returns:
            是否成功应用
        """
        presets = {
            "professional": {
                "transition": TransitionEffect.FADE,
                "entrance": EntranceEffect.FADE_IN,
                "duration": 1.0,
                "stagger": 0.2,
            },
            "creative": {
                "transition": TransitionEffect.PUSH,
                "entrance": EntranceEffect.FLY_IN,
                "duration": 0.8,
                "stagger": 0.15,
            },
            "minimal": {
                "transition": TransitionEffect.WIPE,
                "entrance": EntranceEffect.WIPE_ENTRANCE,
                "duration": 1.2,
                "stagger": 0.3,
            },
            "dynamic": {
                "transition": TransitionEffect.SPLIT,
                "entrance": EntranceEffect.ZOOM,
                "duration": 0.6,
                "stagger": 0.1,
            },
        }

        preset = presets.get(template_name.lower())
        if not preset:
            logger.error(f"Unknown template: {template_name}. Available: {list(presets.keys())}")
            return False

        try:
            self.set_default_transition(
                prs, preset["transition"], preset["duration"]
            )

            for slide in prs.slides:
                shapes_to_animate = [
                    shape for shape in slide.shapes
                    if shape.has_text_frame and shape.text_frame.text.strip()
                ]
                if shapes_to_animate:
                    self.apply_content_animation(
                        slide, shapes_to_animate, preset["stagger"]
                    )

            logger.info(f"Applied template animations: {template_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply template animations: {e}")
            return False

    def set_default_transition(
        self, prs, effect: TransitionEffect, duration: float = 1.0
    ) -> bool:
        """为所有幻灯片设置默认切换效果

        Args:
            prs: python-pptx Presentation 对象
            effect: 切换效果类型
            duration: 动画持续时间（秒）

        Returns:
            是否成功应用
        """
        try:
            success_count = 0
            for slide in prs.slides:
                result = self.apply_slide_transition(slide, effect, duration)
                if result:
                    success_count += 1

            logger.info(
                f"Set default transition '{effect.value}' for {success_count} slides"
            )
            return success_count > 0
        except Exception as e:
            logger.error(f"Failed to set default transition: {e}")
            return False

    def animate_slide_sequence(self, slide, shapes: List) -> bool:
        """按顺序动画多个元素

        为形状列表依次添加动画，每个元素在前一个之后触发。

        Args:
            slide: python-pptx Slide 对象
            shapes: 形状列表

        Returns:
            是否成功应用
        """
        if not shapes:
            logger.warning("No shapes provided for sequence animation")
            return False

        try:
            current_delay = 0.3
            for shape in shapes:
                self.apply_shape_entrance(shape, EntranceEffect.FADE_IN, current_delay)
                current_delay += 0.2

            logger.info(f"Applied sequence animation to {len(shapes)} shapes")
            return True
        except Exception as e:
            logger.error(f"Failed to animate slide sequence: {e}")
            return False

    def _get_or_create_timing_ctn(self, shape_element) -> etree._Element:
        """获取或创建时间树容器元素"""
        p_namespace = NS_MAP["p"]
        ns = f"{{{p_namespace}}}"

        # 查找现有的 timing 元素
        timing = shape_element.find(f"{ns}timing")
        if timing is None:
            timing = etree.SubElement(shape_element, f"{ns}timing")

        ctn = timing.find(f"{ns}tn")
        if ctn is None:
            ctn = etree.SubElement(timing, f"{ns}tn")
            ctn.set("id", "main_seq")

        return ctn

    def _generate_seq_id(self) -> str:
        """生成唯一的序列 ID"""
        import uuid
        return f"seq_{uuid.uuid4().hex[:8]}"

    def _get_preset_id(self, effect: EntranceEffect) -> str:
        """获取效果的预设 ID"""
        preset_ids = {
            EntranceEffect.FADE_IN: "1",
            EntranceEffect.FLY_IN: "2",
            EntranceEffect.ZOOM: "3",
            EntranceEffect.WIPE_ENTRANCE: "4",
        }
        return preset_ids.get(effect, "0")

    def _add_animation_effect(
        self, parent: etree._Element, effect: EntranceEffect, shape_id: int
    ) -> None:
        """添加具体的动画效果 XML"""
        p_namespace = NS_MAP["p"]
        ns = f"{{{p_namespace}}}"

        # 添加 animate 元素
        anim = etree.SubElement(parent, f"{ns}animate")
        anim.set("id", f"anim_{shape_id}")
        anim.set("calcmode", "linear")
        anim.set("fill", "hold")

        # 添加值范围
        by_val = etree.SubElement(anim, f"{ns}by")
        by_val.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}val", "1")

        # 添加目标元素引用
        tgt_el = etree.SubElement(anim, f"{ns}tgtEl")
        sp_tgt = etree.SubElement(tgt_el, f"{ns}spTgt")
        sp_tgt.set("spid", str(shape_id))

    def _speed_from_duration(self, duration: float) -> str:
        """将持续时间转换为速度标识"""
        if duration <= 0.5:
            return "fast"
        elif duration <= 1.0:
            return "med"
        elif duration <= 2.0:
            return "slow"
        return "slow"


class AnimationPresets:
    """动画预设 - 提供常用动画组合"""

    @staticmethod
    def get_preset_for_theme(theme: str) -> Dict:
        """根据主题获取动画预设

        Args:
            theme: 主题名称

        Returns:
            动画预设字典，包含 transition、entrance、duration 等配置

        Raises:
            ValueError: 当主题不存在时
        """
        presets = {
            "corporate": {
                "transition": TransitionEffect.FADE,
                "entrance": EntranceEffect.FADE_IN,
                "duration": 1.0,
                "stagger": 0.2,
                "trigger": "on_click",
            },
            "creative": {
                "transition": TransitionEffect.PUSH,
                "entrance": EntranceEffect.FLY_IN,
                "duration": 0.8,
                "stagger": 0.15,
                "trigger": "auto",
            },
            "minimal": {
                "transition": TransitionEffect.WIPE,
                "entrance": EntranceEffect.NONE,
                "duration": 1.2,
                "stagger": 0.0,
                "trigger": "on_click",
            },
            "dynamic": {
                "transition": TransitionEffect.SPLIT,
                "entrance": EntranceEffect.ZOOM,
                "duration": 0.6,
                "stagger": 0.1,
                "trigger": "with_previous",
            },
            "elegant": {
                "transition": TransitionEffect.COVER,
                "entrance": EntranceEffect.FADE_IN,
                "duration": 1.5,
                "stagger": 0.25,
                "trigger": "on_click",
            },
        }

        theme_lower = theme.lower()
        if theme_lower not in presets:
            raise ValueError(
                f"Unknown theme: '{theme}'. "
                f"Available themes: {list(presets.keys())}"
            )

        logger.info(f"Retrieved preset for theme: {theme}")
        return presets[theme_lower]

    @staticmethod
    def apply_fade_transition(prs, duration: float = 1.0) -> bool:
        """为演示文稿统一应用淡入淡出切换效果

        Args:
            prs: python-pptx Presentation 对象
            duration: 动画持续时间（秒）

        Returns:
            是否成功应用
        """
        try:
            engine = AnimationEngine()
            result = engine.set_default_transition(prs, TransitionEffect.FADE, duration)
            if result:
                logger.info(f"Applied fade transition to all slides (duration: {duration}s)")
            return result
        except Exception as e:
            logger.error(f"Failed to apply fade transition: {e}")
            return False

    @staticmethod
    def apply_professional_animations(prs) -> bool:
        """应用商务专业动画组合

        包括淡入页面切换、标题渐入、内容交错出现。

        Args:
            prs: python-pptx Presentation 对象

        Returns:
            是否成功应用
        """
        try:
            engine = AnimationEngine()
            success_count = 0

            for slide in prs.slides:
                slide_ok = True

                # 页面切换：淡入
                if not engine.apply_slide_transition(slide, TransitionEffect.FADE, 1.0):
                    slide_ok = False

                # 标题动画：渐入
                if not engine.apply_title_animation(slide, delay=0.3):
                    slide_ok = False

                # 内容动画：交错过画
                shapes_to_animate = [
                    shape for shape in slide.shapes
                    if shape.has_text_frame
                    and shape.text_frame.text.strip()
                    and shape != slide.shapes.title
                ]
                if shapes_to_animate:
                    if not engine.apply_content_animation(
                        slide, shapes_to_animate, stagger=0.2
                    ):
                        slide_ok = False

                if slide_ok:
                    success_count += 1

            logger.info(
                f"Applied professional animations to {success_count}/{len(prs.slides)} slides"
            )
            return success_count > 0
        except Exception as e:
            logger.error(f"Failed to apply professional animations: {e}")
            return False
