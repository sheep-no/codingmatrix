"""补测 EvaluationMixin 的完整评价流程与 JSON 解析边界。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.complexity import ComplexityAnalysis, ProjectComplexity
from app.agent.orchestrator_generation import evaluate_mixin
from app.agent.orchestrator_generation.evaluate_mixin import EvaluationMixin
from app.agent.orchestrator_requirements.data_models import AssociationResult


class _FakeOrchestrator(EvaluationMixin):
    def __init__(self, use_dynamic_topology=True):
        self.use_dynamic_topology = use_dynamic_topology
        self.api_key_token = "token"
        self.provider_id = "provider"
        self.cancel_event = None
        self.complexity = None
        self.model_assignment = None
        self.model_router = None
        self.progress = []
        self.phases = []

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))

    def _update_phase(self, phase):
        self.phases.append(phase)

    async def _generate_requirement_associations(self, requirement, level):
        return AssociationResult(
            skipped=False,
            domain_matched="banking",
            domains_matched=["banking", "risk"],
            items=[],
            devil_review_items=[{"challenge": "缺少冲正", "target_item": "转账", "severity": "high"}],
            enhanced_requirement="增强后的需求",
        )


@pytest.fixture
def orchestrator(monkeypatch):
    agent = _FakeOrchestrator()

    complexity = ComplexityAnalysis(
        level=ProjectComplexity.MEDIUM,
        estimated_files=8,
        has_frontend=True,
        has_backend=True,
        has_database=True,
        key_technologies=["fastapi"],
        risk_factors=["并发"],
    )
    assignment = SimpleNamespace(architect_model="arch-model", reviewer_model="review-model")

    class _Analyzer:
        def analyze(self, requirement):
            return complexity

    class _Router:
        def get_assignment(self):
            return assignment

    class _Architect:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def design_architecture(self, requirement, complexity):
            return {
                "project_type": "web",
                "tech_stack": ["fastapi", "vue"],
                "file_plan": [{"path": "app/main.py", "description": "入口"}],
                "api_spec": {"paths": {}},
                "db_schema": {"tables": []},
            }

    class _Reviewer:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(evaluate_mixin, "ComplexityAnalyzer", _Analyzer)
    monkeypatch.setattr(evaluate_mixin, "LayeredModelRouter", _Router)
    monkeypatch.setattr(evaluate_mixin, "Architect", _Architect)
    monkeypatch.setattr(evaluate_mixin, "CodeReviewer", _Reviewer)

    agent._evaluate_requirement = AsyncMock(
        return_value={"completeness": {"score": 90}, "recommendations": ["补充测试"]}
    )
    agent._evaluate_architecture = AsyncMock(
        return_value={"architecture_quality": {"score": 88}, "recommendations": ["分层"]}
    )
    return agent


class TestEvaluateFlow:
    @pytest.mark.asyncio
    async def test_full_evaluation_returns_report(self, orchestrator):
        result = await orchestrator.evaluate("做一个银行转账系统")

        assert result["mode"] == "evaluation_only"
        assert result["success"] is True
        assert result["complexity"]["level"] == "medium"
        assert result["association_result"]["domain_matched"] == "banking"
        assert result["association_result"]["items_count"] == 0
        assert result["risk_evaluation"]["critical_risks"] == 1
        assert result["overall_assessment"]["grade"] in {"A", "B", "C", "D"}
        assert result["files_generated"] == 0
        assert result["models_used"] == {
            "architect": "arch-model",
            "reviewer": "review-model",
        }
        assert orchestrator.phases == ["evaluation"]
        assert len(orchestrator.progress) == 5

    @pytest.mark.asyncio
    async def test_static_topology_skips_model_router(self, monkeypatch):
        agent = _FakeOrchestrator(use_dynamic_topology=False)
        agent.model_assignment = SimpleNamespace(
            architect_model="arch-model", reviewer_model="review-model"
        )
        complexity = ComplexityAnalysis(
            level=ProjectComplexity.SIMPLE,
            estimated_files=1,
            has_frontend=False,
            has_backend=False,
            has_database=False,
        )

        class _Analyzer:
            def analyze(self, requirement):
                return complexity

        class _Architect:
            def __init__(self, *args, **kwargs):
                pass

            async def design_architecture(self, requirement, complexity):
                return {"project_type": "cli"}

        monkeypatch.setattr(evaluate_mixin, "ComplexityAnalyzer", _Analyzer)
        monkeypatch.setattr(evaluate_mixin, "Architect", _Architect)
        monkeypatch.setattr(evaluate_mixin, "CodeReviewer", _Architect)
        agent._evaluate_requirement = AsyncMock(return_value={"completeness": {"score": 50}})
        agent._evaluate_architecture = AsyncMock(return_value={"architecture_quality": {"score": 50}})

        result = await agent.evaluate("写个脚本")

        assert agent.model_router is None
        assert result["mode"] == "evaluation_only"

    @pytest.mark.asyncio
    async def test_missing_assignment_raises(self, orchestrator):
        orchestrator.model_assignment = None

        class _Router:
            def get_assignment(self):
                return None

        evaluate_mixin.LayeredModelRouter = _Router

        with pytest.raises(RuntimeError, match="model assignment is required"):
            await orchestrator.evaluate("需求")


class TestEvaluateArchitecture:
    @pytest.mark.asyncio
    async def test_success_returns_parsed_json(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(reviewer_model="review-model")
        payload = json.dumps({"architecture_quality": {"score": 77}})

        async def fake_call_llm(**kwargs):
            assert kwargs["model"] == "review-model"
            return payload

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await agent._evaluate_architecture(
            "需求",
            {
                "tech_stack": ["fastapi"],
                "project_type": "web",
                "file_plan": [{"path": "app/main.py", "description": "入口"}],
            },
        )

        assert result["architecture_quality"]["score"] == 77

    @pytest.mark.asyncio
    async def test_missing_optional_architecture_fields_use_defaults(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(reviewer_model="review-model")
        seen = {}

        async def fake_call_llm(**kwargs):
            seen["prompt"] = kwargs["prompt"]
            return json.dumps({"architecture_quality": {"score": 60}})

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        await agent._evaluate_architecture("需求", {})

        assert "unknown" in seen["prompt"]
        assert "- 技术栈：[]" in seen["prompt"]

    @pytest.mark.asyncio
    async def test_llm_failure_wraps_in_runtime_error(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(reviewer_model="review-model")

        async def fake_call_llm(**kwargs):
            raise ConnectionError("boom")

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        with pytest.raises(RuntimeError, match="architecture evaluation failed"):
            await agent._evaluate_architecture("需求", {})

    @pytest.mark.asyncio
    async def test_runtime_error_is_reraised_unchanged(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(reviewer_model="review-model")

        async def fake_call_llm(**kwargs):
            raise RuntimeError("already classified")

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        with pytest.raises(RuntimeError, match="already classified"):
            await agent._evaluate_architecture("需求", {})


class TestEvaluateRequirement:
    @pytest.mark.asyncio
    async def test_success_returns_parsed_json(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(architect_model="arch-model")

        async def fake_call_llm(**kwargs):
            assert kwargs["model"] == "arch-model"
            return json.dumps({"completeness": {"score": 82}})

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await agent._evaluate_requirement(
            "需求", {"project_type": "web", "tech_stack": ["vue"], "file_plan": [1, 2]}
        )

        assert result["completeness"]["score"] == 82

    @pytest.mark.asyncio
    async def test_missing_architecture_fields_use_defaults(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(architect_model="arch-model")
        seen = {}

        async def fake_call_llm(**kwargs):
            seen["prompt"] = kwargs["prompt"]
            return json.dumps({"completeness": {"score": 60}})

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        await agent._evaluate_requirement("需求", {})

        assert "unknown" in seen["prompt"]
        assert "- 规划文件数：0" in seen["prompt"]

    @pytest.mark.asyncio
    async def test_runtime_error_is_reraised_unchanged(self, monkeypatch):
        agent = _FakeOrchestrator()
        agent.model_assignment = SimpleNamespace(architect_model="arch-model")

        async def fake_call_llm(**kwargs):
            raise RuntimeError("classified")

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        with pytest.raises(RuntimeError, match="classified"):
            await agent._evaluate_requirement("需求", {})


class TestOverallGrades:
    def _agent(self):
        return _FakeOrchestrator()

    def test_grade_b(self):
        result = self._agent()._build_overall_assessment(
            {"completeness": {"score": 70}},
            {"architecture_quality": {"score": 70}},
            {"critical_risks": 0},
        )
        assert result["grade"] == "B"
        assert "基本完整" in result["summary"]

    def test_grade_c(self):
        result = self._agent()._build_overall_assessment(
            {"completeness": {"score": 50}},
            {"architecture_quality": {"score": 50}},
            {"critical_risks": 0},
        )
        assert result["grade"] == "C"
        assert "明显缺失" in result["summary"]

    def test_grade_d(self):
        result = self._agent()._build_overall_assessment(
            {"completeness": {"score": 10}},
            {"architecture_quality": {"score": 10}},
            {"critical_risks": 0},
        )
        assert result["grade"] == "D"
        assert "严重不足" in result["summary"]

    def test_recommendations_are_capped_at_ten(self):
        result = self._agent()._build_overall_assessment(
            {"completeness": {"score": 90}, "recommendations": [f"r{i}" for i in range(8)]},
            {"architecture_quality": {"score": 90}, "recommendations": [f"a{i}" for i in range(8)]},
            {"critical_risks": 0},
        )
        assert len(result["recommendations"]) == 10


class TestRiskBranchesWithoutComplexity:
    def test_missing_complexity_skips_backend_and_db_risks(self):
        agent = _FakeOrchestrator()
        agent.complexity = None

        result = agent._evaluate_risks(
            "需求",
            {"tech_stack": ["python"], "file_plan": []},
            None,
        )

        assert result["risks"] == []
        assert result["overall_severity"] == "low"

    def test_medium_only_risks_yield_medium_severity(self):
        agent = _FakeOrchestrator()
        agent.complexity = None

        result = agent._evaluate_risks(
            "需求",
            {"tech_stack": ["a", "b", "c", "d", "e", "f", "g"], "file_plan": []},
            None,
        )

        assert result["overall_severity"] == "medium"
        assert result["medium_risks"] == 1
        assert result["critical_risks"] == 0

    def test_devil_items_without_complexity(self):
        agent = _FakeOrchestrator()
        agent.complexity = None
        association = AssociationResult(
            devil_review_items=[{"challenge": "边界", "severity": "low"}]
        )

        result = agent._evaluate_risks(
            "需求", {"tech_stack": [], "file_plan": []}, association
        )

        assert result["risks"][0]["type"] == "devil_advocate"
        assert result["overall_severity"] == "low"
        assert result["low_risks"] == 1


class TestParseEvaluationJson:
    def _agent(self):
        return _FakeOrchestrator()

    @pytest.mark.parametrize(
        "payload",
        [
            json.dumps({"score": 80}),
            json.dumps({"completeness": {"score": 80}}),
            json.dumps({"architecture_quality": {"score": 80}}),
        ],
    )
    def test_accepts_any_recognized_key(self, payload):
        assert self._agent()._parse_evaluation_json(payload, "requirement")

    def test_json_decode_error_is_wrapped(self):
        with pytest.raises(RuntimeError, match="was not valid JSON"):
            self._agent()._parse_evaluation_json("{broken", "requirement")

    def test_json_decode_error_from_braced_body_is_wrapped(self):
        # 正则能匹配到 {...}，但内部不是合法 JSON，必须走 JSONDecodeError 分支
        with pytest.raises(RuntimeError, match="was not valid JSON"):
            self._agent()._parse_evaluation_json('{"a": }', "requirement")

    def test_missing_required_keys_raises(self):
        with pytest.raises(RuntimeError, match="did not include score"):
            self._agent()._parse_evaluation_json('{"other": 1}', "requirement")
