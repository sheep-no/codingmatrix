"""补齐 profile_discovery 的框架发现、探测计划与缓存边界。"""

import json

import pytest

from app.agent.evaluation_matrix import ApplicationDomain
from app.agent.framework_profiles import ProfileStatus
from app.agent.profile_discovery import (
    CapabilityGap,
    DiscoveredProfile,
    ProfileCache,
    ProfileProbeResult,
    _discover_database,
    build_probe_plan,
    discover_profile,
)


def _workspace(tmp_path, name="ws"):
    path = tmp_path / name
    path.mkdir()
    return path


class TestPackageJsonFrameworks:
    def test_electron(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "package.json").write_text(
            json.dumps({"dependencies": {"electron": "1.0"}}), encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.domain is ApplicationDomain.WINDOWS
        assert profile.framework == "electron"
        assert "desktop_window" in profile.capabilities

    def test_react_native_with_scoped_dependency(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "package.json").write_text(
            json.dumps({"dependencies": {"@react-native/core": "1.0"}}),
            encoding="utf-8",
        )

        profile = discover_profile(ws)

        assert profile.domain is ApplicationDomain.ANDROID
        assert profile.framework == "react-native"

    def test_express(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "package.json").write_text(
            json.dumps({"dependencies": {"express": "4"}}), encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.framework == "express"

    def test_unrecognized_framework_records_gap(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "package.json").write_text(
            json.dumps({"dependencies": {"lodash": "4"}}), encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.gaps[0].capability == "framework"


class TestPythonManifestFrameworks:
    @pytest.mark.parametrize(
        ("manifest", "framework", "domain"),
        [
            ("django", "django", ApplicationDomain.WEB),
            ("fastapi", "fastapi", ApplicationDomain.WEB),
            ("flask", "flask", ApplicationDomain.WEB),
        ],
    )
    def test_web_frameworks(self, tmp_path, manifest, framework, domain):
        ws = _workspace(tmp_path)
        (ws / "requirements.txt").write_text(manifest, encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.framework == framework
        assert profile.domain is domain

    def test_project_scripts_is_cli(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "pyproject.toml").write_text(
            "[project.scripts]\ndemo = 'demo:main'\n", encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.framework == "stdlib-cli"
        assert profile.domain is ApplicationDomain.CLI


class TestGoRustJavaFrameworks:
    def test_echo(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "go.mod").write_text(
            "require github.com/labstack/echo/v4 v4.0.0", encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.framework == "echo"

    def test_go_stdlib(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "go.mod").write_text("module demo\n", encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.framework == "stdlib"
        assert profile.domain is ApplicationDomain.CLI

    def test_actix_web(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "Cargo.toml").write_text('[dependencies]\nactix-web = "4"\n', encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.framework == "actix-web"

    def test_rust_cli(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "Cargo.toml").write_text("[package]\nname = 'demo'\n", encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.framework == "rust-cli"
        assert profile.domain is ApplicationDomain.CLI

    def test_java_pom_without_spring_records_gap(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "pom.xml").write_text("<project/>", encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.language == "java"
        assert profile.gaps[0].capability == "framework"

    def test_java_pom_spring_boot(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "pom.xml").write_text(
            "<dependency>spring-boot-starter-web</dependency>", encoding="utf-8"
        )

        profile = discover_profile(ws)

        assert profile.domain is ApplicationDomain.WEB
        assert profile.framework == "spring-boot"

    def test_gradle_kts_android_fallback(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "build.gradle.kts").write_text("plugins { kotlin('jvm') }", encoding="utf-8")

        profile = discover_profile(ws)

        assert profile.language == "kotlin"
        assert profile.domain is ApplicationDomain.ANDROID


class TestBuildProbePlan:
    def _profile(self, **kwargs):
        defaults = dict(
            language="unknown",
            framework="unknown",
            domain=ApplicationDomain.CLI,
            evidence=(),
            capabilities=(),
        )
        defaults.update(kwargs)
        return DiscoveredProfile(**defaults)

    def test_javascript_build_step(self, tmp_path):
        ws = _workspace(tmp_path)
        (ws / "package.json").write_text(
            json.dumps({"dependencies": {"lodash": "4"}}), encoding="utf-8"
        )
        profile = discover_profile(ws)

        steps = build_probe_plan(profile)

        assert steps[0].command == ("npm", "run", "build")

    def test_game_domain_appends_event_loop(self):
        steps = build_probe_plan(self._profile(domain=ApplicationDomain.GAME))

        assert [step.name for step in steps] == ["syntax", "event_loop"]

    def test_scraper_domain_appends_scraper_tests(self):
        steps = build_probe_plan(self._profile(domain=ApplicationDomain.SCRAPER))

        assert steps[-1].name == "scraper_tests"

    def test_default_domain_appends_tests(self):
        steps = build_probe_plan(self._profile(domain=ApplicationDomain.CLI))

        assert steps[-1].command == ("python3", "-m", "pytest")

    def test_unknown_validation_step_raises(self, tmp_path, monkeypatch):
        from app.agent import framework_profiles

        class _Builtin:
            validation_steps = ("nonsense",)

            def command_for_stage(self, stage):
                return ("true",)

        class _Registry(dict):
            def get(self, language, framework=None):
                return _Builtin()

        monkeypatch.setattr(framework_profiles, "DEFAULT_PROFILES", _Registry())

        with pytest.raises(ValueError, match="unsupported profile validation step"):
            build_probe_plan(self._profile(language="python", framework="fastapi"))

    def test_builtin_without_commands_falls_back(self, monkeypatch):
        from app.agent import framework_profiles

        class _Builtin:
            validation_steps = ("build",)

            def command_for_stage(self, stage):
                return None

        class _Registry(dict):
            def get(self, language, framework=None):
                return _Builtin()

        monkeypatch.setattr(framework_profiles, "DEFAULT_PROFILES", _Registry())

        steps = build_probe_plan(self._profile(language="python", framework="fastapi"))

        assert steps[0].name == "syntax"


class TestProfileCacheBoundaries:
    def test_promote_requires_experimental_status(self, tmp_path):
        cache = ProfileCache(tmp_path)
        profile = DiscoveredProfile(
            language="python",
            framework="fastapi",
            domain=ApplicationDomain.WEB,
            evidence=(),
            capabilities=(),
            status="custom_pending",
        )

        with pytest.raises(ValueError, match="passing experimental probe"):
            cache.promote_supported(
                profile, required_checks=("build",), checks=("build",)
            )

    def test_promote_requires_all_checks(self, tmp_path):
        cache = ProfileCache(tmp_path)
        profile = DiscoveredProfile(
            language="python",
            framework="fastapi",
            domain=ApplicationDomain.WEB,
            evidence=(),
            capabilities=(),
            status="experimental",
        )

        with pytest.raises(ValueError):
            cache.promote_supported(
                profile, required_checks=("build", "test"), checks=("build",)
            )

    def test_record_probe_failure_keeps_pending(self, tmp_path):
        cache = ProfileCache(tmp_path)
        profile = DiscoveredProfile(
            language="python",
            framework="fastapi",
            domain=ApplicationDomain.WEB,
            evidence=(),
            capabilities=(),
        )
        result = ProfileProbeResult(
            profile=profile, passed=False, checks=(), failures=("boom",)
        )

        updated = cache.record_probe(result)

        assert updated.status == "custom_pending"
        assert updated.gaps[0].capability == "probe"

    def test_missing_entry_returns_none(self, tmp_path):
        assert ProfileCache(tmp_path).get("python", "fastapi") is None


class TestDatabaseDiscovery:
    def _profile(self):
        return DiscoveredProfile(
            language="python",
            framework="fastapi",
            domain=ApplicationDomain.CLI,
            evidence=(),
            capabilities=(),
        )

    def test_postgres_tokens(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("psycopg2\n", encoding="utf-8")

        assert _discover_database(tmp_path, self._profile()) == "postgresql"

    def test_postgresql_word(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("postgresql\n", encoding="utf-8")

        assert _discover_database(tmp_path, self._profile()) == "postgresql"

    def test_mysql_tokens(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pymysql\n", encoding="utf-8")

        assert _discover_database(tmp_path, self._profile()) == "mysql"

    def test_web_defaults_to_sqlite(self, tmp_path):
        profile = DiscoveredProfile(
            language="python",
            framework="fastapi",
            domain=ApplicationDomain.WEB,
            evidence=(),
            capabilities=(),
        )

        assert _discover_database(tmp_path, profile) == "sqlite"

    def test_unknown(self, tmp_path):
        assert _discover_database(tmp_path, self._profile()) == "unknown"
