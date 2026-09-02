from app.agent.evaluation_matrix import ApplicationDomain
from app.agent.profile_discovery import ProfileCache, build_probe_plan, discover_or_load_profile, discover_profile, probe_profile, profile_context


def test_discovery_identifies_pygame_game_workspace(tmp_path):
    (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")

    profile = discover_profile(tmp_path)

    assert profile.language == "python"
    assert profile.framework == "pygame"
    assert profile.domain is ApplicationDomain.GAME
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
