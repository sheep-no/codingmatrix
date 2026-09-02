"""Frozen cross-file interface contracts for code generation plans."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InterfaceVisibility(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class InterfaceSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    parameters: Tuple[str, ...] = ()
    return_type: Optional[str] = None
    is_async: bool = False
    visibility: InterfaceVisibility = InterfaceVisibility.PUBLIC


class InterfaceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    symbols: Tuple[InterfaceSymbol, ...] = ()


class InterfaceRegistry(BaseModel):
    """A deterministic registry of symbols exposed by planned modules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    entries: Tuple[InterfaceEntry, ...] = ()
    digest: str = Field(default="", min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_digest(self) -> "InterfaceRegistry":
        if self.digest != _digest(self.version, self.entries):
            raise ValueError("interface registry digest does not match its contents")
        return self

    @classmethod
    def build(cls, entries: Iterable[Mapping[str, object] | InterfaceEntry], version: int = 1) -> "InterfaceRegistry":
        normalized = tuple(sorted((_coerce_entry(entry) for entry in entries), key=lambda item: (item.module, item.owner)))
        _validate_entries(normalized)
        digest = _digest(version, normalized)
        return cls(version=version, entries=normalized, digest=digest)

    def symbol_owner(self, symbol: str) -> Optional[str]:
        owners = {entry.owner for entry in self.entries for item in entry.symbols if item.name == symbol}
        return next(iter(owners)) if len(owners) == 1 else None

    def symbols_for(self, module: str) -> Tuple[InterfaceSymbol, ...]:
        return tuple(item for entry in self.entries if entry.module == module for item in entry.symbols)


def _coerce_entry(entry: Mapping[str, object] | InterfaceEntry) -> InterfaceEntry:
    if isinstance(entry, InterfaceEntry):
        return entry
    raw_symbols = entry.get("symbols", entry.get("exports", ()))
    if isinstance(raw_symbols, str):
        raw_symbols = (raw_symbols,)
    symbols = tuple(
        item if isinstance(item, InterfaceSymbol) else InterfaceSymbol(name=str(item.get("name", item.get("symbol", ""))) if isinstance(item, Mapping) else str(item), **({k: v for k, v in item.items() if k not in {"name", "symbol"}} if isinstance(item, Mapping) else {}))
        for item in raw_symbols or ()
    )
    return InterfaceEntry(module=str(entry.get("module", entry.get("path", ""))), owner=str(entry.get("owner", entry.get("module", entry.get("path", "")))), symbols=symbols)


def _validate_entries(entries: Tuple[InterfaceEntry, ...]) -> None:
    seen_modules = set()
    owners = {}
    for entry in entries:
        if entry.module in seen_modules:
            raise ValueError(f"interface module has multiple owners: {entry.module}")
        seen_modules.add(entry.module)
        for symbol in entry.symbols:
            if symbol.visibility is not InterfaceVisibility.PUBLIC:
                continue
            previous = owners.get(symbol.name)
            if previous and previous != entry.owner:
                raise ValueError(f"public symbol has multiple owners: {symbol.name}")
            owners[symbol.name] = entry.owner


def _digest(version: int, entries: Tuple[InterfaceEntry, ...]) -> str:
    payload = {"version": version, "entries": [item.model_dump(mode="json") for item in entries]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
