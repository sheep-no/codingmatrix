import json
import logging
from typing import List, Dict

from app.agent.orchestrator_requirements.constants import DOMAIN_TEMPLATES_DIR
from app.agent.orchestrator_requirements.data_models import AssociationItem

logger = logging.getLogger(__name__)


async def layer1_cross_domain_template(
    requirement: str, domains: List[str]
) -> List[AssociationItem]:
    if not domains:
        return []

    items = []
    for domain in domains:
        template_path = DOMAIN_TEMPLATES_DIR / f"{domain}.json"
        if not template_path.exists():
            logger.debug(f"领域模板不存在: {domain}")
            continue

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)
        except Exception as e:
            logger.warning(f"领域模板加载失败: {e}")
            continue

        confidence = compute_template_confidence(requirement, template)

        for module in template.get("core_modules", []):
            items.append(AssociationItem(
                content=module.get("name", ""),
                category="functional",
                source=f"domain_template:{domain}",
                confidence=confidence,
                sub_category=module.get("category", "core"),
                impact=module.get("impact", "")
            ))

        for nfr in template.get("non_functional_requirements", []):
            items.append(AssociationItem(
                content=nfr.get("item", ""),
                category="architectural",
                source=f"domain_template:{domain}",
                confidence=confidence * 0.9,
                sub_category=nfr.get("category", ""),
                impact=nfr.get("priority", "medium")
            ))

        for pitfall in template.get("common_pitfalls", []):
            items.append(AssociationItem(
                content=pitfall,
                category="risk",
                source=f"domain_template:{domain}",
                confidence=confidence * 0.85,
                sub_category="common_pitfall"
            ))

        for decision in template.get("key_decisions", []):
            items.append(AssociationItem(
                content=decision.get("question", ""),
                category="decision",
                source=f"domain_template:{domain}",
                confidence=confidence * 0.95,
                sub_category=decision.get("impact", "architecture"),
                impact=decision.get("impact", "architecture")
            ))

    seen = {}
    deduped = []
    for item in items:
        key = f"{item.category}:{item.content}"
        if key not in seen:
            deduped.append(item)
            seen[key] = item
        else:
            existing = seen[key]
            if item.confidence > existing.confidence:
                deduped.remove(existing)
                deduped.append(item)
                seen[key] = item

    return deduped


def compute_template_confidence(requirement: str, template: Dict) -> float:
    req_lower = requirement.lower()
    domain = template.get("domain", "")
    domain_keywords_map = {
        "banking": ["银行", "金融", "转账", "存款", "贷款", "账户", "支付"],
        "ecommerce": ["电商", "商城", "购物", "商品", "订单", "库存"],
        "cms": ["cms", "内容管理", "文章", "发布", "编辑"],
        "saas": ["saas", "后台", "管理平台", "租户"],
        "social": ["社交", "聊天", "朋友圈", "消息"],
        "dashboard": ["大屏", "数据大屏", "报表", "可视化"],
        "education": ["教育", "课程", "学生", "考试"],
        "healthcare": ["医疗", "健康", "挂号", "病历"],
        "iot": ["iot", "物联网", "传感器", "设备"],
        "erp": ["erp", "进销存", "采购", "销售"],
    }
    keywords = domain_keywords_map.get(domain, [])
    if not keywords:
        return 0.7
    hit = sum(1 for kw in keywords if kw in req_lower)
    return min(0.5 + (hit / len(keywords)) * 0.5, 1.0)
