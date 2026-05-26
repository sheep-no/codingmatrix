"""
v5.1.0 需求理解深度增强 - 单元测试

覆盖:
1. FAISS 向量索引管理
2. 功能清单自动生成
3. 领域模板自动萃取
4. 双模型交叉联想合并
5. 跨领域联想
6. 魔鬼代言人反向审视
7. 需求覆盖校验
8. AssociationFeedbackTracker (拒绝理由 + 显式反馈)
"""

import json
import pytest
import asyncio
import sqlite3
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.agent.orchestrator_requirements import (
    RequirementAssociationMixin,
    AssociationItem,
    AssociationResult,
    AssociationFeedbackTracker,
)
from app.agent.orchestrator_requirements.domain_detection import _detect_domains, _detect_domain
from app.agent.orchestrator_requirements.layer3_dual_model import merge_dual_model_results
from app.agent.orchestrator_requirements.devil_advocate import parse_devil_response
from app.agent.orchestrator_requirements.layer1_template import layer1_cross_domain_template


class FakeMixin(RequirementAssociationMixin):
    def __init__(self):
        self.callback = None
        self._start_time = 0
        self._current_phase = ""
        self.architect = None

    def _report_progress(self, step, current, total, **kwargs):
        pass


@pytest.fixture
def mixin():
    return FakeMixin()


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


class TestVectorIndexManager:

    def test_create_empty_index(self, temp_dir):
        from app.agent.vector_index import VectorIndexManager
        with patch.object(VectorIndexManager, '__init__', lambda self: None):
            vi = VectorIndexManager()
            vi._index = None
            vi._id_map = {}
            vi._next_id = 0
            vi._loaded = False
            vi._create_empty_index()
            assert vi._index is not None
            assert vi._index.ntotal == 0

    @pytest.mark.asyncio
    async def test_search_empty_index(self):
        from app.agent.vector_index import VectorIndexManager
        vi = VectorIndexManager()
        vi._loaded = True
        vi._index = MagicMock()
        vi._index.ntotal = 0
        results = await vi.search("test query")
        assert results == []


class TestProjectMetadataManager:

    def test_load_empty(self, temp_dir):
        from app.agent.project_metadata import ProjectMetadataManager
        with patch('app.agent.project_metadata.METADATA_PATH', temp_dir / "meta.json"):
            pm = ProjectMetadataManager()
            assert pm.total_count() == 0
            assert pm.count_with_features() == 0

    def test_add_and_count(self, temp_dir):
        from app.agent.project_metadata import ProjectMetadataManager
        meta_path = temp_dir / "meta.json"
        with patch('app.agent.project_metadata.METADATA_PATH', meta_path):
            pm = ProjectMetadataManager()
            pm._projects = [
                {"project_id": "p1", "requirement": "银行系统", "domain": "banking",
                 "feature_list": ["登录", "转账"], "file_count": 5},
                {"project_id": "p2", "requirement": "电商", "domain": "ecommerce",
                 "feature_list": [], "file_count": 3},
            ]
            pm._save()
            assert pm.total_count() == 2
            assert pm.count_with_features() == 1

    def test_get_projects_by_domain(self, temp_dir):
        from app.agent.project_metadata import ProjectMetadataManager
        meta_path = temp_dir / "meta.json"
        with patch('app.agent.project_metadata.METADATA_PATH', meta_path):
            pm = ProjectMetadataManager()
            pm._projects = [
                {"project_id": "p1", "domain": "banking", "feature_list": ["x"]},
                {"project_id": "p2", "domain": "ecommerce", "feature_list": ["y"]},
                {"project_id": "p3", "domain": "banking", "feature_list": ["z"]},
            ]
            pm._save()
            banking = pm.get_projects_by_domain("banking")
            assert len(banking) == 2


