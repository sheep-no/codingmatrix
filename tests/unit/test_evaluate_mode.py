"""
EvaluationMixin (evaluate_only 模式) 单元测试

覆盖:
1. EvaluationMixin.evaluate() 入口
2. _evaluate_requirement (需求评价)
3. _evaluate_architecture (架构评价)
4. _evaluate_risks (风险评价 - 确定性规则)
5. _build_overall_assessment (综合评估)
6. 评价模式 vs 生成模式分流
7. API 端点 schema 验证
"""

import json
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.orchestrator_generation.evaluate_mixin import EvaluationMixin, EVALUATION_MODEL
from app.agent.orchestrator_requirements import AssociationResult, AssociationItem


class FakeOrchestrator(EvaluationMixin):
    def __init__(self):
        self.callback = None
        self._start_time = 0
        self._current_phase = ""
        self.architect = None
        self.reviewer = None
        self.analyzer = None
        self.model_router = None
        self.model_assignment = None
        self.complexity = None
        self.evaluation_only = False

    def _report_progress(self, step, current, total, **kwargs):
        pass

    def _update_phase(self, phase):
        self._current_phase = phase


@pytest.fixture
def mixin():
    return FakeOrchestrator()


class TestEvaluationParsing:

    def test_parse_evaluation_json_valid(self, mixin):
        response = json.dumps({
            "completeness": {"score": 85, "missing_items": ["错误处理"]},
            "feasibility": {"score": 90, "technical_risks": ["并发"]},
            "recommendations": ["添加错误处理"]
        })
        result = mixin._parse_evaluation_json(response, "requirement")
        assert result.get("completeness", {}).get("score") == 85

    def test_parse_evaluation_json_invalid(self, mixin):
        result = mixin._parse_evaluation_json("not json", "requirement")
        assert result.get("error") is not None

    def test_fallback_evaluation(self, mixin):
        result = mixin._fallback_evaluation("architecture", "模型调用失败")
        assert result.get("score") == 0
        assert "architecture" in result.get("error", "")


class TestEvaluateRisks:

    def test_high_file_count_risk(self, mixin):
        architecture = {
            "tech_stack": ["python", "vue"],
            "file_plan": [{"path": f"file_{i}.py"} for i in range(60)],
            "has_backend": True,
            "has_database": True,
        }
        association_result = AssociationResult(skipped=True)
        result = mixin._evaluate_risks("req", architecture, association_result)
        assert result["total_risks"] >= 1
        complexity_risks = [r for r in result["risks"] if r["type"] == "complexity"]
        assert len(complexity_risks) == 1
        assert complexity_risks[0]["severity"] == "high"

    def test_missing_api_spec_risk(self, mixin):
        architecture = {
            "tech_stack": ["python", "fastapi"],
            "file_plan": [{"path": "app/main.py"}],
            "has_backend": True,
            "has_database": False,
        }
        association_result = AssociationResult(skipped=True)
        result = mixin._evaluate_risks("req", architecture, association_result)
        api_risks = [r for r in result["risks"] if r["type"] == "missing_api"]
        assert len(api_risks) == 1

    def test_missing_db_schema_risk(self, mixin):
        architecture = {
            "tech_stack": ["python"],
            "file_plan": [{"path": "app/main.py"}],
            "has_backend": True,
            "has_database": True,
        }
        association_result = AssociationResult(skipped=True)
        result = mixin._evaluate_risks("req", architecture, association_result)
        db_risks = [r for r in result["risks"] if r["type"] == "missing_db_schema"]
        assert len(db_risks) == 1

    def test_devil_advocate_risks(self, mixin):
        architecture = {
            "tech_stack": ["python"],
            "file_plan": [{"path": "app/main.py"}],
            "has_backend": False,
        }
        association_result = AssociationResult(
            skipped=False,
            devil_review_items=[
                {"target_item": "转账功能", "challenge": "缺少冲正流程",
                 "severity": "high", "suggestion": "添加冲正"}
            ]
        )
        result = mixin._evaluate_risks("req", architecture, association_result)
        devil_risks = [r for r in result["risks"] if r["type"] == "devil_advocate"]
        assert len(devil_risks) == 1
        assert devil_risks[0]["severity"] == "high"

    def test_no_risks(self, mixin):
        architecture = {
            "tech_stack": ["python"],
            "file_plan": [{"path": "app/main.py"}],
            "has_backend": False,
        }
        association_result = AssociationResult(skipped=True)
        result = mixin._evaluate_risks("req", architecture, association_result)
        assert result["total_risks"] == 0
        assert result["overall_severity"] == "low"

    def test_tech_diversity_risk(self, mixin):
        architecture = {
            "tech_stack": ["python", "vue", "redis", "postgres", "celery", "docker", "nginx"],
            "file_plan": [{"path": "app/main.py"}],
            "has_backend": False,
        }
        association_result = AssociationResult(skipped=True)
        result = mixin._evaluate_risks("req", architecture, association_result)
        tech_risks = [r for r in result["risks"] if r["type"] == "tech_diversity"]
        assert len(tech_risks) == 1


