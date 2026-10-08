"""Render findings for humans (colored text) or machines (JSON)."""

import json
import os
import sys
from collections import defaultdict
from typing import TextIO

from k8s_validator.models import Finding, Resource, Severity

_COLORS = {
    Severity.CRITICAL: "\033[1;31m",
    Severity.WARNING: "\033[33m",
    "ok": "\033[32m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def use_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class TextReporter:
    def __init__(self, stream: TextIO | None = None, color: bool | None = None) -> None:
        self.stream = stream or sys.stdout
        self.color = use_color(self.stream) if color is None else color

    def _c(self, key: str | Severity, text: str) -> str:
        return f"{_COLORS[key]}{text}{_COLORS['reset']}" if self.color else text

    def report(self, resources: list[Resource], findings: list[Finding]) -> None:
        by_resource: dict[tuple[str, str], list[Finding]] = defaultdict(list)
        for f in findings:
            by_resource[(str(f.resource.source), f.resource.ref)].append(f)

        for resource in resources:
            key = (str(resource.source), resource.ref)
            items = by_resource.get(key, [])
            status = self._c("ok", "PASS") if not items else self._c(_worst(items), "FAIL" if _has_critical(items) else "WARN")
            self.stream.write(f"{status}  {self._c('bold', resource.ref)}  {self._c('dim', str(resource.source))}\n")
            for f in sorted(items, key=lambda x: (x.severity != Severity.CRITICAL, x.rule)):
                where = f" [{f.container}]" if f.container else ""
                label = self._c(f.severity, f"{f.severity.value:<8}")
                self.stream.write(f"      {label} {f.rule:<16}{where} {f.message}\n")

        critical = sum(f.severity == Severity.CRITICAL for f in findings)
        warnings = len(findings) - critical
        self.stream.write("\n" + "-" * 72 + "\n")
        self.stream.write(
            f"Scanned {len(resources)} resource(s): "
            f"{self._c(Severity.CRITICAL, f'{critical} critical')}, "
            f"{self._c(Severity.WARNING, f'{warnings} warning(s)')}\n"
        )
        if not resources:
            self.stream.write("No Deployment, StatefulSet, DaemonSet or Service resources found.\n")


class JsonReporter:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def report(self, resources: list[Resource], findings: list[Finding]) -> None:
        critical = sum(f.severity == Severity.CRITICAL for f in findings)
        payload = {
            "summary": {
                "resources": len(resources),
                "critical": critical,
                "warnings": len(findings) - critical,
            },
            "findings": [f.to_dict() for f in findings],
        }
        json.dump(payload, self.stream, indent=2)
        self.stream.write("\n")


def _has_critical(findings: list[Finding]) -> bool:
    return any(f.severity == Severity.CRITICAL for f in findings)


def _worst(findings: list[Finding]) -> Severity:
    return Severity.CRITICAL if _has_critical(findings) else Severity.WARNING
