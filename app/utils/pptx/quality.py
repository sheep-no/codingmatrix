"""Deterministic PPT layout quality checks and bounded reflow actions."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QualityIssue:
    issue_type: str
    slide_id: str
    severity: str
    message: str
    element_ids: tuple[str, ...] = ()
    fix_action: str | None = None


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)
    slide_scores: dict[str, float] = field(default_factory=dict)
    reflow_attempts: dict[str, int] = field(default_factory=dict)
    manual_review_slides: list[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if not self.slide_scores:
            return 100.0
        return round(sum(self.slide_scores.values()) / len(self.slide_scores), 2)


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (0.0, 0.0, 0.0)
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    return tuple(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels)


def contrast_ratio(first: str, second: str) -> float:
    luminance = lambda color: 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    left, right = luminance(_rgb(first)), luminance(_rgb(second))
    return (max(left, right) + 0.05) / (min(left, right) + 0.05)


def _intersection(first: dict[str, Any], second: dict[str, Any]) -> float:
    left = max(first["left"], second["left"])
    top = max(first["top"], second["top"])
    right = min(first["left"] + first["width"], second["left"] + second["width"])
    bottom = min(first["top"] + first["height"], second["top"] + second["height"])
    return max(0, right - left) * max(0, bottom - top)


def check_slide(slide: dict[str, Any], previous_layout: str | None = None, repeated_layouts: int = 0) -> list[QualityIssue]:
    slide_id = str(slide.get("id", slide.get("slide_id", "unknown")))
    width, height = slide.get("width", 13.333), slide.get("height", 7.5)
    margin = slide.get("safe_margin", 0.5)
    elements = slide.get("elements", [])
    issues: list[QualityIssue] = []
    for element in elements:
        element_id = str(element.get("id", "unknown"))
        if element.get("text_overflow") or element.get("measured_height", element.get("height", 0)) > element.get("height", 0):
            issues.append(QualityIssue("text_overflow", slide_id, "high", "文本超出文本框边界", (element_id,), "reduce_text_or_switch_layout"))
        if element.get("type") in {"text", "chart", "image", "shape"} and (
            element.get("left", 0) < margin or element.get("top", 0) < margin
            or element.get("left", 0) + element.get("width", 0) > width - margin
            or element.get("top", 0) + element.get("height", 0) > height - margin
        ):
            issues.append(QualityIssue("unsafe_margin", slide_id, "medium", "关键元素超出页面安全区", (element_id,), "move_into_safe_area"))
        if element.get("type") == "text" and contrast_ratio(element.get("foreground", "#000000"), element.get("background", "#FFFFFF")) < (3 if element.get("font_size", 16) >= 24 else 4.5):
            issues.append(QualityIssue("low_contrast", slide_id, "high", "文字对比度低于可读性阈值", (element_id,), "adjust_text_color"))
        if element.get("type") == "image" and element.get("source_width") and element.get("source_height"):
            source_ratio = element["source_width"] / element["source_height"]
            display_ratio = element.get("width", 1) / max(element.get("height", 1), 0.001)
            if abs(display_ratio / source_ratio - 1) > 0.02 and not element.get("cropped"):
                issues.append(QualityIssue("image_distortion", slide_id, "high", "图片显示比例偏离原始比例", (element_id,), "preserve_aspect_ratio"))
    for index, first in enumerate(elements):
        if first.get("decorative"):
            continue
        for second in elements[index + 1:]:
            if second.get("decorative"):
                continue
            overlap = _intersection(first, second)
            smaller = min(first.get("width", 0) * first.get("height", 0), second.get("width", 0) * second.get("height", 0))
            if smaller and overlap / smaller > 0.02:
                issues.append(QualityIssue("element_overlap", slide_id, "high", "非装饰元素重叠面积超过阈值", (str(first.get("id")), str(second.get("id"))), "reposition_elements"))
    if previous_layout and slide.get("layout") == previous_layout and repeated_layouts >= 2:
        issues.append(QualityIssue("layout_repetition", slide_id, "medium", "相同布局连续出现超过两页", fix_action="switch_layout"))
    return issues


class AutoReflowEngine:
    """Apply only deterministic, bounded layout fixes."""

    max_attempts = 2

    def reflow(self, slide: dict[str, Any], issues: list[QualityIssue], report: QualityReport) -> dict[str, Any]:
        slide_id = str(slide.get("id", slide.get("slide_id", "unknown")))
        attempts = report.reflow_attempts.get(slide_id, 0)
        if attempts >= self.max_attempts:
            if slide_id not in report.manual_review_slides:
                report.manual_review_slides.append(slide_id)
            return slide
        fixed = dict(slide)
        fixed["elements"] = [dict(element) for element in slide.get("elements", [])]
        for issue in issues:
            if issue.fix_action == "move_into_safe_area":
                for element in fixed["elements"]:
                    if element.get("id") in issue.element_ids:
                        element["left"] = max(slide.get("safe_margin", 0.5), element.get("left", 0))
                        element["top"] = max(slide.get("safe_margin", 0.5), element.get("top", 0))
            elif issue.fix_action == "preserve_aspect_ratio":
                for element in fixed["elements"]:
                    if element.get("id") in issue.element_ids:
                        element["cropped"] = True
        report.reflow_attempts[slide_id] = attempts + 1
        return fixed


def check_deck(slides: list[dict[str, Any]]) -> QualityReport:
    report = QualityReport()
    previous_layout = None
    repeated_layouts = 0
    for slide in slides:
        layout = slide.get("layout")
        repeated_layouts = repeated_layouts + 1 if layout == previous_layout else 1
        issues = check_slide(slide, previous_layout, repeated_layouts)
        report.issues.extend(issues)
        report.slide_scores[str(slide.get("id", slide.get("slide_id", "unknown")))] = max(0, 100 - len(issues) * 10)
        previous_layout = layout
    return report
