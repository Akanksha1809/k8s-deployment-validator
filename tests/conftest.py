import copy
from pathlib import Path
from typing import Any

import pytest

from k8s_validator.models import Resource

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

GOOD_DEPLOYMENT: dict[str, Any] = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "app",
        "labels": {
            "app.kubernetes.io/name": "app",
            "app.kubernetes.io/instance": "app-prod",
            "app.kubernetes.io/version": "1.0.0",
        },
    },
    "spec": {
        "replicas": 2,
        "template": {
            "spec": {
                "securityContext": {"runAsNonRoot": True, "runAsUser": 1000},
                "containers": [
                    {
                        "name": "app",
                        "image": "registry.example.com:5000/team/app:1.0.0",
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "64Mi"},
                            "limits": {"cpu": "200m", "memory": "128Mi"},
                        },
                        "readinessProbe": {"httpGet": {"path": "/ready", "port": 8080}},
                        "livenessProbe": {"httpGet": {"path": "/live", "port": 8080}},
                    }
                ],
            }
        },
    },
}


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture
def make_resource():
    """Build a Resource from GOOD_DEPLOYMENT, optionally mutated by a callback."""

    def _make(mutate=None, kind: str = "Deployment") -> Resource:
        body = copy.deepcopy(GOOD_DEPLOYMENT)
        body["kind"] = kind
        if mutate:
            mutate(body)
        return Resource(kind=kind, name=body["metadata"]["name"], namespace="default", source=Path("test.yaml"), body=body)

    return _make


def container(body: dict[str, Any]) -> dict[str, Any]:
    return body["spec"]["template"]["spec"]["containers"][0]
