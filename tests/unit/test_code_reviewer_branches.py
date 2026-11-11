"""CodeReviewer 提示词加载、结果解析与版本兼容性分支测试。"""

import builtins
import json
import sys
import types

import pytest

import app.agent.code_reviewer as cr
from app.agent.code_reviewer import CodeReviewer


def _stub(**overrides):
    reviewer = object.__new__(CodeReviewer)
    captured = {}

    async def fake_call_llm(prompt, _system_prompt):
        captured["prompt"] = prompt
        return overrides.get("response", "{}")

    reviewer.call_llm = fake_call_llm
    reviewer._check_version_compatibility = overrides.get(
        "version_check", _async_list([])
    )
    return reviewer, captured


def _async_list(value):
    async def run(*_args, **_kwargs):
        return value

    return run


def _patch_versions(monkeypatch, versions):
    import importlib.metadata as metadata

    def fake_version(name):
        if name in versions:
            return versions[name]
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", fake_version)


class TestSystemPrompt:
    def test_custom_prompt_from_registry(self, monkeypatch):
        import app.services.skill_registry as registry

        monkeypatch.setattr(registry, "get_skill", lambda name: "custom-prompt")
        reviewer = object.__new__(CodeReviewer)

        assert reviewer.SYSTEM_PROMPT == "custom-prompt"

    def test_registry_failure_falls_back_to_loader(self, monkeypatch):
        import app.services.skill_registry as registry

        def boom(_name):
            raise RuntimeError("registry down")

        monkeypatch.setattr(registry, "get_skill", boom)
        monkeypatch.setattr(cr, "load_code_reviewer_prompt", lambda: "file-prompt")
        reviewer = object.__new__(CodeReviewer)

        assert reviewer.SYSTEM_PROMPT == "file-prompt"

    def test_missing_prompt_uses_fallback(self, monkeypatch):
        import app.services.skill_registry as registry

        monkeypatch.setattr(registry, "get_skill", lambda name: None)
        monkeypatch.setattr(cr, "load_code_reviewer_prompt", lambda: None)
        errors = []
        monkeypatch.setattr(cr.logger, "error", lambda message: errors.append(message))
        reviewer = object.__new__(CodeReviewer)

        prompt = reviewer.SYSTEM_PROMPT

        assert prompt == reviewer._fallback_prompt()
        assert errors == ["代码审查员提示词加载失败，使用兜底提示词"]

    def test_fallback_prompt_mentions_required_fields(self):
        reviewer = object.__new__(CodeReviewer)
        prompt = reviewer._fallback_prompt()

        assert "approved" in prompt
        assert "version_issues" in prompt


