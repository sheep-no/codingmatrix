"""Discover candidate application profiles from workspace evidence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from app.agent.evaluation_matrix import ApplicationDomain
from app.agent.toolchain import CommandSpec, ToolchainAction
from app.agent.capability_resolver import resolve_capabilities


@dataclass(frozen=True)
class CapabilityGap:
    capability: str
    reason: str
    required: bool = True


@dataclass(frozen=True)
class DiscoveredProfile:
    language: str
    framework: str
    domain: ApplicationDomain
    evidence: Tuple[str, ...]
    capabilities: Tuple[str, ...]
    gaps: Tuple[CapabilityGap, ...] = ()
    status: str = "custom_pending"


@dataclass(frozen=True)
class ProfileProbeResult:
    profile: DiscoveredProfile
    passed: bool
    checks: Tuple[str, ...]
    failures: Tuple[str, ...] = ()


class ProfileCache:
    """Persist discovered profiles as workspace-scoped, versioned metadata."""

    schema_version = 1

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.path = workspace / ".monkeycode" / "profiles.json"

    def get(self, language: str, framework: str) -> DiscoveredProfile | None:
        payload = self._read()
        item = payload.get("profiles", {}).get(self._key(language, framework))
        if item is None:
            return None
        return DiscoveredProfile(
            language=item["language"], framework=item["framework"],
            domain=ApplicationDomain(item["domain"]), evidence=tuple(item.get("evidence", ())),
            capabilities=tuple(item.get("capabilities", ())),
            gaps=tuple(CapabilityGap(**gap) for gap in item.get("gaps", ())),
            status=item.get("status", "custom_pending"),
        )

    def put(self, profile: DiscoveredProfile) -> None:
        payload = self._read()
        payload.setdefault("profiles", {})[self._key(profile.language, profile.framework)] = {
            "language": profile.language,
            "framework": profile.framework,
            "domain": profile.domain.value,
            "evidence": list(profile.evidence),
            "capabilities": list(profile.capabilities),
            "gaps": [{"capability": gap.capability, "reason": gap.reason, "required": gap.required} for gap in profile.gaps],
            "status": profile.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_path = tempfile.mkstemp(prefix="profiles-", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": self.schema_version, **payload}, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
            os.replace(temporary_path, self.path)
        except Exception:
            os.close(handle) if not stream.closed else None
            raise

    def record_probe(self, result: ProfileProbeResult) -> DiscoveredProfile:
        """Persist probe state and return the updated profile."""
        status = "experimental" if result.passed else "custom_pending"
        updated = DiscoveredProfile(
            language=result.profile.language,
            framework=result.profile.framework,
            domain=result.profile.domain,
            evidence=result.profile.evidence,
            capabilities=result.profile.capabilities,
            gaps=tuple(CapabilityGap("probe", failure) for failure in result.failures),
            status=status,
        )
        self.put(updated)
        return updated

    def promote_supported(self, profile: DiscoveredProfile, *, required_checks: Tuple[str, ...], checks: Tuple[str, ...]) -> DiscoveredProfile:
        """Promote a profile only after every required conformance check passes."""
        if profile.status != "experimental" or not set(required_checks).issubset(checks):
            raise ValueError("profile requires a passing experimental probe and complete conformance checks")
        updated = DiscoveredProfile(
            language=profile.language, framework=profile.framework, domain=profile.domain,
            evidence=profile.evidence, capabilities=profile.capabilities, gaps=(), status="supported",
        )
        self.put(updated)
        return updated

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema_version": self.schema_version, "profiles": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != self.schema_version:
            return {"schema_version": self.schema_version, "profiles": {}}
        return payload

    @staticmethod
    def _key(language: str, framework: str) -> str:
        return f"{language.lower()}:{framework.lower()}"


@dataclass(frozen=True)
class ProfileProbeStep:
    name: str
    command: Tuple[str, ...]
    action: ToolchainAction
    required: bool = True

    def __post_init__(self) -> None:
        CommandSpec(action=self.action, command=self.command)


def build_probe_plan(profile: DiscoveredProfile) -> Tuple[ProfileProbeStep, ...]:
    """Create safe, non-shell probe commands for a discovered profile."""
    steps = [ProfileProbeStep("syntax", ("python3", "-m", "py_compile", "main.py"), ToolchainAction.BUILD)]
    if profile.language in {"typescript", "javascript"}:
        steps = [ProfileProbeStep("build", ("npm", "run", "build"), ToolchainAction.BUILD)]
    if profile.domain is ApplicationDomain.ANDROID:
        steps = [ProfileProbeStep("build", ("./gradlew", "assembleDebug"), ToolchainAction.BUILD)]
    if profile.domain is ApplicationDomain.GAME:
        steps.append(ProfileProbeStep("event_loop", ("python3", "-m", "pytest", "tests"), ToolchainAction.TEST))
    elif profile.domain is ApplicationDomain.SCRAPER:
        steps.append(ProfileProbeStep("scraper_tests", ("python3", "-m", "pytest"), ToolchainAction.TEST))
    else:
        steps.append(ProfileProbeStep("tests", ("python3", "-m", "pytest"), ToolchainAction.TEST))
    return tuple(steps)


def discover_profile(workspace: Path) -> DiscoveredProfile:
    evidence: list[str] = []
    capabilities: list[str] = []
    gaps: list[CapabilityGap] = []
    language = "unknown"
    framework = "unknown"
    domain = ApplicationDomain.CLI

    package_json = workspace / "package.json"
    if package_json.exists():
        language = "typescript"
        evidence.append("package.json")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        if "electron" in dependencies:
            domain, framework = ApplicationDomain.WINDOWS, "electron"
            capabilities.extend(("desktop_window", "event_loop"))
        elif "react-native" in dependencies or "@react-native" in " ".join(dependencies):
            domain, framework = ApplicationDomain.ANDROID, "react-native"
            capabilities.extend(("mobile_ui", "navigation"))
        elif "express" in dependencies:
            domain, framework = ApplicationDomain.WEB, "express"
            capabilities.extend(("http_api", "test_client"))
        else:
            gaps.append(CapabilityGap("framework", "package.json contains no recognized framework"))
    elif (workspace / "requirements.txt").exists() or (workspace / "pyproject.toml").exists():
        language = "python"
        evidence.append("python manifest")
        manifest = ""
        for name in ("requirements.txt", "pyproject.toml"):
            path = workspace / name
            if path.exists():
                manifest += path.read_text(encoding="utf-8").lower()
                evidence.append(name)
        if "pygame" in manifest:
            domain, framework = ApplicationDomain.GAME, "pygame"
            capabilities.extend(("desktop_window", "2d_rendering", "event_loop", "mouse_input"))
        elif "scrapy" in manifest:
            domain, framework = ApplicationDomain.SCRAPER, "scrapy"
            capabilities.extend(("http_client", "selectors", "pipelines"))
        elif "fastapi" in manifest:
            domain, framework = ApplicationDomain.WEB, "fastapi"
            capabilities.extend(("http_api", "test_client"))
        else:
            gaps.append(CapabilityGap("framework", "Python manifest contains no recognized framework"))
    elif (workspace / "build.gradle").exists() or (workspace / "settings.gradle").exists():
        language, domain, framework = "kotlin", ApplicationDomain.ANDROID, "android-gradle"
        evidence.append("Gradle manifest")
        capabilities.extend(("mobile_ui", "build"))
    else:
        gaps.append(CapabilityGap("language", "no supported project manifest was found"))

    return DiscoveredProfile(language, framework, domain, tuple(evidence), tuple(capabilities), tuple(gaps))


def discover_or_load_profile(workspace: Path) -> DiscoveredProfile:
    """Reuse a cached profile when its language/framework can be identified."""
    discovered = discover_profile(workspace)
    cache = ProfileCache(workspace)
    cached = cache.get(discovered.language, discovered.framework)
    return cached or discovered


def profile_context(workspace: Path) -> dict:
    """Return a serializable profile projection for generation contexts."""
    profile = discover_or_load_profile(workspace)
    context = {
        "language": profile.language,
        "framework": profile.framework,
        "domain": profile.domain.value,
        "capabilities": list(profile.capabilities),
        "gaps": [
            {"capability": gap.capability, "reason": gap.reason, "required": gap.required}
            for gap in profile.gaps
        ],
        "status": profile.status,
        "evidence": list(profile.evidence),
    }
    resolved = resolve_capabilities(context)
    context["capability_policy"] = {
        "required": list(resolved.required),
        "missing": list(resolved.missing),
        "generation_constraints": list(resolved.generation_constraints),
        "validation_steps": list(resolved.validation_steps),
        "required_components": list(resolved.required_components),
        "component_file_plan": [
            {"path": path, "component": component}
            for path, component in resolved.component_file_plan()
        ],
        "ready": resolved.ready,
    }
    return context


def probe_profile(profile: DiscoveredProfile, *, checks: Tuple[str, ...]) -> ProfileProbeResult:
    failures = tuple(gap.reason for gap in profile.gaps if gap.required)
    passed = bool(checks) and not failures
    return ProfileProbeResult(profile=profile, passed=passed, checks=checks, failures=failures)


__all__ = ["CapabilityGap", "DiscoveredProfile", "ProfileProbeResult", "ProfileProbeStep", "ProfileCache", "discover_profile", "discover_or_load_profile", "profile_context", "probe_profile", "build_probe_plan"]
