"""Unified language capability facade for generation and validation.

``get_language_capabilities`` reports the declared contract for a language:
what the adapter and target stack are designed to support. The host may lack a
compiler or test runner, which is a runtime environment fact, so callers that
need to decide whether to actually run a command must use
``probe_language_compiler`` / ``probe_language_test_runner`` instead of reading
the static flags.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from app.agent.adapters import LanguageAdapter, LanguageAdapterRegistry


@dataclass(frozen=True)
class LanguageCapabilities:
    language: str
    extensions: tuple[str, ...]
    supports_ast: bool = True
    supports_module_resolution: bool = True
    supports_signatures: bool = True
    supports_compile: bool = False
    supports_tests: bool = False


_CAPABILITIES: dict[str, LanguageCapabilities] = {
    "python": LanguageCapabilities("python", (".py",), supports_compile=True, supports_tests=True),
    "javascript": LanguageCapabilities("javascript", (".js", ".jsx",), supports_compile=True, supports_tests=True),
    "typescript": LanguageCapabilities("typescript", (".ts", ".tsx"), supports_compile=True, supports_tests=True),
    "java": LanguageCapabilities("java", (".java",), supports_compile=True, supports_tests=True),
    "go": LanguageCapabilities("go", (".go",), supports_compile=True, supports_tests=True),
    "rust": LanguageCapabilities("rust", (".rs",), supports_compile=True, supports_tests=True),
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


_COMPILER_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "python": ("python3", "python"),
    "javascript": ("node",),
    "typescript": ("tsc",),
    "java": ("javac",),
    "go": ("go",),
    "rust": ("rustc", "cargo"),
}

_TEST_RUNNER_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "python": ("python3", "python"),
    "javascript": ("npm", "node"),
    "typescript": ("npm", "node"),
    "java": ("mvn", "gradle"),
    "go": ("go",),
    "rust": ("cargo",),
}


def _missing(executables: dict[str, tuple[str, ...]], language: str) -> tuple[str, ...]:
    normalized = {"js": "javascript", "ts": "typescript"}.get(language.lower(), language.lower())
    required = executables.get(normalized)
    if not required:
        return ()
    return () if any(shutil.which(item) for item in required) else required


def probe_language_compiler(language: str) -> tuple[str, ...]:
    """Return the compiler executables missing on this host, empty when usable."""
    return _missing(_COMPILER_EXECUTABLES, language)


def probe_language_test_runner(language: str) -> tuple[str, ...]:
    """Return the test-runner executables missing on this host, empty when usable."""
    return _missing(_TEST_RUNNER_EXECUTABLES, language)


__all__ = [
    "LanguageCapabilities",
    "get_language_adapter",
    "get_language_capabilities",
    "probe_language_compiler",
    "probe_language_test_runner",
]