class TestOverallAssessment:

    def test_grade_a(self, mixin):
        req_eval = {"completeness": {"score": 90}, "recommendations": ["优化X"]}
        arch_eval = {"architecture_quality": {"score": 85}, "recommendations": ["优化Y"]}
        risk_eval = {"critical_risks": 0, "medium_risks": 0}
        result = mixin._build_overall_assessment(req_eval, arch_eval, risk_eval)
        assert result["grade"] == "A"
        assert result["overall_score"] >= 80

    def test_grade_c_with_critical_risks(self, mixin):
        req_eval = {"completeness": {"score": 70}, "recommendations": []}
        arch_eval = {"architecture_quality": {"score": 70}, "recommendations": []}
        risk_eval = {"critical_risks": 2, "medium_risks": 1}
        result = mixin._build_overall_assessment(req_eval, arch_eval, risk_eval)
        assert result["grade"] in ["C", "D"]
        assert result["overall_score"] < 60

    def test_recommendations_merged(self, mixin):
        req_eval = {"completeness": {"score": 80}, "recommendations": ["需求建议1", "需求建议2"]}
        arch_eval = {"architecture_quality": {"score": 80}, "recommendations": ["架构建议1"]}
        risk_eval = {"critical_risks": 0}
        result = mixin._build_overall_assessment(req_eval, arch_eval, risk_eval)
        assert len(result["recommendations"]) >= 3


class TestEvaluationModeRouting:

    def test_evaluation_only_flag(self):
        from app.agent.orchestrator import OrchestratorAgent
        agent = OrchestratorAgent(output_dir="./tmp_test", evaluation_only=True)
        assert agent.evaluation_only == True

    def test_generate_routes_to_evaluate(self):
        from app.agent.orchestrator_generation.mixin import GenerationMixin

        class FakeGen(GenerationMixin):
            def __init__(self):
                self.evaluation_only = True
                self._report_progress = lambda *a, **kw: None

            async def evaluate(self, requirement):
                return {"mode": "evaluation_only", "success": True}

        gen = FakeGen()
        result = asyncio.get_event_loop().run_until_complete(
            gen.generate("银行转账系统")
        )
        assert result["mode"] == "evaluation_only"


class TestAPISchemas:

    def test_evaluate_request_schema(self):
        from app.api.v1.ai_agent.schemas import EvaluateRequest
        req = EvaluateRequest(requirement="开发一个电商系统")
        assert req.requirement == "开发一个电商系统"
        assert req.output_dir is None
        assert req.session_id is None

    def test_evaluate_response_schema(self):
        from app.api.v1.ai_agent.schemas import EvaluateResponse
        resp = EvaluateResponse(
            mode="evaluation_only",
            requirement="银行系统",
            overall_assessment={"grade": "B", "overall_score": 75},
            elapsed_seconds=5.2
        )
        assert resp.mode == "evaluation_only"
        assert resp.success == True

    def test_orchestrator_request_with_evaluation_only(self):
        from app.api.v1.ai_agent.schemas import OrchestratorRequest
        req = OrchestratorRequest(
            requirement="银行系统",
            evaluation_only=True
        )
        assert req.evaluation_only == True