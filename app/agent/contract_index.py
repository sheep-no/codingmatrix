"""Versioned public interface and data contract index for synthesis."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .code_synthesis_contracts import HttpContract
from .interface_registry import InterfaceVisibility

logger = logging.getLogger(__name__)


class ContractEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    schema: Mapping[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)


class ContractIndex(BaseModel):
    """Immutable contract snapshot shared by all files in one plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    entries: Tuple[ContractEntry, ...] = ()
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_index(self) -> "ContractIndex":
        names = [entry.name for entry in self.entries]
        if len(names) != len(set(names)):
            raise ValueError("contract names must be unique")
        if self.digest != _digest(self.version, self.entries):
            raise ValueError("contract index digest does not match its contents")
        return self

    @classmethod
    def build(
        cls,
        entries: Iterable[ContractEntry | Mapping[str, Any]],
        *,
        version: int = 1,
    ) -> "ContractIndex":
        normalized = tuple(
            sorted(
                (entry if isinstance(entry, ContractEntry) else ContractEntry.model_validate(entry) for entry in entries),
                key=lambda entry: entry.name,
            )
        )
        return cls(version=version, entries=normalized, digest=_digest(version, normalized))

    def get(self, name: str) -> Optional[ContractEntry]:
        return next((entry for entry in self.entries if entry.name == name), None)

    def missing(self, names: Iterable[str]) -> Tuple[str, ...]:
        known = {entry.name for entry in self.entries}
        return tuple(sorted(set(names) - known))

    @classmethod
    def from_generation_plan(
        cls,
        plan: Any,
        *,
        contracts: Any = None,
    ) -> "ContractIndex":
        """Freeze plan interfaces, file contracts, and explicit contracts together."""
        entries: list[ContractEntry] = []
        interfaces = getattr(plan, "interfaces", None)
        for interface in getattr(interfaces, "entries", ()):
            for symbol in interface.symbols:
                # InterfaceRegistry 只保证 public 符号全局唯一；private/internal
                # 同名符号是合法的，不能进入以名字为键的契约索引。
                if symbol.visibility is not InterfaceVisibility.PUBLIC:
                    continue
                entries.append(ContractEntry(
                    name=symbol.name,
                    kind="interface",
                    owner=interface.owner,
                    schema={
                        "module": interface.module,
                        "parameters": list(symbol.parameters),
                        "return_type": symbol.return_type,
                        "is_async": symbol.is_async,
                        "visibility": symbol.visibility.value,
                    },
                ))

        for planned_file in getattr(plan, "files", ()):
            schema = dict(getattr(planned_file, "contract", {}) or {})
            if not schema:
                continue
            entries.append(ContractEntry(
                name=str(schema.get("name") or f"file:{planned_file.path}"),
                kind=str(schema.get("kind") or getattr(planned_file, "file_type", None) or "file"),
                owner=str(schema.get("owner") or planned_file.path),
                schema=schema,
                version=int(schema.get("version", 1)),
            ))

        entries.extend(_explicit_contract_entries(contracts))
        # 接口符号、文件契约与显式契约之间可能重名（如文件契约与自身导出同名）。
        # 索引以名字为键，保留首个（接口优先，顺序即来源优先级），避免合法计划
        # 因重名抛 ValidationError 而中断生成。
        unique_entries: list[ContractEntry] = []
        seen_names: set[str] = set()
        for entry in entries:
            if entry.name in seen_names:
                logger.debug("跳过重复契约名: %s", entry.name)
                continue
            seen_names.add(entry.name)
            unique_entries.append(entry)
        return cls.build(unique_entries, version=int(getattr(plan, "version", 1)))


def _digest(version: int, entries: Tuple[ContractEntry, ...]) -> str:
    payload = {"version": version, "entries": [entry.model_dump(mode="json") for entry in entries]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _explicit_contract_entries(contracts: Any) -> Tuple[ContractEntry, ...]:
    if contracts is None:
        return ()
    if isinstance(contracts, ContractIndex):
        return contracts.entries
    if not isinstance(contracts, Mapping):
        raise ValueError("explicit contracts must be a mapping or ContractIndex")

    raw_entries = contracts.get("entries")
    if raw_entries is not None:
        if not isinstance(raw_entries, (list, tuple)):
            raise ValueError("explicit contract entries must be a sequence")
        return tuple(ContractEntry.model_validate(entry) for entry in raw_entries)

    entries = []
    for collection_name in ("routes", "endpoints"):
        raw_routes = contracts.get(collection_name, ())
        if isinstance(raw_routes, Mapping):
            raw_routes = tuple(raw_routes.values())
        if not isinstance(raw_routes, (list, tuple)):
            continue
        for position, raw_route in enumerate(raw_routes):
            if not isinstance(raw_route, Mapping):
                continue
            schema = HttpContract.model_validate(
                raw_route.get("schema", raw_route)
            ).model_dump(mode="json", exclude_unset=True)
            method = str(schema.get("method", "")).upper()
            path = str(schema.get("path", schema.get("route", "")))
            name = str(
                raw_route.get("name")
                or schema.get("operation_id")
                or schema.get("operationId")
                or (f"{method} {path}" if method and path else f"{collection_name}:{position}")
            )
            entries.append(ContractEntry(
                name=name,
                kind="api",
                owner=str(raw_route.get("owner") or contracts.get("owner") or "api"),
                schema=schema,
                version=int(raw_route.get("version", 1)),
            ))
    return tuple(entries)


__all__ = ["ContractEntry", "ContractIndex"]
