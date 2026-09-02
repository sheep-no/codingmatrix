"""Unified language capability facade for generation and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from app.agent.adapters import LanguageAdapter, LanguageAdapterRegistry


@dataclass(frozen=True)
class LanguageCapabilities:
    language: str
    extensions: Tuple[str, ...]
    supports_ast: bool = True
    supports_module_resolution: bool = True
    supports_signatures: bool = True
    supports_compile: bool = False
    supports_tests: bool = False


_CAPABILITIES: Dict[str, LanguageCapabilities] = {
    "python": LanguageCapabilities("python", (".py",), supports_compile=True, supports_tests=True),
    "javascript": LanguageCapabilities("javascript", (".js", ".jsx",), supports_compile=True, supports_tests=True),
    "typescript": LanguageCapabilities("typescript", (".ts", ".tsx"), supports_compile=True, supports_tests=True),
    "generic": LanguageCapabilities("generic", ()),
}


def get_language_adapter(language: str) -> LanguageAdapter:
    """Return the registered adapter while normalizing JS aliases."""
    normalized = "javascript" if language.lower() in {"js", "ts", "typescript", "javascript"} else language.lower()
    adapter = LanguageAdapterRegistry.get_adapter(normalized)
    if adapter is None:
        raise LookupError(f"language adapter not found: {language}")
    return adapter


def get_language_capabilities(language: str) -> LanguageCapabilities:
    normalized = {"js": "javascript", "ts": "typescript"}.get(language.lower(), language.lower())
    return _CAPABILITIES.get(normalized, _CAPABILITIES["generic"])


__all__ = ["LanguageCapabilities", "get_language_adapter", "get_language_capabilities"]