class TestAssociationFeedbackTracker:

    def test_record_and_stats(self, temp_dir):
        db_path = temp_dir / "feedback.db"
        with patch.object(AssociationFeedbackTracker, 'DB_PATH', db_path):
            tracker = AssociationFeedbackTracker()
            tracker.record_choice(
                "session_1", "银行系统",
                [{"category": "functional", "content": "转账", "source": "domain_template"}],
                "accepted"
            )
            tracker.record_choice(
                "session_1", "银行系统",
                [{"category": "functional", "content": "贷款", "source": "llm_association",
                  "rejection_reason": "out_of_scope"}],
                "rejected"
            )
            stats = tracker.get_feedback_stats()
            assert "domain_template:accepted" in stats
            assert "llm_association:rejected" in stats

    def test_rejection_reason_stats(self, temp_dir):
        db_path = temp_dir / "feedback.db"
        with patch.object(AssociationFeedbackTracker, 'DB_PATH', db_path):
            tracker = AssociationFeedbackTracker()
            tracker.record_choice(
                "s1", "req",
                [{"category": "functional", "content": "x", "source": "template",
                  "rejection_reason": "irrelevant"}],
                "rejected"
            )
            tracker.record_choice(
                "s1", "req",
                [{"category": "functional", "content": "y", "source": "template",
                  "rejection_reason": "out_of_scope"}],
                "rejected"
            )
            reasons = tracker.get_rejection_reason_stats()
            assert "irrelevant" in reasons
            assert "out_of_scope" in reasons

    def test_record_helpfulness(self, temp_dir):
        db_path = temp_dir / "feedback.db"
        with patch.object(AssociationFeedbackTracker, 'DB_PATH', db_path):
            tracker = AssociationFeedbackTracker()
            tracker.record_choice(
                "s1", "req",
                [{"category": "functional", "content": "x", "source": "template"}],
                "accepted"
            )
            tracker.record_helpfulness("s1", "req", "very_helpful")
            conn = tracker._conn
            cursor = conn.execute(
                "SELECT overall_helpfulness FROM association_feedback WHERE session_id='s1'"
            )
            rows = cursor.fetchall()
            assert any(r[0] == "very_helpful" for r in rows)


class TestDualModelMerge:

    def test_merge_both_agree(self):
        items_a = [
            AssociationItem(content="用户登录", category="functional", source="llm_a", confidence=0.8),
            AssociationItem(content="权限管理", category="functional", source="llm_a", confidence=0.7),
        ]
        items_b = [
            AssociationItem(content="用户登录", category="functional", source="llm_b", confidence=0.85),
            AssociationItem(content="数据备份", category="architectural", source="llm_b", confidence=0.6),
        ]
        merged = merge_dual_model_results(items_a, items_b)

        login_items = [i for i in merged if i.content == "用户登录"]
        assert len(login_items) == 1
        assert login_items[0].dual_model_agreement == "both_agree"
        assert login_items[0].confidence >= 0.85

        single_items = [i for i in merged if i.dual_model_agreement == "needs_confirmation"]
        assert len(single_items) >= 1

    def test_merge_single_model(self):
        items_a = [
            AssociationItem(content="登录", category="functional", source="llm_a", confidence=0.8),
        ]
        items_b = []
        merged = merge_dual_model_results(items_a, items_b)
        assert len(merged) == 1
        assert merged[0].dual_model_agreement == "needs_confirmation"


class TestCrossDomainDetection:

    def test_single_domain(self):
        domains = _detect_domains("银行转账系统，支持存款和贷款管理")
        assert "banking" in domains
        assert len(domains) >= 1

    def test_cross_domain(self):
        domains = _detect_domains("医疗电商平台，挂号和购物系统")
        assert "healthcare" in domains
        assert "ecommerce" in domains

    def test_no_domain(self):
        domains = _detect_domains("简单的待办事项管理工具")
        assert len(domains) == 0

    def test_max_three_domains(self):
        domains = _detect_domains("银行电商教育CMS后台管理平台")
        assert len(domains) <= 3


class TestDevilAdvocateReview:

    def test_parse_devil_response_json(self):
        response = json.dumps({
            "challenges": [
                {"target_item": "转账功能", "challenge": "缺少冲正流程", "severity": "high", "suggestion": "添加冲正机制"},
                {"target_item": "用户认证", "challenge": "未考虑双因素", "severity": "medium", "suggestion": "添加短信验证"},
            ]
        })
        result = parse_devil_response(response)
        assert len(result) == 2
        assert result[0]["challenge"] == "缺少冲正流程"
        assert result[0]["severity"] == "high"

    def test_parse_devil_response_empty(self):
        result = parse_devil_response("no json here")
        assert result == []

    def test_parse_devil_partial(self):
        response = json.dumps({
            "challenges": [
                {"challenge": "some challenge"},
            ]
        })
        result = parse_devil_response(response)
        assert len(result) == 0


