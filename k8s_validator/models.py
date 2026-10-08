"""Core data types shared by the loader, checks and reporter."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Resource:
    """A single Kubernetes object parsed from a manifest file."""

    kind: str
    name: str
    namespace: str
    source: Path
    body: dict[str, Any] = field(repr=False)

    @property
    def ref(self) -> str:
        return f"{self.kind}/{self.name}"


@dataclass(frozen=True)
class Finding:
    """A single rule violation for a resource (and optionally a container)."""

    rule: str
    severity: Severity
    message: str
    resource: Resource
    container: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "kind": self.resource.kind,
            "name": self.resource.name,
            "namespace": self.resource.namespace,
            "file": str(self.resource.source),
            "container": self.container,
        }
