"""Framework-independent capability contracts."""

from enum import Enum
from typing import FrozenSet, Iterable

from pydantic import BaseModel, ConfigDict, Field


class Capability(str, Enum):
    HTTP_API = "http_api"
    ORM = "orm"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    WEBSOCKET = "websocket"
    DEPENDENCY_INJECTION = "dependency_injection"
    TEST_CLIENT = "test_client"
    MIGRATIONS = "migrations"


class CapabilitySet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    values: FrozenSet[Capability] = Field(default_factory=frozenset)

    @classmethod
    def from_values(cls, values: Iterable[Capability | str]) -> "CapabilitySet":
        return cls(values=frozenset(Capability(value) for value in values))

    def supports(self, capability: Capability | str) -> bool:
        return Capability(capability) in self.values


__all__ = ["Capability", "CapabilitySet"]