class TestRequirementCoverageCheck:

    def test_no_association_result(self):
        from app.agent.orchestrator_generation.coverage_checker import check_requirement_coverage
        result = check_requirement_coverage("req", {}, [], None)
        assert result["checked"] == False
        assert result["coverage_rate"] == 1.0

    def test_good_coverage(self):
        from app.agent.orchestrator_generation.coverage_checker import check_requirement_coverage
        from app.agent.orchestrator_requirements import AssociationResult, AssociationItem
        association_result = AssociationResult(
            items=[
                AssociationItem(content="用户登录认证", category="functional", source="template", confidence=0.8),
                AssociationItem(content="商品浏览搜索", category="functional", source="template", confidence=0.9),
            ],
            skipped=False
        )
        result = check_requirement_coverage(
            "req",
            {"project_type": "web app", "tech_stack": ["python", "vue"]},
            [{"path": "app/auth/login.py", "description": "用户登录认证模块"},
             {"path": "app/products/search.py", "description": "商品浏览搜索"}],
            association_result
        )
        assert result["checked"] == True
        assert result["coverage_rate"] > 0.5

    def test_poor_coverage(self):
        from app.agent.orchestrator_generation.coverage_checker import check_requirement_coverage
        from app.agent.orchestrator_requirements import AssociationResult, AssociationItem
        association_result = AssociationResult(
            items=[
                AssociationItem(content="跨行转账冲正", category="functional", source="template", confidence=0.8),
                AssociationItem(content="反洗钱监测", category="functional", source="template", confidence=0.7),
            ],
            skipped=False
        )
        result = check_requirement_coverage(
            "req",
            {"project_type": "web app"},
            [{"path": "app/main.py", "description": "主入口"}],
            association_result
        )
        assert result["checked"] == True
        assert result["coverage_rate"] < 0.5
        assert len(result["uncovered"]) >= 1


class TestLayer1CrossDomainTemplate:

    @pytest.mark.asyncio
    async def test_cross_domain_merge(self):
        domains = _detect_domains("银行支付电商平台")
        items = await layer1_cross_domain_template("银行支付电商平台", domains)
        banking_items = [i for i in items if i.source.startswith("domain_template:banking")]
        ecommerce_items = [i for i in items if i.source.startswith("domain_template:ecommerce")]
        assert len(banking_items) > 0
        assert len(ecommerce_items) > 0

    @pytest.mark.asyncio
    async def test_deduplication(self):
        domains = _detect_domains("银行支付电商")
        items = await layer1_cross_domain_template("银行支付电商", domains)
        contents = [i.content for i in items]
        assert len(contents) == len(set(contents))


class TestLayer2SemanticMatch:

    @pytest.mark.asyncio
    async def test_no_data_returns_empty(self):
        from app.agent.orchestrator_requirements.layer2_semantic import layer2_semantic_match
        items = await layer2_semantic_match("银行系统")
        assert isinstance(items, list)


class TestTemplateExtractor:

    def test_parse_template_response(self):
        from app.agent.template_extractor import TemplateExtractor
        extractor = TemplateExtractor()
        response = json.dumps({
            "domain": "banking",
            "version": "auto_extracted",
            "core_modules": [
                {"name": "账户管理", "category": "core", "impact": "基础", "options": ["A", "B"], "default": "A"}
            ],
            "non_functional_requirements": [
                {"category": "security", "item": "双因素认证", "priority": "high"}
            ],
            "common_pitfalls": ["并发问题"],
            "key_decisions": [
                {"question": "锁策略", "impact": "architecture", "options": ["悲观", "乐观"]}
            ]
        })
        result = extractor._parse_template_response(response, "banking")
        assert result is not None
        assert result["domain"] == "banking"
        assert len(result["core_modules"]) >= 1

    def test_parse_invalid_response(self):
        from app.agent.template_extractor import TemplateExtractor
        extractor = TemplateExtractor()
        result = extractor._parse_template_response("not json", "banking")
        assert result is None


class TestFeatureExtractionParsing:

    def test_parse_json_features(self):
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()
        response = json.dumps({"features": ["用户登录", "商品搜索", "订单管理"]})
        result = pm._parse_feature_response(response)
        assert len(result) == 3
        assert "用户登录" in result

    def test_parse_text_features(self):
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()
        response = "- 用户登录认证\n- 商品浏览和搜索\n## 注释\n- 订单创建管理"
        result = pm._parse_feature_response(response)
        assert len(result) >= 2

    def test_fallback_features(self):
        from app.agent.project_metadata import ProjectMetadataManager
        pm = ProjectMetadataManager()
        result = pm._fallback_feature_list("银行系统", {
            "app/auth.py": "认证模块",
            "app/transfer.py": "转账模块",
        })
        assert len(result) >= 1