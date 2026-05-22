import time
import json
import re
import logging
from typing import Dict, Any, List, Optional

from app.agent.complexity import ComplexityAnalyzer
from app.agent.specialists import Architect, CodeReviewer
from app.agent.dynamic_model_router import LayeredModelRouter
from app.agent.tracing import traced

logger = logging.getLogger(__name__)

EVALUATION_MODEL = "THUDM/GLM-Z1-9B-0414"


class EvaluationMixin:

    @traced("orchestrator.evaluate", attributes={"component": "orchestrator", "mode": "evaluation_only"})
    async def evaluate(self, requirement: str) -> Dict[str, Any]:
        start_time = time.time()
        self._update_phase("evaluation")

        self._report_progress("evaluation", 1, 5, phase="analyzing_complexity",
                              message="正在分析需求复杂度...")

        self.analyzer = ComplexityAnalyzer()
        self.complexity = await self.analyzer.analyze_with_llm(requirement)

        self._report_progress("evaluation", 2, 5, phase="designing_analysis",
                              complexity=self.complexity.level.value,
                              estimated_files=self.complexity.estimated_files,
                              message="正在设计评价框架...")

        self.model_router = LayeredModelRouter()
        self.model_assignment = self.model_router.get_assignment(self.complexity.level)

        self.architect = Architect("评价架构师", self.model_assignment.architect_model,
                                task_type="review")
        self.reviewer = CodeReviewer("评价审查员", self.model_assignment.reviewer_model,
                                     task_type="review")

        self._report_progress("evaluation", 3, 5, phase="requirement_analysis",
                              message="正在分析需求...")

        association_result = await self._generate_requirement_associations(
            requirement, self.complexity.level.value
        )

        self._report_progress("evaluation", 4, 5, phase="deep_evaluation",
                              message="正在进行深度评价...")

        architecture = await self.architect.design_architecture(requirement, self.complexity)

        requirement_evaluation = await self._evaluate_requirement(requirement, architecture)
        architecture_evaluation = await self._evaluate_architecture(requirement, architecture)
        risk_evaluation = self._evaluate_risks(requirement, architecture, association_result)

        self._report_progress("evaluation", 5, 5, phase="complete",
                              message="评价完成")

        elapsed = time.time() - start_time

        return {
            "mode": "evaluation_only",
            "requirement": requirement,
            "complexity": {
                "level": self.complexity.level.value,
                "estimated_files": self.complexity.estimated_files,
                "has_frontend": self.complexity.has_frontend,
                "has_backend": self.complexity.has_backend,
                "has_database": self.complexity.has_database,
                "key_technologies": self.complexity.key_technologies,
                "risk_factors": self.complexity.risk_factors,
            },
            "architecture": architecture,
            "association_result": {
                "skipped": association_result.skipped,
                "domain_matched": association_result.domain_matched,
                "domains_matched": association_result.domains_matched,
                "items_count": len(association_result.items),
                "devil_review_items": association_result.devil_review_items,
                "enhanced_requirement": association_result.enhanced_requirement,
            },
            "requirement_evaluation": requirement_evaluation,
            "architecture_evaluation": architecture_evaluation,
            "risk_evaluation": risk_evaluation,
            "overall_assessment": self._build_overall_assessment(
                requirement_evaluation, architecture_evaluation, risk_evaluation
            ),
            "elapsed_seconds": elapsed,
            "success": True,
            "files_generated": 0,
            "files": [],
            "errors": [],
            "warnings": [],
            "models_used": {
                "architect": self.model_assignment.architect_model,
                "reviewer": self.model_assignment.reviewer_model,
            },
        }

    async def _evaluate_requirement(
        self, requirement: str, architecture: Dict
    ) -> Dict[str, Any]:
        prompt = f"""你是一位资深需求分析专家。请对以下需求进行全面评价，只评价不修改。

需求描述：
{requirement}

架构设计摘要：
- 项目类型：{architecture.get('project_type', 'unknown')}
- 技术栈：{architecture.get('tech_stack', [])}
- 规划文件数：{len(architecture.get('file_plan', []))}

请从以下维度评价需求，严格按照 JSON 格式输出：

{
  "completeness": {
    "score": 0-100,
    "missing_items": ["缺失的功能点1", "缺失的功能点2"],
    "ambiguous_points": ["模糊描述1", "模糊描述2"]
  },
  "feasibility": {
    "score": 0-100,
    "technical_risks": ["技术风险1", "技术风险2"],
    "resource_estimation": "资源估算说明"
  },
  "clarity": {
    "score": 0-100,
    "vague_areas": ["需要澄清的区域1", "需要澄清的区域2"],
    "assumptions_needed": ["需要假设的前提1"]
  },
  "priority_alignment": {
    "score": 0-100,
    "core_features": ["核心功能1", "核心功能2"],
    "nice_to_have": ["锦上添花功能1"],
    "over_specified": ["过度细化部分1"]
  },
  "recommendations": ["建议1", "建议2", "建议3"]
}"""

        try:
            from app.utils import call_llm
            response = await call_llm(
                model=EVALUATION_MODEL,
                prompt=prompt,
            )
            return self._parse_evaluation_json(response, "requirement")
        except Exception as e:
            logger.warning(f"需求评价调用失败: {e}")
            return self._fallback_evaluation("requirement", str(e))

    async def _evaluate_architecture(
        self, requirement: str, architecture: Dict
    ) -> Dict[str, Any]:
        tech_stack = architecture.get("tech_stack", [])
        file_plan = architecture.get("file_plan", [])
        project_type = architecture.get("project_type", "unknown")

        file_summary = "\n".join(
            f"  {f.get('path', '?')} - {f.get('description', '')}"
            for f in file_plan[:30]
        )

        prompt = f"""你是一位资深架构审查专家。请对以下架构设计进行全面评价，只评价不修改。

原始需求：
{requirement}

架构设计：
- 项目类型：{project_type}
- 技术栈：{tech_stack}
- 规划文件：
{file_summary}

请从以下维度评价架构，严格按照 JSON 格式输出：

{
  "architecture_quality": {
    "score": 0-100,
    "layering": "分层评价说明",
    "modularity": "模块化评价说明",
    "extensibility": "扩展性评价说明"
  },
  "tech_stack_fitness": {
    "score": 0-100,
    "appropriate_choices": ["合适的技术选型1"],
    "concerns": ["需要关注的技术选型1"],
    "alternatives": ["替代方案1"]
  },
  "requirement_coverage": {
    "score": 0-100,
    "covered_requirements": ["已覆盖的需求1"],
    "uncovered_requirements": ["未覆盖的需求1"],
    "over_engineered": ["过度设计1"]
  },
  "security_assessment": {
    "score": 0-100,
    "security_measures": ["安全措施1"],
    "vulnerabilities": ["潜在漏洞1"],
    "recommendations": ["安全建议1"]
  },
  "performance_assessment": {
    "score": 0-100,
    "potential_bottlenecks": ["性能瓶颈1"],
    "optimization_opportunities": ["优化机会1"]
  },
  "recommendations": ["建议1", "建议2"]
}"""

        try:
            from app.utils import call_llm
            response = await call_llm(
                model=EVALUATION_MODEL,
                prompt=prompt,
            )
            return self._parse_evaluation_json(response, "architecture")
        except Exception as e:
            logger.warning(f"架构评价调用失败: {e}")
            return self._fallback_evaluation("architecture", str(e))

    def _evaluate_risks(
        self, requirement: str,
        architecture: Dict,
        association_result: Any
    ) -> Dict[str, Any]:
        risks = []

        tech_stack = architecture.get("tech_stack", [])
        file_plan = architecture.get("file_plan", [])

        if len(file_plan) > 50:
            risks.append({
                "type": "complexity",
                "description": f"规划 {len(file_plan)} 个文件，项目复杂度较高，建议分阶段交付",
                "severity": "high",
            })

        if len(tech_stack) > 6:
            risks.append({
                "type": "tech_diversity",
                "description": f"技术栈包含 {len(tech_stack)} 种技术，集成复杂度较高",
                "severity": "medium",
            })

        if not architecture.get("api_spec") and architecture.get("has_backend"):
            risks.append({
                "type": "missing_api",
                "description": "后端项目缺少 API 规范定义",
                "severity": "high",
            })

        if not architecture.get("db_schema") and architecture.get("has_database"):
            risks.append({
                "type": "missing_db_schema",
                "description": "数据库项目缺少 Schema 定义",
                "severity": "high",
            })

        devil_items = association_result.devil_review_items if association_result else []
        for devil in devil_items:
            risks.append({
                "type": "devil_advocate",
                "description": f"[反向审视] {devil.get('challenge', '')}",
                "target": devil.get("target_item", ""),
                "severity": devil.get("severity", "medium"),
                "suggestion": devil.get("suggestion", ""),
            })

        critical_risks = [r for r in risks if r.get("severity") == "high"]
        medium_risks = [r for r in risks if r.get("severity") == "medium"]

        overall_severity = "high" if critical_risks else "medium" if medium_risks else "low"

        return {
            "total_risks": len(risks),
            "critical_risks": len(critical_risks),
            "medium_risks": len(medium_risks),
            "low_risks": len(risks) - len(critical_risks) - len(medium_risks),
            "overall_severity": overall_severity,
            "risks": risks,
        }

    def _build_overall_assessment(
        self,
        requirement_evaluation: Dict,
        architecture_evaluation: Dict,
        risk_evaluation: Dict,
    ) -> Dict[str, Any]:
        req_score = requirement_evaluation.get("completeness", {}).get("score", 0)
        arch_score = architecture_evaluation.get("architecture_quality", {}).get("score", 0)

        risk_penalty = risk_evaluation.get("critical_risks", 0) * 10
        overall_score = max(0, (req_score + arch_score) // 2 - risk_penalty)

        if overall_score >= 80:
            grade = "A"
            summary = "需求完整、架构合理，可以进入开发阶段"
        elif overall_score >= 60:
            grade = "B"
            summary = "需求基本完整，架构有优化空间，建议补充后再开发"
        elif overall_score >= 40:
            grade = "C"
            summary = "需求有明显缺失或架构有重要问题，需要补充完善后再开发"
        else:
            grade = "D"
            summary = "需求严重不足或架构有重大缺陷，不建议直接进入开发"

        all_recommendations = []
        all_recommendations.extend(requirement_evaluation.get("recommendations", []))
        all_recommendations.extend(architecture_evaluation.get("recommendations", []))

        return {
            "overall_score": overall_score,
            "grade": grade,
            "summary": summary,
            "recommendations": all_recommendations[:10],
        }

    def _parse_evaluation_json(self, response: str, eval_type: str) -> Dict[str, Any]:
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                parsed = json.loads(json_match.group())
                if parsed.get("score") or parsed.get("completeness"):
                    return parsed
        except json.JSONDecodeError:
            pass

        return self._fallback_evaluation(eval_type, "LLM 输出非 JSON")

    def _fallback_evaluation(self, eval_type: str, reason: str) -> Dict[str, Any]:
        return {
            "score": 0,
            "error": f"{eval_type} 评价降级: {reason}",
            "recommendations": [f"建议手动进行 {eval_type} 评价"],
        }