"""app.utils.agent_skills 的分支覆盖测试。"""

import re

import pytest

from app.utils import agent_skills as skills
from app.utils.agent_skills import (
    AgentSkillsManager,
    AntiPatternSelfCheckSkill,
    ComparativeLearningSkill,
    KeywordDetectionSkill,
    MultiAngleReviewSkill,
    RiskSelfAssessmentSkill,
    get_skills_manager,
)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """把三个配置路径重定向到临时目录，避免依赖仓库内配置。"""
    monkeypatch.setattr(skills.settings, "KEYWORD_TRIGGERS_PATH", str(tmp_path / "kw.yaml"))
    monkeypatch.setattr(skills.settings, "REVIEW_CHECKLIST_PATH", str(tmp_path / "review.yaml"))
    monkeypatch.setattr(skills.settings, "ANTI_PATTERNS_PATH", str(tmp_path / "anti.yaml"))
    return tmp_path


def _write(path, text):
    path.write_text(text, encoding="utf-8")


class TestKeywordDetectionSkill:
    def test_loads_triggers_and_matches_case_insensitively(self, config_dir):
        _write(
            config_dir / "kw.yaml",
            "triggers:\n"
            "  - keywords: [Refactor, 重构]\n"
            "    type: refactor\n"
            "    questions: [a, b, c, d]\n",
        )
        skill = KeywordDetectionSkill()
        result = skill.detect("please REFACTOR this")

        assert result["triggered"] is True
        assert result["type"] == "refactor"
        assert result["keyword"] == "Refactor"
        assert result["questions"] == ["a", "b", "c"]
        assert result["action"] == "generate_spec"

    def test_missing_config_yields_no_triggers(self, config_dir):
        skill = KeywordDetectionSkill()
        assert skill.triggers == []
        assert skill.detect("anything") == {"skill": "keyword_detection", "triggered": False}

    def test_broken_yaml_is_swallowed_and_logged(self, config_dir):
        _write(config_dir / "kw.yaml", "triggers: [oops\n")

        skill = KeywordDetectionSkill()

        assert skill.triggers == []

    def test_non_dict_yaml_defaults_to_empty(self, config_dir):
        _write(config_dir / "kw.yaml", "- just\n- a\n- list\n")
        assert KeywordDetectionSkill().triggers == []


class TestMultiAngleReviewSkill:
    def test_review_builds_pending_entries(self, config_dir):
        _write(config_dir / "review.yaml", "checklists:\n  security: [s1]\n  performance: [p1]\n")
        skill = MultiAngleReviewSkill()

        result = skill.review("a.py", "change")

        assert result["file"] == "a.py"
        assert set(result["reviews"]) == {"security", "performance"}
        assert result["reviews"]["security"]["items"] == ["s1"]
        assert result["reviews"]["security"]["status"] == "pending_review"

    def test_missing_checklist_is_empty(self, config_dir):
        skill = MultiAngleReviewSkill()
        assert skill.review("a.py", "x")["reviews"] == {}

    def test_broken_checklist_is_swallowed(self, config_dir):
        _write(config_dir / "review.yaml", "checklists: [oops\n")
        assert MultiAngleReviewSkill().checklist == {}

    def test_review_prompt_uses_category_names_and_fallbacks(self, config_dir):
        _write(
            config_dir / "review.yaml",
            "checklists:\n  security: [s1]\n  unknown_category: [u1]\n",
        )
        prompt = MultiAngleReviewSkill().get_review_prompt("a.py", "change")

        assert "安全审查" in prompt
        assert "unknown_category" in prompt
        assert "- [ ] s1" in prompt

    def test_category_name_lookup(self, config_dir):
        skill = MultiAngleReviewSkill()
        for category, name in (
            ("compatibility", "兼容性审查"),
            ("performance", "性能审查"),
            ("testing", "测试审查"),
            ("documentation", "文档审查"),
            ("operations", "运维审查"),
        ):
            assert skill._get_category_name(category) == name
        assert skill._get_category_name("other") == "other"


