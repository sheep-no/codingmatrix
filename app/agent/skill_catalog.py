"""Structured discovery for workspace and market Skills."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Tuple

from pydantic import BaseModel, ConfigDict, Field

_DISCOVERY_STOPWORDS = {
    "a", "an", "and", "build", "generate", "implement", "only", "plus",
    "point", "project", "runnable", "simple", "small", "standard", "the",
    "using", "with", "library", "operations", "command", "line", "entry",
}


def discovery_terms(value: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[\w一-龥+#.-]+", value or "")
        if len(term) > 1 and term.lower() not in _DISCOVERY_STOPWORDS
    }


class SkillManifest(BaseModel):
    """Stable metadata used to compose Skills without loading every Skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(default="1", min_length=1)
    kind: str = Field(default="capability", min_length=1)
    source: str = Field(default="workspace", min_length=1)
    path: str = Field(min_length=1)
    description: str = ""
    languages: Tuple[str, ...] = ()
    frameworks: Tuple[str, ...] = ()
    databases: Tuple[str, ...] = ()
    capabilities: Tuple[str, ...] = ()
    stages: Tuple[str, ...] = ()
    priority: int = Field(default=50, ge=0, le=100)
    content: str = Field(min_length=1)

    def score(self, query: str) -> int:
        terms = discovery_terms(query)
        declared_fields = (
            self.name,
            self.description,
            *self.languages,
            *self.frameworks,
            *self.databases,
            *self.capabilities,
            *self.stages,
        )
        searchable = {
            token
            for value in declared_fields
            for token in discovery_terms(value)
        }
        # Match declared metadata strongly; prose bodies contain generic workflow
        # words that otherwise make unrelated skills look relevant.
        match_score = sum(4 for term in terms if term in searchable)
        return match_score + (self.priority // 25 if match_score else 0)


class SkillCatalog:
    """Discover and rank structured Skills from a bounded directory."""

    def __init__(self, skills: Iterable[SkillManifest] = ()) -> None:
        self._skills = tuple(skills)

    @classmethod
    def from_directory(cls, directory: Path, *, source: str = "workspace") -> "SkillCatalog":
        skills = []
        if not directory.exists():
            return cls()
        for skill_file in sorted(directory.glob("*/SKILL.md")):
            try:
                content = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            metadata, body = _parse_front_matter(content)
            directory_name = skill_file.parent.name
            skills.append(SkillManifest(
                name=metadata.get("name", directory_name),
                version=str(metadata.get("version", "1")),
                kind=str(metadata.get("kind", "capability")),
                source=source,
                path=str(skill_file),
                description=str(metadata.get("description", _first_description(body))),
                languages=_as_tuple(metadata.get("languages")),
                frameworks=_as_tuple(metadata.get("frameworks")),
                databases=_as_tuple(metadata.get("databases")),
                capabilities=_as_tuple(metadata.get("capabilities")),
                stages=_as_tuple(metadata.get("stages")),
                priority=int(metadata.get("priority", 50)),
                content=body.strip() or content.strip(),
            ))
        return cls(skills)

    def all(self) -> Tuple[SkillManifest, ...]:
        return self._skills

    def discover(self, query: str, *, limit: int = 5) -> Tuple[SkillManifest, ...]:
        ranked = sorted(
            ((skill.score(query), skill) for skill in self._skills),
            key=lambda item: (-item[0], item[1].name),
        )
        return tuple(skill for score, skill in ranked[: max(0, limit)] if score >= 8)


def _parse_front_matter(content: str) -> tuple[dict[str, str | list[str]], str]:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, content
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}, content
    metadata: dict[str, str | list[str]] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        normalized_key = key.strip()
        # Front matter can contain nested argument descriptions. Preserve the
        # top-level Skill description when a nested field repeats the key.
        if normalized_key not in metadata:
            metadata[normalized_key] = value
    return metadata, "\n".join(lines[end + 1:])


def _as_tuple(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    return tuple(item.strip().lower() for item in str(value).split(",") if item.strip())


def _first_description(content: str) -> str:
    return next(
        (line.strip() for line in content.splitlines()
         if line.strip() and not line.lstrip().startswith("#")),
        "",
    )


__all__ = ["SkillCatalog", "SkillManifest"]
