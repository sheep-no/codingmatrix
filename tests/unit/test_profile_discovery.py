import json

from app.agent.evaluation_matrix import ApplicationDomain
from app.agent.framework_profiles import ProfileStatus
from app.agent.profile_discovery import ProfileCache, build_probe_plan, discover_or_load_profile, discover_profile, probe_profile, profile_context


def test_discovery_identifies_pygame_game_workspace(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")

    profile = discover_profile(tmp_path)

    assert profile.language == "python"
    assert profile.framework == "pygame"
    assert profile.domain is ApplicationDomain.GAME
    assert profile.status == ProfileStatus.EXPERIMENTAL.value
    assert "2d_rendering" in profile.capabilities
    assert probe_profile(profile, checks=("syntax", "startup")).passed
    assert all(step.command and step.action.value for step in build_probe_plan(profile))


def test_discovery_identifies_scrapy_and_reports_unknown_framework(tmp_path):
    (tmp_path / "requirements.txt").write_text("scrapy\n", encoding="utf-8")
    profile = discover_profile(tmp_path)
    assert profile.domain is ApplicationDomain.SCRAPER

    unknown_workspace = tmp_path / "unknown"
    unknown_workspace.mkdir()
    unknown = unknown_workspace / "pyproject.toml"
    unknown.write_text("custom_runtime\n", encoding="utf-8")
    unknown_profile = discover_profile(unknown_workspace)
    assert unknown_profile.gaps[0].capability == "framework"


def test_discovery_marks_empty_workspace_as_unresolved(tmp_path):
    profile = discover_profile(tmp_path)

    result = probe_profile(profile, checks=("syntax",))

    assert result.passed is False
    assert result.failures


def test_probe_plan_uses_android_build_contract(tmp_path):
    (tmp_path / "settings.gradle").write_text("rootProject.name='demo'\n", encoding="utf-8")

    profile = discover_profile(tmp_path)
    steps = build_probe_plan(profile)

    assert steps[0].command == ("./gradlew", "assembleDebug")
    assert all("&&" not in part for step in steps for part in step.command)


def test_profile_cache_round_trips_workspace_profile(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")
    profile = discover_profile(tmp_path)
    cache = ProfileCache(tmp_path)

    cache.put(profile)
    loaded = cache.get("python", "pygame")

    assert loaded == profile
    assert (tmp_path / ".monkeycode" / "profiles.json").exists()


def test_discovery_reuses_cached_profile(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")
    cache = ProfileCache(tmp_path)
    cached = discover_profile(tmp_path)
    cache.put(cached.__class__(
        language=cached.language, framework=cached.framework, domain=cached.domain,
        evidence=cached.evidence, capabilities=cached.capabilities, status="experimental",
    ))

    assert discover_or_load_profile(tmp_path).status == "experimental"


def test_profile_cache_invalidates_previous_schema_version(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    metadata_dir = tmp_path / ".monkeycode"
    metadata_dir.mkdir()
    (metadata_dir / "profiles.json").write_text(json.dumps({
        "schema_version": 1,
        "profiles": {
            "python:fastapi": {
                "language": "python",
                "framework": "fastapi",
                "domain": "web",
                "status": "custom_pending",
            }
        },
    }), encoding="utf-8")

    assert discover_or_load_profile(tmp_path).status == ProfileStatus.SUPPORTED.value


def test_probe_result_drives_profile_status_and_promotion(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")
    cache = ProfileCache(tmp_path)
    profile = discover_profile(tmp_path)

    experimental = cache.record_probe(probe_profile(profile, checks=("syntax", "startup")))
    supported = cache.promote_supported(
        experimental, required_checks=("syntax", "startup", "crud", "persistence"),
        checks=("syntax", "startup", "crud", "persistence"),
    )

    assert supported.status == "supported"
    assert cache.get("python", "pygame").status == "supported"


def test_profile_context_is_serializable_for_generation(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")

    context = profile_context(tmp_path)

    assert context["domain"] == "game"
    assert context["framework"] == "pygame"
    assert isinstance(context["capabilities"], list)
    assert context["capability_policy"]["ready"]
    assert "renderer" in context["capability_policy"]["required_components"]
    assert any(item["path"] == "game/renderer.py" for item in context["capability_policy"]["component_file_plan"])


def test_profile_context_includes_database_contract_and_defaults_web_to_sqlite(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\nsqlalchemy\n", encoding="utf-8")

    context = profile_context(tmp_path)

    assert context["database"]["name"] == "sqlite"
    assert context["database"]["status"] == "supported"
    assert "restart_persistence" in context["database"]["capabilities"]


def test_profile_context_marks_unknown_database_unsupported(tmp_path):
    (tmp_path / "pyproject.toml").write_text("custom_db_driver = true\n", encoding="utf-8")

    context = profile_context(tmp_path)

    assert context["database"]["status"] == "unsupported"
    assert context["database"]["test_database"] == "unsupported"


def test_discovery_identifies_high_frequency_web_profiles(tmp_path):
    cases = (
        ("next", "nextjs"),
        ("react_vite", "react-vite"),
        ("nestjs", "nestjs"),
    )
    dependencies = {
        "next": {"next": "latest", "react": "latest"},
        "react_vite": {"react": "latest", "vite": "latest"},
        "nestjs": {"@nestjs/core": "latest"},
    }
    for directory, expected in cases:
        workspace = tmp_path / directory
        workspace.mkdir()
        (workspace / "package.json").write_text(
            json.dumps({"dependencies": dependencies[directory]}), encoding="utf-8"
        )
        profile = discover_profile(workspace)
        assert profile.framework == expected
        assert profile.status == ProfileStatus.SUPPORTED.value


def test_discovery_identifies_go_and_rust_profiles(tmp_path):
    gin_workspace = tmp_path / "gin"
    gin_workspace.mkdir()
    (gin_workspace / "go.mod").write_text(
        "module demo\nrequire github.com/gin-gonic/gin v1.10.0\n", encoding="utf-8"
    )
    axum_workspace = tmp_path / "axum"
    axum_workspace.mkdir()
    (axum_workspace / "Cargo.toml").write_text(
        '[dependencies]\naxum = "0.8"\n', encoding="utf-8"
    )

    assert discover_profile(gin_workspace).framework == "gin"
    assert discover_profile(axum_workspace).framework == "axum"
    assert build_probe_plan(discover_profile(gin_workspace))[0].command == (
        "go", "vet", "./..."
    )


def test_discovery_identifies_spring_gradle_profile(tmp_path):
    (tmp_path / "build.gradle").write_text(
        "plugins { id 'org.springframework.boot' version '3.3.0' }\n", encoding="utf-8"
    )

    profile = discover_profile(tmp_path)

    assert profile.language == "java"
    assert profile.framework == "spring-boot-gradle"