class TestComparativeLearningSkill:
    def test_detects_all_supported_patterns(self):
        before = "x = 1\n"
        after = (
            "import os\n"
            "def f():\n"
            "    pass\n"
            "class C:\n"
            "    pass\n"
            "@router.get('/x')\n"
            "async def g():\n"
            "    pass\n"
        )

        result = ComparativeLearningSkill().detect_patterns(before, after)

        assert set(result["patterns_detected"]) == {
            "新增依赖",
            "新增函数",
            "新增类",
            "新增路由",
            "异步化改造",
        }
        for suggestion in (
            "requirements.txt",
            "测试用例和文档字符串",
            "测试用例和类型注解",
            "认证和参数验证",
            "I/O 操作都是异步",
        ):
            assert suggestion in result["suggestion"]

    def test_no_patterns_yields_empty_suggestion(self):
        result = ComparativeLearningSkill().detect_patterns("a\n", "a\nb\n")
        assert result["patterns_detected"] == []
        assert result["suggestion"] == ""
        assert result["lines_added"] == 1
        assert result["lines_removed"] == 0

    def test_unknown_pattern_is_ignored_by_suggestion_mapping(self):
        skill = ComparativeLearningSkill()
        assert skill._get_suggestion(["未知模式"]) == ""


class TestAntiPatternSelfCheckSkill:
    def test_reports_matches_with_defaults(self, config_dir):
        _write(
            config_dir / "anti.yaml",
            "patterns:\n"
            "  - pattern: password\n"
            "  - pattern: ''\n"
            "  - id: X\n"
            "    name: 名称\n"
            "    severity: critical\n"
            "    description: 描述\n"
            "    suggestion: 建议\n"
            "    pattern: token\n",
        )
        skill = AntiPatternSelfCheckSkill()

        findings = skill.check("password\npassword\ntoken\n")

        assert len(findings) == 2
        assert findings[0]["id"] == "unknown"
        assert findings[0]["category"] == "unknown"
        assert findings[0]["name"] == "未知模式"
        assert findings[0]["severity"] == "notice"
        assert findings[0]["match_count"] == 2
        assert findings[1]["id"] == "X"
        assert findings[1]["match_count"] == 1

    def test_empty_pattern_is_skipped(self, config_dir):
        _write(config_dir / "anti.yaml", "patterns:\n  - pattern: ''\n")
        assert AntiPatternSelfCheckSkill().check("anything") == []

    def test_pattern_without_match_is_ignored(self, config_dir):
        _write(config_dir / "anti.yaml", "patterns:\n  - pattern: 'never_matches_xyz'\n")
        assert AntiPatternSelfCheckSkill().check("nothing here") == []

    def test_invalid_regex_is_reported_as_warning(self, config_dir, monkeypatch):
        _write(config_dir / "anti.yaml", "patterns:\n  - pattern: '('\n")
        skill = AntiPatternSelfCheckSkill()
        warnings = []
        monkeypatch.setattr(
            skills.logger, "warning", lambda message: warnings.append(message)
        )

        findings = skill.check("x")

        assert findings == []
        assert warnings == ["正则表达式错误: ("]

    def test_missing_config_and_broken_config(self, config_dir):
        assert AntiPatternSelfCheckSkill().patterns == []
        _write(config_dir / "anti.yaml", "patterns: [oops\n")
        assert AntiPatternSelfCheckSkill().patterns == []

    def test_check_prompt_lists_patterns_with_fallbacks(self, config_dir):
        _write(
            config_dir / "anti.yaml",
            "patterns:\n"
            "  - pattern: a\n"
            "  - name: 命名\n"
            "    severity: warning\n"
            "    description: 描述\n"
            "    pattern: b\n",
        )
        prompt = AntiPatternSelfCheckSkill().get_check_prompt()

        assert "[NOTICE] 未知" in prompt
        assert "[WARNING] 命名" in prompt
        assert "请逐项检查" in prompt


