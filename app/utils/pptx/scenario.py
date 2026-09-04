"""Deterministic presentation scenario classification and template ranking."""

from dataclasses import dataclass
import re
from typing import Iterable

from app.utils.pptx.templates.base import TemplateCategory


SCENARIO_PROFILES = {
    "business": (TemplateCategory.BUSINESS, ("经营", "季度", "汇报", "战略", "管理", "运营")),
    "data_report": (TemplateCategory.BUSINESS, ("数据", "指标", "分析", "报表", "趋势", "增长")),
    "product_pitch": (TemplateCategory.PITCH, ("产品", "路演", "融资", "商业模式", "用户", "发布")),
    "academic": (TemplateCategory.ACADEMIC, ("论文", "研究", "学术", "实验", "方法", "结论")),
    "education": (TemplateCategory.EDUCATION, ("课程", "培训", "教学", "课堂", "知识", "学习")),
    "general": (TemplateCategory.MINIMAL, ()),
}


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    category: TemplateCategory
    confidence: float
    matched_keywords: tuple[str, ...]


def classify_scenario(text: str) -> ScenarioResult:
    """Classify a topic using stable keyword evidence and a confidence floor."""
    normalized = re.sub(r"\s+", "", text or "").lower()
    scores = {
        scenario: tuple(keyword for keyword in keywords if keyword.lower() in normalized)
        for scenario, (_, keywords) in SCENARIO_PROFILES.items()
    }
    scenario, matched = max(
        ((name, hits) for name, hits in scores.items() if name != "general"),
        key=lambda item: (len(item[1]), item[0]),
        default=("general", ()),
    )
    confidence = min(1.0, len(matched) / 3.0)
    if confidence < 0.6:
        scenario = "general"
    category = SCENARIO_PROFILES[scenario][0]
    return ScenarioResult(scenario, category, confidence, tuple(matched))


def scenario_keywords(scenario: str) -> Iterable[str]:
    """Return the configured keywords for a scenario."""
    return SCENARIO_PROFILES.get(scenario, SCENARIO_PROFILES["general"])[1]
