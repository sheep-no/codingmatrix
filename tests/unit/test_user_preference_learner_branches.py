"""Branch coverage for app/agent/user_preference_learner.py."""

import json
from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

import app.agent.user_preference_learner as module
from app.agent.user_preference_learner import (
    ArchitecturePreference,
    CodeStylePreference,
    DocumentationPreference,
    TechStackPreference,
    UserPreferenceLearner,
    UserPreferenceProfile,
    get_user_preference_learner,
)


@pytest.fixture
def learner(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
    return UserPreferenceLearner(user_id="u1", data_dir=tmp_path)


class TestLoadPreferences:
    def test_full_profile_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        original = UserPreferenceProfile(user_id="u1")
        original.code_style = CodeStylePreference(paradigm="functional")
        original.documentation = DocumentationPreference(comment_density="verbose")
        original.architecture = ArchitecturePreference(layer_separation="relaxed")
        original.tech_stack = TechStackPreference(database="pg")
        (tmp_path / "u1.json").write_text(
            json.dumps(asdict(original), ensure_ascii=False), encoding="utf-8"
        )

        learner = UserPreferenceLearner(user_id="u1", data_dir=tmp_path)

        assert learner.profile.code_style.paradigm == "functional"
        assert learner.profile.documentation.comment_density == "verbose"
        assert learner.profile.architecture.layer_separation == "relaxed"
        assert learner.profile.tech_stack.database == "pg"

    def test_partial_profile_skips_missing_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        (tmp_path / "u1.json").write_text(json.dumps({"user_id": "u1"}), encoding="utf-8")

        learner = UserPreferenceLearner(user_id="u1", data_dir=tmp_path)

        assert learner.profile.user_id == "u1"
        assert learner.profile.code_style.paradigm == "mixed"

    def test_invalid_profile_logs_error(self, tmp_path, monkeypatch):
        (tmp_path / "u1.json").write_text("not-json", encoding="utf-8")
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        UserPreferenceLearner(user_id="u1", data_dir=tmp_path)

        assert fake_logger.error.called


class TestSavePreferences:
    def test_save_writes_file(self, learner):
        learner._save_preferences()

        data = json.loads((learner.data_dir / "u1.json").read_text(encoding="utf-8"))
        assert data["user_id"] == "u1"
        assert learner.profile.updated_at

    def test_save_failure_logs_error(self, learner, monkeypatch):
        (learner.data_dir / "u1.json").mkdir()
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        learner._save_preferences()

        assert fake_logger.error.called


class TestRecordModification:
    def test_records_history_and_persists(self, learner):
        learner.record_modification(
            "a.py", "python", "def a():\n    pass", "def a():\n    return 1"
        )

        assert learner.profile.total_modifications == 1
        assert learner._modification_history[0]["file_path"] == "a.py"
        assert learner._modification_history[0]["modification_type"] == "unknown"
        assert (learner.data_dir / "u1.json").exists()

    def test_explicit_modification_type(self, learner):
        learner.record_modification(
            "a.py", "python", "x", "y", modification_type="refactor"
        )
        assert learner._modification_history[0]["modification_type"] == "refactor"

    def test_history_is_trimmed_to_1000(self, learner):
        learner._modification_history = [{"i": i} for i in range(1000)]

        learner.record_modification("a.py", "python", "x", "y")

        assert len(learner._modification_history) == 1000
        assert learner._modification_history[-1]["file_path"] == "a.py"


class TestAnalysis:
    def test_naming_toward_snake_case(self, learner):
        result = learner._analyze_naming_changes(
            {"user_name = 1"}, {"userName = 1"}
        )
        assert result == {"trend": "toward_snake_case", "confidence": 0.7}

    def test_naming_toward_camel_case(self, learner):
        result = learner._analyze_naming_changes(
            {"userName = 1"}, {"user_name = 1"}
        )
        assert result == {"trend": "toward_camel_case", "confidence": 0.7}

    def test_naming_no_change_returns_none(self, learner):
        assert learner._analyze_naming_changes({"x = 1"}, {"y = 2"}) is None

    def test_comment_changes_more(self, learner):
        original = "x = 1"
        modified = "\n".join(["# c"] * 6)
        assert learner._analyze_comment_changes(original, modified) == {
            "trend": "more_comments",
            "diff": 6,
        }

    def test_comment_changes_fewer(self, learner):
        original = "\n".join(["# c"] * 6)
        modified = "x = 1"
        assert learner._analyze_comment_changes(original, modified) == {
            "trend": "fewer_comments",
            "diff": -6,
        }

    def test_comment_changes_within_threshold(self, learner):
        assert learner._analyze_comment_changes("# a", "# b") is None

    def test_structure_more_functions(self, learner):
        original = "def a():\n    pass"
        modified = "def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\ndef d():\n    pass"
        assert learner._analyze_structure_changes(original, modified) == {
            "trend": "more_functions",
            "confidence": 0.6,
        }

    def test_structure_more_classes(self, learner):
        original = "def a():\n    pass"
        modified = "def a():\n    pass\nclass B:\n    pass"
        assert learner._analyze_structure_changes(original, modified) == {
            "trend": "more_classes",
            "confidence": 0.6,
        }

    def test_structure_unchanged(self, learner):
        assert learner._analyze_structure_changes("def a():\n    pass", "x = 1") is None

    def test_tech_added_framework(self, learner):
        assert learner._analyze_tech_changes("x = 1", "from flask import Flask") == {
            "added_flask": True
        }

    def test_tech_removed_framework(self, learner):
        assert learner._analyze_tech_changes("from flask import Flask", "x = 1") == {
            "removed_flask": True
        }

    def test_tech_unchanged(self, learner):
        assert learner._analyze_tech_changes("from flask import Flask", "import flask") is None

    def test_analyze_modification_collects_all_changes(self, learner):
        original = "from flask import Flask\n# one"
        modified = (
            "from fastapi import FastAPI\n"
            + "\n".join(["# comment"] * 8)
            + "\ndef a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\ndef d():\n    pass"
        )

        analysis = learner._analyze_modification(original, modified, "python")

        types = {c["type"] for c in analysis["changes"]}
        assert {"documentation", "structure", "technology"} <= types
        assert analysis["file_type"] == "python"

    def test_analyze_modification_no_changes(self, learner):
        analysis = learner._analyze_modification("x = 1", "x = 1", "python")
        assert analysis["changes"] == []

    def test_analyze_modification_detects_naming_change(self, learner):
        analysis = learner._analyze_modification(
            "def f():\n    userName = 1", "def f():\n    user_name = 1", "python"
        )
        assert analysis["changes"][0]["type"] == "naming_convention"
        assert analysis["changes"][0]["details"]["trend"] == "toward_snake_case"


class TestUpdatePreferences:
    def test_naming_preferences(self, learner):
        learner._update_preferences(
            {"changes": [{"type": "naming_convention", "details": {"trend": "toward_snake_case"}}]}
        )
        assert learner.profile.code_style.naming_convention == "snake_case"
        assert learner.profile.confidence_scores["naming_convention"] == pytest.approx(0.6)

        learner._update_preferences(
            {"changes": [{"type": "naming_convention", "details": {"trend": "toward_camel_case"}}]}
        )
        assert learner.profile.code_style.naming_convention == "camelCase"
        assert learner.profile.confidence_scores["naming_convention"] == pytest.approx(0.7)

    def test_naming_unknown_trend_is_ignored(self, learner):
        learner._update_preferences(
            {"changes": [{"type": "naming_convention", "details": {"trend": "other"}}]}
        )
        assert learner.profile.code_style.naming_convention == "snake_case"

    def test_documentation_preferences(self, learner):
        learner._update_preferences(
            {"changes": [{"type": "documentation", "details": {"diff": 11}}]}
        )
        assert learner.profile.documentation.comment_density == "verbose"

        learner._update_preferences(
            {"changes": [{"type": "documentation", "details": {"diff": 3}}]}
        )
        assert learner.profile.documentation.comment_density == "moderate"

        learner._update_preferences(
            {"changes": [{"type": "documentation", "details": {"diff": -11}}]}
        )
        assert learner.profile.documentation.comment_density == "minimal"

    def test_documentation_small_negative_is_ignored(self, learner):
        learner.profile.documentation.comment_density = "verbose"
        learner._update_preferences(
            {"changes": [{"type": "documentation", "details": {"diff": -3}}]}
        )
        assert learner.profile.documentation.comment_density == "verbose"

    def test_structure_preferences(self, learner):
        learner._update_preferences(
            {"changes": [{"type": "structure", "details": {"trend": "more_functions"}}]}
        )
        assert learner.profile.code_style.paradigm == "functional"

        learner._update_preferences(
            {"changes": [{"type": "structure", "details": {"trend": "more_classes"}}]}
        )
        assert learner.profile.code_style.paradigm == "object_oriented"

    def test_structure_unknown_trend_is_ignored(self, learner):
        learner._update_preferences(
            {"changes": [{"type": "structure", "details": {"trend": "other"}}]}
        )
        assert learner.profile.code_style.paradigm == "mixed"

    def test_technology_added_only(self, learner):
        learner._update_preferences(
            {
                "changes": [
                    {
                        "type": "technology",
                        "details": {"added_fastapi": True, "removed_flask": True},
                    }
                ]
            }
        )
        assert learner.profile.tech_stack.frameworks == {"web_backend": "fastapi"}

    def test_unknown_change_type_is_ignored(self, learner):
        learner._update_preferences({"changes": [{"type": "other", "details": {}}]})
        assert learner.profile.total_modifications == 0

    def test_update_confidence_clamps_at_one(self, learner):
        learner.profile.confidence_scores["x"] = 0.95
        learner._update_confidence("x", 0.5)
        assert learner.profile.confidence_scores["x"] == 1.0
        assert learner.profile.preference_strength["x"] == 1.0

    def test_update_confidence_defaults_to_half(self, learner):
        learner._update_confidence("fresh", 0.1)
        assert learner.profile.confidence_scores["fresh"] == pytest.approx(0.6)


class TestFrameworkCategory:
    @pytest.mark.parametrize(
        ("framework", "expected"),
        [
            ("flask", "web_backend"),
            ("vue", "web_frontend"),
            ("prisma", "orm"),
            ("unknownlib", "other"),
        ],
    )
    def test_category(self, learner, framework, expected):
        assert learner._infer_framework_category(framework) == expected


class TestPreferencePrompt:
    def test_default_profile_prompt(self, learner):
        prompt = learner.get_preference_prompt()
        assert "## 用户偏好" in prompt
        assert "下划线命名" in prompt
        assert "类型注解：使用类型注解" in prompt
        assert "严格分层" in prompt
        assert "detail" not in prompt

    def test_alternative_profile_prompt(self, learner):
        learner.profile.code_style.paradigm = "functional"
        learner.profile.code_style.naming_convention = "camelCase"
        learner.profile.documentation.comment_density = "verbose"
        learner.profile.documentation.type_annotations = False
        learner.profile.architecture.layer_separation = "relaxed"
        learner.profile.tech_stack.frameworks = {"web_backend": "fastapi"}
        learner.profile.confidence_scores = {"naming": 0.8, "tech": 0.9, "low": 0.2}

        prompt = learner.get_preference_prompt()

        assert "函数式" in prompt
        assert "驼峰命名" in prompt
        assert "详细注释" in prompt
        assert "不使用类型注解" in prompt
        assert "灵活分层" in prompt
        assert "web_backend: fastapi" in prompt
        assert "2 个高置信度" in prompt

    def test_moderate_architecture_skips_line(self, learner):
        learner.profile.architecture.layer_separation = "moderate"
        assert "架构风格" not in learner.get_preference_prompt()

    def test_mixed_naming_skips_line(self, learner):
        learner.profile.code_style.naming_convention = "mixed"
        assert "命名风格" not in learner.get_preference_prompt()


class TestStats:
    def test_learning_stats(self, learner):
        learner.profile.total_modifications = 4
        learner.profile.confidence_scores = {"a": 0.9, "b": 0.5}
        learner.profile.tech_stack.frameworks = {"web_backend": "fastapi"}

        stats = learner.get_learning_stats()

        assert stats["total_modifications"] == 4
        assert stats["preference_items"] == 2
        assert stats["high_confidence_preferences"] == 1
        assert stats["tech_stack"] == {"web_backend": "fastapi"}
        assert stats["code_style"]["paradigm"] == "mixed"
        assert stats["documentation"]["comment_density"] == "moderate"


class TestSingleton:
    async def test_returns_cached_instance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        module._user_preference_learners.clear()

        first = await get_user_preference_learner("u1")
        second = await get_user_preference_learner("u1")

        assert first is second
        assert module._user_preference_learners["u1"] is first
        module._user_preference_learners.clear()

    async def test_inner_double_check_returns_existing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        module._user_preference_learners.clear()
        existing = UserPreferenceLearner(user_id="u1", data_dir=tmp_path)

        class RaceLock:
            async def __aenter__(self):
                module._user_preference_learners["u1"] = existing
                return self

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(module, "_learner_lock", RaceLock())

        result = await get_user_preference_learner("u1")

        assert result is existing
        module._user_preference_learners.clear()

    async def test_inner_check_sees_race_winner(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        existing = UserPreferenceLearner(user_id="u1", data_dir=tmp_path)

        class RacingDict(dict):
            """First containment probe misses, the double-check then sees the winner."""

            def __contains__(self, key):
                if key in self.keys():
                    return True
                self[key] = existing
                return False

        racing = RacingDict()
        monkeypatch.setattr(module, "_user_preference_learners", racing)

        result = await get_user_preference_learner("u1")

        assert result is existing
        module._user_preference_learners.clear()

    async def test_separate_users_get_separate_instances(self, tmp_path, monkeypatch):
        monkeypatch.setattr(module, "PREFERENCE_DATA_DIR", tmp_path)
        module._user_preference_learners.clear()

        first = await get_user_preference_learner("u1")
        second = await get_user_preference_learner("u2")

        assert first is not second
        assert first.user_id == "u1"
        assert second.user_id == "u2"
        module._user_preference_learners.clear()