class TestRiskSelfAssessmentSkill:
    @pytest.mark.parametrize(
        "file_path,expected_score,expected_factor",
        [
            ("app/auth/login.py", 30, "涉及认证/安全核心模块"),
            ("app/security/core.py", 30, "涉及认证/安全核心模块"),
            ("app/middleware/request_log.py", 25, "涉及中间件层"),
            ("app/models/user.py", 20, "涉及数据库模型"),
            ("app/db/session.py", 20, "涉及数据库模型"),
            ("app/api/v1/x.py", 15, "涉及 API 接口"),
            ("app/plain.py", 0, None),
        ],
    )
    def test_file_type_factors(self, file_path, expected_score, expected_factor):
        result = RiskSelfAssessmentSkill().assess(file_path, "add")

        assert result["risk_score"] == expected_score
        if expected_factor:
            assert expected_factor in result["risk_factors"]
        else:
            assert result["risk_factors"] == []

    def test_change_type_factors(self):
        assert RiskSelfAssessmentSkill().assess("plain.py", "delete")["risk_score"] == 20
        result = RiskSelfAssessmentSkill().assess("plain.py", "modify")
        assert result["risk_score"] == 10
        assert result["risk_factors"] == ["修改操作"]

    def test_dependency_factor_high(self):
        graph = {"reverse_index": {"app/auth/x.py": ["a", "b", "c", "d", "e", "f"]}}
        result = RiskSelfAssessmentSkill().assess("app/auth/x.py", "modify", graph)

        assert result["risk_score"] == 30 + 10 + 20
        assert any("被 6 个其他文件依赖" in factor for factor in result["risk_factors"])
        assert result["risk_level"] == "high"
        assert result["recommended_action"] == "需要详细审查和用户确认"

    def test_dependency_factor_low(self):
        graph = {"reverse_index": {"plain.py": ["a"]}}
        result = RiskSelfAssessmentSkill().assess("plain.py", "add", graph)

        assert result["risk_score"] == 10
        assert "被 1 个文件依赖" in result["risk_factors"]
        assert result["risk_level"] == "low"

    def test_dependency_factor_ignores_unrelated_targets(self):
        graph = {"reverse_index": {"other.py": ["a"]}}
        result = RiskSelfAssessmentSkill().assess("plain.py", "add", graph)

        assert result["risk_score"] == 0

    def test_dependency_factor_skips_when_zero(self):
        graph = {"reverse_index": {"plain.py": []}}
        result = RiskSelfAssessmentSkill().assess("plain.py", "add", graph)

        assert result["risk_score"] == 0
        assert result["risk_factors"] == []

    def test_empty_dep_graph_is_ignored(self):
        assert RiskSelfAssessmentSkill().assess("plain.py", "add", {})["risk_score"] == 0

    def test_medium_risk_level(self):
        result = RiskSelfAssessmentSkill().assess("app/api/v1/x.py", "modify", {
            "reverse_index": {"x.py": ["a"]}
        })

        assert result["risk_score"] == 15 + 10 + 10
        assert result["risk_level"] == "medium"
        assert result["recommended_action"] == "需要审查，建议运行关联测试"


class TestAgentSkillsManager:
    @pytest.fixture
    def manager(self, config_dir):
        _write(
            config_dir / "kw.yaml",
            "triggers:\n  - keywords: [重构]\n    type: refactor\n    questions: [q]\n",
        )
        _write(config_dir / "review.yaml", "checklists:\n  security: [s1]\n")
        _write(
            config_dir / "anti.yaml",
            "patterns:\n  - id: AP\n    pattern: password\n    severity: critical\n    name: 密钥\n",
        )
        return AgentSkillsManager()

    def test_get_all_skills_context(self, manager):
        context = manager.get_all_skills_context()["skills"]

        assert context["keyword_detection"]["trigger_count"] == 1
        assert context["multi_angle_review"]["checklist_categories"] == ["security"]
        assert context["anti_pattern_check"]["pattern_count"] == 1
        assert context["risk_assessment"]["levels"] == ["low", "medium", "high"]

    def test_process_user_input_records_triggered_skill(self, manager):
        result = manager.process_user_input("帮我重构这个模块")

        assert result["skills_triggered"] == ["keyword_detection"]
        assert result["keyword_detection"]["type"] == "refactor"

    def test_process_user_input_without_trigger(self, manager):
        result = manager.process_user_input("你好")

        assert result["skills_triggered"] == []
        assert "keyword_detection" not in result

    def test_pre_modify_review(self, manager):
        result = manager.pre_modify_review("app/api/v1/x.py", "调整接口")

        assert "security" in result["multi_angle_review"]["reviews"]
        assert result["risk_assessment"]["change_type"] == "modify"
        assert result["risk_assessment"]["risk_score"] == 15 + 10

    def test_post_modify_check(self, manager):
        result = manager.post_modify_check("password = 'secret'\ndef f():\n    pass\n", "a.py")

        assert result["anti_pattern_check"][0]["id"] == "AP"
        assert "新增函数" in result["comparative_learning"]["patterns_detected"]

    def test_get_skills_manager_is_singleton(self, monkeypatch, manager):
        monkeypatch.setattr(skills, "_skills_manager", None)

        first = get_skills_manager()
        second = get_skills_manager()

        assert first is second
        assert isinstance(first, AgentSkillsManager)
