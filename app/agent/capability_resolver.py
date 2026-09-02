"""Resolve application-domain capabilities into generation and validation policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


@dataclass(frozen=True)
class ResolvedCapabilities:
    domain: str
    required: Tuple[str, ...]
    available: Tuple[str, ...]
    missing: Tuple[str, ...]
    generation_constraints: Tuple[str, ...]
    validation_steps: Tuple[str, ...]
    required_components: Tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing

    def component_file_plan(self) -> Tuple[Tuple[str, str], ...]:
        plans = {
            "web": (("app/handlers.py", "handler"), ("app/services.py", "service"), ("app/persistence.py", "persistence")),
            "game": (("game/rules.py", "rules"), ("game/renderer.py", "renderer"), ("game/input_loop.py", "input_loop")),
            "scraper": (("scraper/fetcher.py", "fetcher"), ("scraper/parser.py", "parser"), ("scraper/pipeline.py", "pipeline")),
            "android": (("app/src/main/java/app/MainActivity.kt", "screen"), ("app/src/main/java/app/AppNavigation.kt", "navigation"), ("app/src/main/java/app/TodoViewModel.kt", "view_model")),
            "windows": (("app/window.py", "window"), ("app/events.py", "event_handler")),
            "cli": (("app/command.py", "command"),),
        }
        return plans.get(self.domain, plans["cli"])


_DOMAIN_POLICY = {
    "web": (
        ("http_api", "database", "test_client"),
        ("expose a health endpoint", "keep request and persistence contracts aligned"),
        ("syntax", "tests", "startup", "persistence"), ("handler", "service", "persistence"),
    ),
    "game": (
        ("desktop_window", "event_loop", "2d_rendering", "input"),
        ("keep game rules independent from rendering", "provide a deterministic headless test path"),
        ("syntax", "rules", "headless_startup"), ("rules", "renderer", "input_loop"),
    ),
    "scraper": (
        ("http_client", "selectors", "pipelines"),
        ("separate fetching, parsing, and persistence", "bound request concurrency and retries"),
        ("syntax", "parser", "pipeline"), ("fetcher", "parser", "pipeline"),
    ),
    "android": (
        ("mobile_ui", "navigation", "build"),
        ("keep UI state and domain logic separate", "verify a debug build"),
        ("compile", "unit_tests", "debug_build"), ("screen", "navigation", "view_model"),
    ),
    "windows": (
        ("desktop_window", "event_loop"),
        ("keep platform integration behind an application boundary", "provide a non-interactive smoke test"),
        ("syntax", "smoke_test", "package"), ("window", "event_handler"),
    ),
    "cli": (
        ("command_line",),
        ("return actionable exit codes",),
        ("syntax", "command_test"), ("command",),
    ),
}


def resolve_capabilities(profile: Mapping[str, object]) -> ResolvedCapabilities:
    domain = str(profile.get("domain", "cli")).lower()
    required, constraints, validation, components = _DOMAIN_POLICY.get(domain, _DOMAIN_POLICY["cli"])
    available_values = {str(item) for item in profile.get("capabilities", ())}
    if {"mouse_input", "keyboard_input"} & available_values:
        available_values.add("input")
    available = tuple(sorted(available_values))
    missing = tuple(item for item in required if item not in available)
    return ResolvedCapabilities(domain, required, available, missing, constraints, validation, components)


__all__ = ["ResolvedCapabilities", "resolve_capabilities"]
