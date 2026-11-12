"""Branch coverage for app/agent/critical_decision.py."""

from types import SimpleNamespace

import pytest

from app.agent.critical_decision import (
    CriticalDecisionExtractor,
    _complexity_flag,
    _complexity_int,
    _tech_stack_text,
    should_skip_user_decision,
)


def _complexity(**overrides):
    values = {
        "has_frontend": False,
        "has_backend": False,
        "has_database": False,
        "has_auth": False,
        "estimated_files": 0,
    }
    values.update(overrides)
    return values


class TestUncertaintyAnalysis:
    def test_all_signals_undecided(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {"tech_stack": [], "project_spec": {"default": {}}},
            _complexity(
                has_frontend=True,
                has_backend=True,
                has_database=True,
                has_auth=True,
                estimated_files=30,
            ),
        )
        ids = [d.id for d in decisions]
        assert ids == ["auth_strategy", "database_choice", "frontend_framework"]

    def test_dict_tech_stack_decisions_suppress(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {
                "tech_stack": {
                    "frontend_framework": "React",
                    "api_style": "graphql",
                    "architecture_pattern": "microservice",
                    "db": "sqlite",
                },
                "project_spec": {"default": {}},
            },
            _complexity(
                has_frontend=True,
                has_backend=True,
                has_database=True,
                has_auth=False,
                estimated_files=30,
            ),
        )
        ids = [d.id for d in decisions]
        assert "frontend_framework" not in ids
        assert "api_style" not in ids
        assert "architecture_pattern" not in ids
        assert "database_choice" not in ids

    def test_non_dict_project_spec_is_ignored(self):
        extractor = CriticalDecisionExtractor()
        extractor.extract_from_architecture(
            {"tech_stack": [], "project_spec": "plain text"},
            _complexity(has_auth=True),
        )
        assert [d.id for d in extractor.decisions] == ["auth_strategy"]

    def test_project_spec_without_default(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {"tech_stack": [], "project_spec": {"auth": {"scheme": "jwt"}}},
            _complexity(has_auth=True),
        )
        assert [d.id for d in decisions] == []

    def test_architecture_pattern_requested_over_20_files(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {"tech_stack": [], "project_spec": {}},
            _complexity(estimated_files=21),
        )
        assert [d.id for d in decisions] == ["architecture_pattern"]

    def test_storage_persistent_suppresses_db_question(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {
                "tech_stack": [],
                "project_spec": {"default": {"storage": {"type": "postgres"}}},
            },
            _complexity(has_database=True),
        )
        assert "database_choice" not in [d.id for d in decisions]

    def test_memory_storage_still_asks(self):
        extractor = CriticalDecisionExtractor()
        decisions = extractor.extract_from_architecture(
            {
                "tech_stack": [],
                "project_spec": {"default": {"storage": {"type": "memory"}}},
            },
            _complexity(has_database=True),
        )
        assert "database_choice" in [d.id for d in decisions]

    def test_unknown_decision_template_skipped(self):
        extractor = CriticalDecisionExtractor()

        class _Extractor(CriticalDecisionExtractor):
            def _analyze_uncertainty(self, architecture, complexity_analysis):
                return ["not_a_real_decision"]

        custom = _Extractor()
        assert custom.extract_from_architecture({}, None) == []


class TestImpactFiles:
    def test_dict_and_string_file_plan(self):
        extractor = CriticalDecisionExtractor()
        impact = extractor._identify_impact_files(
            "auth_strategy",
            {
                "file_plan": [
                    {"path": "app/auth/service.py"},
                    "app/config.py",
                    {"path": "README.md"},
                    None,
                    {"path": None},
                ]
            },
        )
        assert impact == ["app/auth/service.py", "app/config.py"]

    def test_unknown_decision_has_no_keywords(self):
        extractor = CriticalDecisionExtractor()
        assert extractor._identify_impact_files("unknown", {"file_plan": ["auth.py"]}) == []


