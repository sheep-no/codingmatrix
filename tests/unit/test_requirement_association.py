"""
RequirementAssociationMixin 单元测试

测试三层联想机制:
1. 领域模板匹配 (跨领域)
2. FAISS 语义检索 / 关键词匹配
3. 双模型交叉联想
4. 魔鬼代言人反向审视
"""

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.orchestrator_requirements import (
    RequirementAssociationMixin,
    AssociationItem,
    AssociationResult,
    DOMAIN_TEMPLATES_DIR,
    SKIP_COMPLEXITY_LEVELS,
    CONFIDENCE_DEFAULT_SHOW,
)
from app.agent.orchestrator_requirements.domain_detection import _detect_domains, _detect_domain
from app.agent.orchestrator_requirements.layer1_template import layer1_cross_domain_template, compute_template_confidence
from app.agent.orchestrator_requirements.layer2_semantic import check_history_data_available
from app.agent.orchestrator_requirements.layer3_dual_model import merge_dual_model_results
from app.agent.orchestrator_requirements.llm_prompts import parse_llm_response


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


class TestDomainDetection:

    def test_detect_banking(self):
        result = _detect_domain("银行转账系统，支持存款和贷款管理")
        assert result == "banking"

    def test_detect_ecommerce(self):
        result = _detect_domain("电商平台，购物车和订单管理系统")
        assert result == "ecommerce"

    def test_detect_cms(self):
        result = _detect_domain("CMS内容管理系统，文章发布和编辑")
        assert result == "cms"

    def test_detect_saas(self):
        result = _detect_domain("SaaS后台管理平台，租户管理")
        assert result == "saas"

    def test_detect_social(self):
        result = _detect_domain("社交聊天应用，朋友圈和好友系统")
        assert result == "social"

    def test_detect_dashboard(self):
        result = _detect_domain("数据大屏可视化报表系统")
        assert result == "dashboard"

    def test_detect_no_domain(self):
        result = _detect_domain("简单的待办事项管理工具")
        assert result == ""

    def test_detect_low_keyword_count(self):
        result = _detect_domain("一个银行工具")
        assert result == "banking"

    def test_detect_domains_cross_domain(self):
        result = _detect_domains("医疗电商平台，挂号和购物")
        assert "healthcare" in result
        assert "ecommerce" in result


class TestLayer1DomainTemplate:

    @pytest.mark.asyncio
    async def test_layer1_with_banking_template(self):
        domains = _detect_domains("银行转账系统，账户管理")
        items = await layer1_cross_domain_template("银行转账系统，账户管理", domains)
        assert len(items) > 0
        functional_items = [i for i in items if i.category == "functional"]
        assert len(functional_items) > 0

    @pytest.mark.asyncio
    async def test_layer1_no_domain_match(self):
        domains = _detect_domains("简单的计算器程序")
        items = await layer1_cross_domain_template("简单的计算器程序", domains)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_layer1_template_categories(self):
        domains = _detect_domains("银行金融系统")
        items = await layer1_cross_domain_template("银行金融系统", domains)
        categories = set(i.category for i in items)
        assert "functional" in categories


class TestLayer2HistoryMatch:

    @pytest.mark.asyncio
    async def test_layer2_no_history_data(self):
        from app.agent.orchestrator_requirements.layer2_semantic import layer2_semantic_match
        items = await layer2_semantic_match("银行系统")
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_check_history_not_available(self):
        assert check_history_data_available() == False


class TestLayer3LLMDeep:

    @pytest.mark.asyncio
    async def test_layer3_no_architect(self):
        from app.agent.orchestrator_requirements.layer3_dual_model import layer3_dual_model_deep
        items = await layer3_dual_model_deep("银行系统", [], [], architect=None)
        assert len(items) == 0


class TestAssociationPipeline:

    @pytest.mark.asyncio
    async def test_simple_project_skipped(self, mixin):
        result = await mixin._generate_requirement_associations("银行系统", "simple")
        assert result.skipped == True

    @pytest.mark.asyncio
    async def test_small_project_skipped(self, mixin):
        result = await mixin._generate_requirement_associations("银行系统", "small")
        assert result.skipped == True

    @pytest.mark.asyncio
    async def test_medium_project_not_skipped(self, mixin):
        result = await mixin._generate_requirement_associations("银行转账系统，账户管理", "medium")
        assert result.skipped == False
        assert len(result.items) > 0


class TestEnhancedRequirement:

    def test_build_enhanced_requirement_with_items(self, mixin):
        items = [
            AssociationItem(content="用户登录", category="functional", source="template", confidence=0.8),
            AssociationItem(content="数据加密", category="architectural", source="template", confidence=0.6),
        ]
        result = mixin._build_enhanced_requirement("银行系统", items)
        assert "银行系统" in result
        assert "需求联想增强" in result
        assert "用户登录" in result

    def test_build_enhanced_requirement_no_items(self, mixin):
        result = mixin._build_enhanced_requirement("银行系统", [])
        assert result == "银行系统"


class TestClassifyItemsForDisplay:

    def test_classify_shown_and_collapsed(self, mixin):
        items = [
            AssociationItem(content="用户登录", category="functional", source="template", confidence=0.8),
            AssociationItem(content="数据加密", category="architectural", source="template", confidence=0.6),
        ]
        result = mixin._classify_items_for_display(items)
        assert "functional" in result
        assert len(result["functional"]["shown"]) >= 1

    def test_classify_empty_items(self, mixin):
        result = mixin._classify_items_for_display([])
        assert result == {}


class TestTemplateConfidence:

    def test_high_confidence_with_many_keywords(self):
        template = {"domain": "banking"}
        confidence = compute_template_confidence("银行金融转账存款系统", template)
        assert confidence >= 0.7

    def test_low_confidence_with_few_keywords(self):
        template = {"domain": "banking"}
        confidence = compute_template_confidence("一个简单工具", template)
        assert confidence <= 0.7


class TestParseLLMResponse:

    def test_parse_valid_json(self):
        response = json.dumps({
            "functional_requirements": [{"item": "用户登录", "confidence": 0.8, "category": "core"}],
            "architectural_impacts": [],
            "risks": [],
            "key_decisions": []
        })
        items = parse_llm_response(response)
        assert len(items) >= 1
        assert items[0].content == "用户登录"

    def test_parse_text_fallback(self):
        response = "This is some text\n- 用户登录功能\n- 订单管理系统"
        items = parse_llm_response(response)
        assert len(items) >= 1

    def test_parse_json_in_text(self):
        response = "Here is the analysis:\n" + json.dumps({
            "functional_requirements": [{"item": "搜索功能", "confidence": 0.7}],
            "architectural_impacts": [],
            "risks": [],
            "key_decisions": []
        })
        items = parse_llm_response(response)
        assert len(items) >= 1

    def test_parse_empty_json(self):
        response = json.dumps({
            "functional_requirements": [],
            "architectural_impacts": [],
            "risks": [],
            "key_decisions": []
        })
        items = parse_llm_response(response)
        assert len(items) == 0