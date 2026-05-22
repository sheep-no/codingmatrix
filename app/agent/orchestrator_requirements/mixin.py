import time
import asyncio
import logging
from typing import Dict, Any, List

from app.agent.orchestrator_progress import PROGRESS_LABELS
from app.agent.tracing import traced

from app.agent.orchestrator_requirements.constants import (
    SKIP_COMPLEXITY_LEVELS,
    TIME_BUDGET_SECONDS,
    CONFIDENCE_DEFAULT_SHOW,
    CONFIDENCE_DISPLAY_THRESHOLD,
)
from app.agent.orchestrator_requirements.data_models import (
    AssociationItem,
    AssociationResult,
)
from app.agent.orchestrator_requirements.domain_detection import _detect_domains
from app.agent.orchestrator_requirements.layer1_template import layer1_cross_domain_template
from app.agent.orchestrator_requirements.layer2_semantic import layer2_semantic_match
from app.agent.orchestrator_requirements.layer3_dual_model import layer3_dual_model_deep
from app.agent.orchestrator_requirements.devil_advocate import devil_advocate_review

logger = logging.getLogger(__name__)


class RequirementAssociationMixin:

    @traced("orchestrator.requirement_association", attributes={"component": "orchestrator"})
    async def _generate_requirement_associations(
        self, requirement: str, complexity_level: str = ""
    ) -> AssociationResult:

        if complexity_level in SKIP_COMPLEXITY_LEVELS:
            return AssociationResult(
                skipped=True,
                skip_reason=f"项目复杂度 {complexity_level} 跳过联想环节"
            )

        budget = TIME_BUDGET_SECONDS.get(complexity_level, 20)
        start = time.time()

        try:
            result = await asyncio.wait_for(
                self._association_pipeline(requirement, complexity_level),
                timeout=budget
            )
        except asyncio.TimeoutError:
            logger.warning(f"联想环节超时 ({budget}s), 返回已完成部分")
            result = AssociationResult(
                items=self._partial_items if hasattr(self, '_partial_items') else [],
                enhanced_requirement=requirement,
                elapsed_seconds=time.time() - start,
                skipped=False
            )
        except Exception as e:
            logger.warning(f"联想环节异常, 静默降级: {e}")
            result = AssociationResult(
                skipped=True,
                skip_reason=f"联想异常: {str(e)[:100]}"
            )

        result.elapsed_seconds = time.time() - start
        return result

    async def _association_pipeline(
        self, requirement: str, complexity_level: str
    ) -> AssociationResult:

        self._partial_items = []

        self._report_progress(
            "requirement_association", 1, 6,
            phase="detecting_domain",
            message="正在匹配领域模板..."
        )

        domains = _detect_domains(requirement)
        layer1_items = await layer1_cross_domain_template(requirement, domains)
        self._partial_items.extend(layer1_items)

        self._report_progress(
            "requirement_association", 2, 6,
            phase="searching_history",
            domain=domains[0] if domains else "",
            items_count=len(layer1_items),
            message="正在检索相似项目..."
        )

        layer2_items = await layer2_semantic_match(requirement)
        self._partial_items.extend(layer2_items)

        self._report_progress(
            "requirement_association", 3, 6,
            phase="deep_association",
            history_matched=len(layer2_items),
            message="正在生成深度联想..."
        )

        layer3_items = await layer3_dual_model_deep(
            requirement, layer1_items, layer2_items, architect=self.architect
        )
        self._partial_items.extend(layer3_items)

        self._report_progress(
            "requirement_association", 4, 6,
            phase="devil_review",
            items_count=len(self._partial_items),
            message="正在进行反向审视..."
        )

        devil_items = await devil_advocate_review(
            requirement, self._partial_items, architect=self.architect
        )

        self._report_progress(
            "requirement_association", 5, 6,
            phase="building_result",
            items_count=len(self._partial_items),
            devil_items_count=len(devil_items)
        )

        enhanced = self._build_enhanced_requirement(requirement, self._partial_items)

        self._report_progress(
            "requirement_association", 6, 6,
            phase="complete",
            total_items=len(self._partial_items),
            domains=domains
        )

        return AssociationResult(
            items=self._partial_items,
            enhanced_requirement=enhanced,
            domain_matched=domains[0] if domains else "",
            domains_matched=domains,
            history_matched_count=len(layer2_items),
            llm_called=len(layer3_items) > 0,
            dual_model_used=len(layer3_items) > 0,
            devil_review_items=devil_items,
            elapsed_seconds=0.0,
            skipped=False
        )

    def _build_enhanced_requirement(
        self, original: str, items: List[AssociationItem]
    ) -> str:
        accepted = [i for i in items if i.confidence >= CONFIDENCE_DEFAULT_SHOW]
        if not accepted:
            return original

        parts = [original, "\n\n[需求联想增强 - 系统补全项]"]
        for cat in ["functional", "architectural", "risk", "decision"]:
            cat_items = [i for i in accepted if i.category == cat]
            if cat_items:
                cat_label = {
                    "functional": "功能需求",
                    "architectural": "架构影响",
                    "risk": "潜在风险",
                    "decision": "关键决策",
                }.get(cat, cat)
                parts.append(f"\n{cat_label}:")
                for item in cat_items:
                    parts.append(f"  - {item.content} (来源: {item.source}, 置信度: {item.confidence:.1f})")

        return "\n".join(parts)

    def _classify_items_for_display(
        self, items: List[AssociationItem]
    ) -> Dict[str, Any]:
        default_show = []
        collapsed = []
        for item in items:
            if item.confidence >= CONFIDENCE_DEFAULT_SHOW:
                default_show.append(item)
            elif item.confidence >= CONFIDENCE_DISPLAY_THRESHOLD:
                collapsed.append(item)

        categories = {}
        for item in default_show:
            if item.category not in categories:
                categories[item.category] = {"shown": [], "collapsed": []}
            categories[item.category]["shown"].append({
                "content": item.content,
                "source": item.source,
                "confidence": round(item.confidence, 2),
                "sub_category": item.sub_category,
                "impact": item.impact,
            })

        for item in collapsed:
            if item.category not in categories:
                categories[item.category] = {"shown": [], "collapsed": []}
            categories[item.category]["collapsed"].append({
                "content": item.content,
                "source": item.source,
                "confidence": round(item.confidence, 2),
                "sub_category": item.sub_category,
                "impact": item.impact,
            })

        return categories