class TestQuestionFlow:
    def _extractor_with_decisions(self):
        extractor = CriticalDecisionExtractor()
        extractor.extract_from_architecture(
            {"tech_stack": [], "project_spec": {}},
            _complexity(has_auth=True, has_backend=True),
        )
        return extractor

    def test_format_questions(self):
        extractor = self._extractor_with_decisions()
        questions = extractor.format_as_questions()
        assert questions[0]["id"] == extractor.decisions[0].id
        assert "options" in questions[0]

    def test_apply_user_choice_known(self):
        extractor = self._extractor_with_decisions()
        decision_id = extractor.decisions[0].id
        result = extractor.apply_user_choice(decision_id, "JWT")
        assert result["applied"] is True
        assert result["impact_files"] == extractor.decisions[0].impact_files
        assert extractor.decisions[0].selected == "JWT"

    def test_apply_user_choice_unknown(self):
        extractor = self._extractor_with_decisions()
        result = extractor.apply_user_choice("missing", "x")
        assert result["impact_files"] == []
        assert extractor.get_all_choices()["missing"] == "x"

    def test_get_impact_files_known_and_unknown(self):
        extractor = self._extractor_with_decisions()
        decision_id = extractor.decisions[0].id
        assert extractor._get_impact_files(decision_id) == extractor.decisions[0].impact_files
        assert extractor._get_impact_files("missing") == []

    def test_context_empty_when_no_choices(self):
        assert CriticalDecisionExtractor().get_decision_context_for_prompt() == ""

    def test_context_with_known_choice(self):
        extractor = self._extractor_with_decisions()
        decision_id = extractor.decisions[0].id
        extractor.apply_user_choice(decision_id, "JWT")
        context = extractor.get_decision_context_for_prompt()
        assert "用户架构决策" in context
        assert "JWT" in context

    def test_context_with_unknown_template(self):
        extractor = CriticalDecisionExtractor()
        extractor.user_choices["ghost"] = "x"
        assert extractor.get_decision_context_for_prompt() == ""

    def test_context_with_known_template_unknown_choice(self):
        extractor = self._extractor_with_decisions()
        decision_id = extractor.decisions[0].id
        extractor.apply_user_choice(decision_id, "NotAnOption")
        context = extractor.get_decision_context_for_prompt()
        assert "NotAnOption ()" in context

    def test_skip_remaining_decisions(self):
        extractor = self._extractor_with_decisions()
        first = extractor.decisions[0].id
        extractor.apply_user_choice(first, "JWT")
        extractor.skip_remaining_decisions()

        assert all(d.selected is not None for d in extractor.decisions)
        assert extractor.user_choices[first] == "JWT"
        for decision in extractor.decisions[1:]:
            assert extractor.user_choices[decision.id] == decision.default


class TestShouldSkip:
    def test_no_questions(self):
        assert should_skip_user_decision({}, None) is True
        assert should_skip_user_decision({}, []) is True

    def test_level_enum_value(self):
        complexity = SimpleNamespace(level=SimpleNamespace(value="simple"))
        assert should_skip_user_decision(complexity, [{"id": "x"}]) is True

    def test_level_object_attribute(self):
        complexity = SimpleNamespace(level="medium", has_backend=True, estimated_files=10)
        assert should_skip_user_decision(complexity, [{"id": "x"}]) is False

    def test_none_complexity_with_questions(self):
        assert should_skip_user_decision(None, [{"id": "x"}]) is True

    def test_only_estimated_small(self):
        assert (
            should_skip_user_decision(
                {"level": "medium", "estimated_files": 4}, [{"id": "x"}]
            )
            is True
        )


class TestHelperFunctions:
    def test_flag_none(self):
        assert _complexity_flag(None, "has_auth") is False

    def test_flag_dict(self):
        assert _complexity_flag({"has_auth": 1}, "has_auth") is True

    def test_flag_object(self):
        assert _complexity_flag(SimpleNamespace(has_auth=True), "has_auth") is True

    def test_flag_object_missing(self):
        assert _complexity_flag(SimpleNamespace(), "has_auth") is False

    def test_int_none_returns_default(self):
        assert _complexity_int(None, "estimated_files", 7) == 7

    def test_int_dict(self):
        assert _complexity_int({"estimated_files": "12"}, "estimated_files") == 12

    def test_int_object(self):
        assert _complexity_int(SimpleNamespace(estimated_files=5), "estimated_files") == 5

    def test_int_invalid_returns_default(self):
        assert _complexity_int({"estimated_files": "abc"}, "estimated_files", 3) == 3

    def test_int_none_value_returns_default(self):
        assert _complexity_int({"estimated_files": None}, "estimated_files", 4) == 4

    def test_tech_stack_list(self):
        assert _tech_stack_text(["JWT", "SQLite"]) == "jwt sqlite"

    def test_tech_stack_dict(self):
        assert _tech_stack_text({"a": "JWT", "b": "REST"}) == "jwt rest"

    def test_tech_stack_string(self):
        assert _tech_stack_text("FastAPI") == "fastapi"

    def test_tech_stack_none(self):
        assert _tech_stack_text(None) == ""