class TestReviewResultParsing:
    @pytest.mark.asyncio
    async def test_fenced_json_is_parsed(self):
        payload = '```json\n{"approved": true, "risk_level": "low", "issues": []}\n```'
        reviewer, _ = _stub(response=payload)

        result = await reviewer.review_code("code", "main.py")

        assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_bare_json_is_parsed(self):
        reviewer, _ = _stub(response='{"approved": false, "issues": ["x"]}')

        result = await reviewer.review_code("code", "main.py")

        assert result["issues"] == ["x"]

    @pytest.mark.asyncio
    async def test_invalid_json_requests_manual_review(self, monkeypatch):
        warnings = []
        monkeypatch.setattr(cr.logger, "warning", lambda message: warnings.append(message))
        reviewer, _ = _stub(response="not json at all")

        result = await reviewer.review_code("code", "main.py")

        assert result == {
            "approved": False,
            "risk_level": "medium",
            "issues": ["LLM 审查结果解析失败，需人工审查"],
            "suggestions": [],
            "needs_fix": True,
        }
        assert warnings and warnings[0].startswith("CodeReviewer LLM 输出非合法 JSON")

    @pytest.mark.asyncio
    async def test_non_string_response_requests_manual_review(self, monkeypatch):
        monkeypatch.setattr(cr.logger, "warning", lambda message: None)
        reviewer, _ = _stub(response=None)

        result = await reviewer.review_code("code", "main.py")

        assert result["needs_fix"] is True

    @pytest.mark.asyncio
    async def test_version_issues_are_merged(self):
        reviewer, _ = _stub(
            response=json.dumps(
                {"approved": True, "risk_level": "low", "issues": [], "needs_fix": False}
            ),
            version_check=_async_list(["v1 issue"]),
        )

        result = await reviewer.review_code("import fastapi", "main.py")

        assert result["version_issues"] == ["v1 issue"]
        assert result["issues"] == ["v1 issue"]
        assert result["risk_level"] == "medium"
        assert result["needs_fix"] is True

    @pytest.mark.asyncio
    async def test_version_issues_keep_existing_risk(self):
        reviewer, _ = _stub(
            response=json.dumps(
                {"approved": False, "risk_level": "high", "issues": ["bug"]}
            ),
            version_check=_async_list(["v1 issue"]),
        )

        result = await reviewer.review_code("import fastapi", "main.py")

        assert result["issues"] == ["bug", "v1 issue"]
        assert result["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_version_issues_fill_missing_issues_list(self):
        reviewer, _ = _stub(
            response=json.dumps({"approved": True, "risk_level": "low"}),
            version_check=_async_list(["v1 issue"]),
        )

        result = await reviewer.review_code("import fastapi", "main.py")

        assert result["issues"] == ["v1 issue"]


class TestVersionCompatibility:
    @pytest.mark.asyncio
    async def test_removed_and_changed_apis_reported(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        versions = {"fastapi": "0.100.0", "sqlalchemy": "2.0.0"}
        _patch_versions(monkeypatch, versions)

        code = (
            "from fastapi import Middleware\n"
            "OAuth2PasswordBearer(tokenUrl='x')\n"
            "from sqlalchemy import declarative_base\n"
        )
        issues = await reviewer._check_version_compatibility(code)

        assert any("Middleware" in issue and "已移除" in issue for issue in issues)
        assert any("OAuth2PasswordBearer" in issue for issue in issues)
        assert any("declarative_base" in issue for issue in issues)

    @pytest.mark.asyncio
    async def test_old_version_skips_rules(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        _patch_versions(monkeypatch, {"fastapi": "0.1.0"})

        assert await reviewer._check_version_compatibility("from fastapi import X") == []

    @pytest.mark.asyncio
    async def test_unrelated_imports_are_ignored(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        _patch_versions(monkeypatch, {"fastapi": "9.9.9"})

        assert await reviewer._check_version_compatibility("import os\nfrom x import y") == []


class TestVersionFallback:
    def test_packaging_path(self):
        reviewer = object.__new__(CodeReviewer)
        assert reviewer._version_gte("2.0.0", "1.9.9") is True
        assert reviewer._version_gte("1.0.0", "2.0.0") is False

    def test_string_fallback_when_packaging_missing(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "packaging.version":
                raise ImportError("no packaging")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        reviewer = object.__new__(CodeReviewer)

        assert reviewer._version_gte("1.10.0", "1.9.0") is True
        assert reviewer._version_gte("1.0.0", "1.1.0") is False


class TestVersionDetectionInternals:
    @pytest.mark.asyncio
    async def test_metadata_versions_are_used(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        import importlib.metadata as metadata

        def fake_version(name):
            if name == "fastapi":
                return "0.100.0"
            raise metadata.PackageNotFoundError(name)

        monkeypatch.setattr(metadata, "version", fake_version)

        issues = await reviewer._check_version_compatibility(
            "from fastapi import Middleware"
        )

        assert len(issues) == 1

    @pytest.mark.asyncio
    async def test_pkg_resources_fallback(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "importlib.metadata":
                raise ImportError("no importlib.metadata")
            return real_import(name, *args, **kwargs)

        class FakeDistribution:
            version = "0.100.0"

        fake_resources = types.SimpleNamespace(
            get_distribution=lambda name: FakeDistribution(),
            DistributionNotFound=type("DistributionNotFound", (Exception,), {}),
        )
        monkeypatch.setitem(sys.modules, "pkg_resources", fake_resources)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        issues = await reviewer._check_version_compatibility(
            "from fastapi import Middleware"
        )

        assert len(issues) == 1

    @pytest.mark.asyncio
    async def test_no_version_source_returns_empty(self, monkeypatch):
        reviewer = object.__new__(CodeReviewer)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("importlib.metadata", "pkg_resources"):
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        assert await reviewer._check_version_compatibility("from fastapi import X") == []
