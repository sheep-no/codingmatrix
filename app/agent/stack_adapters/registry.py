"""Registry for resolving and detecting built-in stack adapters."""

from __future__ import annotations

from pathlib import Path

from app.agent.code_synthesis_contracts import ProjectModel
from app.agent.profile_discovery import discover_profile

from .adapters import (
    ExpressStackAdapter,
    FastAPIStackAdapter,
    GoStackAdapter,
    SpringStackAdapter,
)
from .base import StackAdapter


class StackAdapterRegistry:
    def __init__(self, adapters: tuple[StackAdapter, ...] = ()) -> None:
        self._adapters: dict[tuple[str, str], StackAdapter] = {}
        self._unique: list[StackAdapter] = []
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: StackAdapter) -> None:
        for language, framework in adapter.aliases:
            key = self._key(language, framework)
            existing = self._adapters.get(key)
            if existing is not None and existing is not adapter:
                raise ValueError(f"stack adapter alias is already registered: {language}/{framework}")
            self._adapters[key] = adapter
        if adapter not in self._unique:
            self._unique.append(adapter)

    def get(self, language: str, framework: str) -> StackAdapter | None:
        return self._adapters.get(self._key(language, framework))

    def require(self, language: str, framework: str) -> StackAdapter:
        adapter = self.get(language, framework)
        if adapter is None:
            raise LookupError(f"stack adapter not found: {language}/{framework}")
        return adapter

    def detect(self, workspace: Path) -> tuple[StackAdapter, ProjectModel]:
        discovered = discover_profile(workspace)
        adapter = self.require(discovered.language, discovered.framework)
        return adapter, adapter.detect(workspace)

    def all(self) -> tuple[StackAdapter, ...]:
        return tuple(self._unique)

    @staticmethod
    def _key(language: str, framework: str) -> tuple[str, str]:
        language_key = {"js": "javascript", "ts": "typescript"}.get(
            language.lower(), language.lower()
        )
        return language_key, framework.lower()


DEFAULT_STACK_ADAPTERS = StackAdapterRegistry((
    FastAPIStackAdapter(),
    ExpressStackAdapter(),
    GoStackAdapter(),
    SpringStackAdapter(),
))


__all__ = ["DEFAULT_STACK_ADAPTERS", "StackAdapterRegistry"]
