import logging
from typing import List, Dict, Tuple

from app.agent.orchestrator_requirements.constants import (
    DUAL_MODEL_A,
    DUAL_MODEL_B,
    DUAL_MODEL_FALLBACK,
)
from app.agent.orchestrator_requirements.data_models import AssociationItem
from app.agent.orchestrator_requirements.llm_prompts import (
    llm_system_prompt,
    build_llm_prompt,
    summarize_items,
    parse_llm_response,
)

logger = logging.getLogger(__name__)


async def layer3_dual_model_deep(
    requirement: str,
    layer1_items: List[AssociationItem],
    layer2_items: List[AssociationItem],
    architect: object = None,
) -> List[AssociationItem]:

    if not architect:
        return []

    template_summary = summarize_items(layer1_items, "领域模板")
    history_summary = summarize_items(layer2_items, "历史项目")
    prompt = build_llm_prompt(requirement, template_summary, history_summary)
    system_prompt = llm_system_prompt()

    model_a_items = []
    model_b_items = []

    try:
        from app.utils import call_llm
        response_a = await call_llm(
            model=DUAL_MODEL_A,
            prompt=prompt,
            system_prompt=system_prompt
        )
        model_a_items = parse_llm_response(response_a)
    except Exception as e:
        logger.warning(f"双模型联想 Model-A 失败: {e}")

    try:
        from app.utils import call_llm
        response_b = await call_llm(
            model=DUAL_MODEL_B,
            prompt=prompt,
            system_prompt=system_prompt
        )
        model_b_items = parse_llm_response(response_b)
    except Exception as e:
        logger.warning(f"双模型联想 Model-B 失败: {e}")

    if model_a_items and not model_b_items:
        for item in model_a_items:
            item.source = "llm_association:single"
            item.dual_model_agreement = "single_model"
        return model_a_items

    if model_b_items and not model_a_items:
        for item in model_b_items:
            item.source = "llm_association:single"
            item.dual_model_agreement = "single_model"
        return model_b_items

    if not model_a_items and not model_b_items:
        try:
            from app.utils import call_llm
            response = await call_llm(
                model=DUAL_MODEL_FALLBACK,
                prompt=prompt,
                system_prompt=system_prompt
            )
            fallback_items = parse_llm_response(response)
            for item in fallback_items:
                item.source = "llm_association:fallback"
                item.dual_model_agreement = "fallback"
            return fallback_items
        except Exception as e:
            logger.warning(f"LLM 联想降级调用也失败: {e}")
            return []

    return merge_dual_model_results(model_a_items, model_b_items)


def merge_dual_model_results(
    items_a: List[AssociationItem], items_b: List[AssociationItem]
) -> List[AssociationItem]:
    content_map: Dict[str, Tuple[AssociationItem, List[str]]] = {}

    for item in items_a:
        key = f"{item.category}:{item.content[:50]}"
        if key not in content_map:
            content_map[key] = (item, [DUAL_MODEL_A])
        else:
            existing, models = content_map[key]
            models.append(DUAL_MODEL_A)

    for item in items_b:
        key = f"{item.category}:{item.content[:50]}"
        if key not in content_map:
            content_map[key] = (item, [DUAL_MODEL_B])
        else:
            existing, models = content_map[key]
            models.append(DUAL_MODEL_B)
            if item.confidence > existing.confidence:
                content_map[key] = (item, models)

    merged = []
    for key, (item, models) in content_map.items():
        both_agree = DUAL_MODEL_A in models and DUAL_MODEL_B in models
        if both_agree:
            item.confidence = min(item.confidence + 0.1, 0.95)
            item.source = "llm_association:dual"
            item.dual_model_agreement = "both_agree"
        else:
            item.confidence = max(item.confidence * 0.95, 0.5)
            item.source = "llm_association:single"
            item.dual_model_agreement = "needs_confirmation"
        merged.append(item)

    return merged
