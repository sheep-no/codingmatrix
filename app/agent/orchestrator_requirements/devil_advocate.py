import json
import re
import logging
from typing import List, Dict

from app.agent.orchestrator_requirements.constants import DEVILS_ADVOCATE_MODEL, CONFIDENCE_DEFAULT_SHOW
from app.agent.orchestrator_requirements.data_models import AssociationItem

logger = logging.getLogger(__name__)


async def devil_advocate_review(
    requirement: str, items: List[AssociationItem], architect: object = None
) -> List[Dict]:
    if not architect or len(items) < 3:
        return []

    high_conf_items = [i for i in items if i.confidence >= CONFIDENCE_DEFAULT_SHOW]
    if not high_conf_items:
        return []

    items_summary = "\n".join(
        f"  [{i.category}] {i.content} (置信度: {i.confidence:.1f})"
        for i in high_conf_items[:15]
    )

    prompt = f"""你是"魔鬼代言人"，职责是对已确认的需求联想项进行质疑和风险审视。

用户需求：{requirement}

已确认的联想项：
{items_summary}

请从以下角度逐一审视这些联想项：
1. 是否有遗漏的前置条件或依赖关系？
2. 是否有表面合理但实际会产生连锁风险的功能？
3. 是否有需要额外补充但联想项中未提到的环节？

请严格按照以下 JSON 格式输出，不要输出任何其他内容：
{
  "challenges": [
    {
      "target_item": "被质疑的联想项内容",
      "challenge": "质疑内容 - 为什么这个项可能有问题或遗漏了什么",
      "severity": "high/medium/low",
      "suggestion": "补充建议"
    }
  ]
}"""

    try:
        from app.utils import call_llm
        response = await call_llm(
            model=DEVILS_ADVOCATE_MODEL,
            prompt=prompt,
        )
    except Exception as e:
        logger.warning(f"魔鬼代言人审视失败: {e}")
        return []

    return parse_devil_response(response)


def parse_devil_response(response: str) -> List[Dict]:
    import re as _re
    try:
        json_match = _re.search(r'\{[\s\S]*\}', response)
        if json_match:
            parsed = json.loads(json_match.group())
            challenges = parsed.get("challenges", [])
            valid = []
            for c in challenges:
                if c.get("challenge") and c.get("target_item"):
                    valid.append({
                        "target_item": c.get("target_item", ""),
                        "challenge": c.get("challenge", ""),
                        "severity": c.get("severity", "medium"),
                        "suggestion": c.get("suggestion", ""),
                    })
            return valid[:10]
    except json.JSONDecodeError:
        pass

    return []