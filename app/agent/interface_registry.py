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
        if isinstance(entries, str) or entries is None:
            entries = ()
        elif isinstance(entries, Mapping):
            entries = (entries,)
        normalized = tuple(sorted(
            (_coerce_entry(entry) for entry in entries if isinstance(entry, (Mapping, InterfaceEntry))),
            key=lambda item: (item.module, item.owner),
        ))
        normalized = _merge_entries(normalized)
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
    symbols = tuple(_coerce_symbol(item) for item in raw_symbols or ())
    return InterfaceEntry(module=str(entry.get("module", entry.get("path", ""))), owner=str(entry.get("owner", entry.get("module", entry.get("path", "")))), symbols=symbols)


# InterfaceSymbol 的字段集合。架构师提示未固定 symbol 的 schema，模型常额外输出
# signature/description 之类的描述性键，这类键不属于契约（访问器只用
# name/parameters/return_type/is_async/visibility），在强模型校验前丢弃即可，
# 不应因为一个描述字段就让整个生成计划冻结失败。
_SYMBOL_FIELDS = frozenset(InterfaceSymbol.model_fields)


def _coerce_symbol(item: object) -> InterfaceSymbol:
    if isinstance(item, InterfaceSymbol):
        return item
    if not isinstance(item, Mapping):
        return InterfaceSymbol(name=str(item))
    name = str(item.get("name", item.get("symbol", "")))
    fields = {
        key: value
        for key, value in item.items()
        if key in _SYMBOL_FIELDS and key != "name"
    }
    if "parameters" in fields:
        fields["parameters"] = _coerce_parameters(fields["parameters"])
    return InterfaceSymbol(name=name, **fields)


def _coerce_parameters(value: object) -> Tuple[str, ...]:
    """把参数列表归一化为字符串元组。

    架构师可能给出 "uid"、{"name": "uid", "type": "int"} 或 {"uid": "int"}
    等形态，统一转成 "uid" / "uid: int"。
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Mapping):
        return tuple(_parameter_text(key, item) for key, item in value.items())
    if not isinstance(value, (list, tuple, set, frozenset)):
        return (str(value),)
    return tuple(
        _parameter_text(item.get("name", item.get("symbol", "")), item)
        if isinstance(item, Mapping)
        else str(item)
        for item in value
    )


def _parameter_text(name: object, spec: object) -> str:
    label = str(name)
    annotation = spec.get("type", spec.get("annotation")) if isinstance(spec, Mapping) else spec
    annotation = str(annotation).strip() if annotation else ""
    return f"{label}: {annotation}" if annotation else label


def _validate_entries(entries: Tuple[InterfaceEntry, ...]) -> None:
    owners = {}
    for entry in entries:
        for symbol in entry.symbols:
            if symbol.visibility is not InterfaceVisibility.PUBLIC:
                continue
            previous = owners.get(symbol.name)
            if previous and previous != entry.owner:
                raise ValueError(f"public symbol has multiple owners: {symbol.name}")
            owners[symbol.name] = entry.owner


def _merge_entries(entries: Tuple[InterfaceEntry, ...]) -> Tuple[InterfaceEntry, ...]:
    """合并同一 module 的多条条目（保留首个 owner），符号按出现顺序去重。

    架构师按类/接口逐条输出时同一文件会重复出现，而 registry 的访问器
    （``symbols_for``/``symbol_owner``）本来就按 module 聚合，重复条目只是
    簿记冗余；把它当作硬失败会让合法架构直接中断生成。
    """
    merged: dict[str, Tuple[str, list]] = {}
    for entry in entries:
        owner, symbols = merged.setdefault(entry.module, (entry.owner, []))
        seen = {_symbol_key(symbol) for symbol in symbols}
        for symbol in entry.symbols:
            key = _symbol_key(symbol)
            if key not in seen:
                symbols.append(symbol)
                seen.add(key)
    return tuple(
        InterfaceEntry(module=module, owner=owner, symbols=tuple(symbols))
        for module, (owner, symbols) in merged.items()
    )


def _symbol_key(symbol: InterfaceSymbol) -> Tuple:
    return (symbol.name, symbol.visibility, symbol.parameters, symbol.return_type, symbol.is_async)


def _digest(version: int, entries: Tuple[InterfaceEntry, ...]) -> str:
    payload = {"version": version, "entries": [item.model_dump(mode="json") for item in entries]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
