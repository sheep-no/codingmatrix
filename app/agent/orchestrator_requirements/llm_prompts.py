import json
import re
import logging
from typing import List

from app.agent.orchestrator_requirements.data_models import AssociationItem

logger = logging.getLogger(__name__)


def llm_system_prompt() -> str:
    return """你是一位资深的全栈架构顾问。你的任务是分析用户需求，发现可能遗漏的功能模块、架构影响、潜在风险和关键决策。

请严格按照以下 JSON 格式输出，不要输出任何其他内容：
{
  "functional_requirements": [
    {"item": "功能描述", "confidence": 0.8, "category": "core/optional/enhancement"}
  ],
  "architectural_impacts": [
    {"item": "架构影响描述", "confidence": 0.7, "impact_level": "high/medium/low"}
  ],
  "risks": [
    {"item": "风险描述", "confidence": 0.75, "severity": "high/medium/low"}
  ],
  "key_decisions": [
    {"item": "需要用户决定的选项", "confidence": 0.9, "options": ["选项A", "选项B"]}
  ]
}

confidence 取值 0.0-1.0，表示该联想项对用户的重要程度。"""


def build_llm_prompt(
    requirement: str,
    template_summary: str,
    history_summary: str
) -> str:
    parts = [f"用户原始需求：\n{requirement}\n"]
    if template_summary:
        parts.append(f"\n领域模板已匹配的功能：\n{template_summary}\n")
    if history_summary:
        parts.append(f"\n相似历史项目的功能参考：\n{history_summary}\n")
    parts.append(
        "\n请分析以上信息，联想用户可能遗漏的功能模块、架构影响、潜在风险和关键决策。"
        "重点关注：用户没说出来但实际需要的功能、可能存在的架构连锁影响、容易出错的领域风险点。"
    )
    return "\n".join(parts)


def parse_llm_response(response: str) -> List[AssociationItem]:
    items = []

    try:
        json_str = response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            json_str = json_match.group()

        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("LLM 联想输出非 JSON, 尝试文本提取")
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and len(line) > 5 and not line.startswith("#"):
                items.append(AssociationItem(
                    content=line,
                    category="functional",
                    source="llm_association",
                    confidence=0.5
                ))
        return items

    for item in parsed.get("functional_requirements", []):
        items.append(AssociationItem(
            content=item.get("item", ""),
            category="functional",
            source="llm_association",
            confidence=item.get("confidence", 0.7),
            sub_category=item.get("category", "optional"),
            impact=""
        ))

    for item in parsed.get("architectural_impacts", []):
        items.append(AssociationItem(
            content=item.get("item", ""),
            category="architectural",
            source="llm_association",
            confidence=item.get("confidence", 0.6),
            sub_category=item.get("impact_level", "medium"),
            impact=item.get("impact_level", "medium")
        ))

    for item in parsed.get("risks", []):
        items.append(AssociationItem(
            content=item.get("item", ""),
            category="risk",
            source="llm_association",
            confidence=item.get("confidence", 0.65),
            sub_category=item.get("severity", "medium"),
            impact=item.get("severity", "medium")
        ))

    for item in parsed.get("key_decisions", []):
        items.append(AssociationItem(
            content=item.get("item", ""),
            category="decision",
            source="llm_association",
            confidence=item.get("confidence", 0.8),
            sub_category="key_decision",
            impact="architecture",
        ))

    return items


def summarize_items(items: List[AssociationItem], label: str) -> str:
    if not items:
        return ""
    lines = []
    for item in items:
        lines.append(f"  - [{item.category}] {item.content}")
    return f"{label} ({len(items)} 项):\n" + "\n".join(lines)