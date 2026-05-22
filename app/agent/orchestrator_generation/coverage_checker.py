import re
from typing import Dict, Any, List, Optional


def check_requirement_coverage(
    requirement: str,
    architecture: Dict,
    file_plan: List[Dict],
    association_result: Optional[Any] = None,
) -> Dict[str, Any]:
    if not association_result:
        return {"checked": False, "uncovered": [], "coverage_rate": 1.0}

    association_items = association_result.items
    if not association_items or association_result.skipped:
        return {"checked": False, "uncovered": [], "coverage_rate": 1.0}

    confirmed_items = [
        i for i in association_items
        if i.confidence >= 0.7 and i.category == "functional"
    ]
    if not confirmed_items:
        return {"checked": True, "uncovered": [], "coverage_rate": 1.0}

    all_content = []
    for file_info in file_plan:
        path = file_info.get("path", "")
        desc = file_info.get("description", "")
        all_content.append(path.lower())
        all_content.append(desc.lower())

    arch_content = []
    for key in ["project_type", "tech_stack", "database", "api_endpoints"]:
        val = architecture.get(key, "")
        if isinstance(val, str):
            arch_content.append(val.lower())
        elif isinstance(val, list):
            arch_content.extend(str(v).lower() for v in val)

    combined_text = " ".join(all_content + arch_content)

    uncovered = []
    for item in confirmed_items:
        keywords = re.findall(r'\w+', item.content.lower())
        matched_kw = sum(1 for kw in keywords if len(kw) > 2 and kw in combined_text)
        if matched_kw < len(keywords) * 0.3:
            uncovered.append({
                "item": item.content,
                "category": item.category,
                "source": item.source,
                "confidence": item.confidence,
            })

    coverage_rate = 1.0 - (len(uncovered) / max(len(confirmed_items), 1))

    return {
        "checked": True,
        "total_items": len(confirmed_items),
        "uncovered": uncovered,
        "coverage_rate": coverage_rate,
    }