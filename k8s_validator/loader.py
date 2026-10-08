"""Discover and parse Kubernetes manifests from disk."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from k8s_validator.models import Resource

SUPPORTED_KINDS = frozenset({"Deployment", "StatefulSet", "DaemonSet", "Service"})
YAML_SUFFIXES = frozenset({".yaml", ".yml"})


class ManifestError(Exception):
    """Raised when a manifest file cannot be read or parsed."""


def find_manifest_files(path: Path) -> list[Path]:
    """Return all YAML files under ``path`` (or ``path`` itself if it is a file), sorted."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ManifestError(f"Path does not exist: {path}")
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in YAML_SUFFIXES)


def _iter_objects(doc: Any) -> Iterator[dict[str, Any]]:
    """Yield Kubernetes objects from a YAML document, flattening ``kind: List``."""
    if not isinstance(doc, dict):
        return
    if doc.get("kind") == "List" and isinstance(doc.get("items"), list):
        for item in doc["items"]:
            yield from _iter_objects(item)
    else:
        yield doc


def parse_file(path: Path) -> list[Resource]:
    """Parse every supported resource from a (possibly multi-document) YAML file."""
    try:
        with path.open(encoding="utf-8") as fh:
            documents = list(yaml.safe_load_all(fh))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"{path}: {exc}") from exc

    resources: list[Resource] = []
    for doc in documents:
        for obj in _iter_objects(doc):
            kind = obj.get("kind")
            if kind not in SUPPORTED_KINDS:
                continue
            metadata = obj.get("metadata") or {}
            resources.append(
                Resource(
                    kind=kind,
                    name=metadata.get("name", "<unnamed>"),
                    namespace=metadata.get("namespace", "default"),
                    source=path,
                    body=obj,
                )
            )
    return resources


def load_resources(path: Path) -> list[Resource]:
    """Load all supported resources found under ``path``."""
    resources: list[Resource] = []
    for file in find_manifest_files(path):
        resources.extend(parse_file(file))
    return resources
