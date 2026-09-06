from app.agent.capability_resolver import resolve_capabilities


def test_pygame_capabilities_produce_game_generation_policy():
    result = resolve_capabilities({
        "domain": "game",
        "capabilities": ("desktop_window", "event_loop", "2d_rendering", "input"),
    })

    assert result.ready
    assert "keep game rules independent from rendering" in result.generation_constraints
    assert "headless_startup" in result.validation_steps
    assert "renderer" in result.required_components


def test_unknown_domain_uses_safe_cli_policy():
    result = resolve_capabilities({"domain": "new-runtime", "capabilities": ()})

    assert result.ready is False
    assert result.required == ("command_line",)
    assert result.missing == ("command_line",)


def test_scraper_reports_missing_pipeline_capability():
    result = resolve_capabilities({"domain": "scraper", "capabilities": ("http_client", "selectors")})

    assert result.missing == ("pipelines",)
    assert "pipeline" in result.validation_steps


def test_pygame_mouse_input_satisfies_generic_input_requirement():
    result = resolve_capabilities({
        "domain": "game",
        "capabilities": ("desktop_window", "event_loop", "2d_rendering", "mouse_input"),
    })

    assert "input" not in result.missing
    assert result.component_file_plan()[0] == ("game/rules.py", "rules")
