"""Validation rules.

Each check is a plain function ``(Resource) -> Iterable[Finding]`` registered in
``CHECKS`` together with the resource kinds it applies to. Adding a rule means
writing one function and adding one line to the registry.
"""

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from k8s_validator.models import Finding, Resource, Severity

WORKLOAD_KINDS = frozenset({"Deployment", "StatefulSet", "DaemonSet"})
REPLICATED_KINDS = frozenset({"Deployment", "StatefulSet"})
ALL_KINDS = WORKLOAD_KINDS | {"Service"}

RECOMMENDED_LABELS = (
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/version",
)

Check = Callable[[Resource], Iterable[Finding]]


# --------------------------------------------------------------------------- helpers


def pod_spec(resource: Resource) -> dict[str, Any]:
    return ((resource.body.get("spec") or {}).get("template") or {}).get("spec") or {}


def containers(resource: Resource, include_init: bool = False) -> Iterator[dict[str, Any]]:
    spec = pod_spec(resource)
    keys = ("initContainers", "containers") if include_init else ("containers",)
    for key in keys:
        for container in spec.get(key) or []:
            if isinstance(container, dict):
                yield container


def image_tag(image: str) -> str | None:
    """Return the tag of an image reference, ``None`` if untagged, or ``"@digest"`` if pinned."""
    if "@" in image:
        return "@digest"
    last_segment = image.rsplit("/", 1)[-1]  # avoid treating a registry port as a tag
    if ":" in last_segment:
        return last_segment.rsplit(":", 1)[1]
    return None


# --------------------------------------------------------------------------- checks


def check_image_tag(resource: Resource) -> Iterator[Finding]:
    for c in containers(resource, include_init=True):
        image = c.get("image", "")
        tag = image_tag(image)
        if tag is None or tag == "latest":
            reason = "has no tag (implicit :latest)" if tag is None else "uses the 'latest' tag"
            yield Finding(
                rule="image-tag",
                severity=Severity.CRITICAL,
                message=f"Image '{image}' {reason}; pin a version or digest",
                resource=resource,
                container=c.get("name"),
            )


def check_resources(resource: Resource) -> Iterator[Finding]:
    for c in containers(resource):
        res = c.get("resources") or {}
        missing = [
            f"{section}.{name}"
            for section in ("requests", "limits")
            for name in ("cpu", "memory")
            if name not in (res.get(section) or {})
        ]
        if missing:
            yield Finding(
                rule="resources",
                severity=Severity.WARNING,
                message=f"Missing resource settings: {', '.join(missing)}",
                resource=resource,
                container=c.get("name"),
            )


def check_privileged(resource: Resource) -> Iterator[Finding]:
    for c in containers(resource, include_init=True):
        if (c.get("securityContext") or {}).get("privileged") is True:
            yield Finding(
                rule="privileged",
                severity=Severity.CRITICAL,
                message="Container runs in privileged mode",
                resource=resource,
                container=c.get("name"),
            )


def check_run_as_root(resource: Resource) -> Iterator[Finding]:
    pod_ctx = pod_spec(resource).get("securityContext") or {}
    for c in containers(resource, include_init=True):
        ctx = c.get("securityContext") or {}
        # Container-level settings override pod-level ones.
        run_as_user = ctx.get("runAsUser", pod_ctx.get("runAsUser"))
        run_as_non_root = ctx.get("runAsNonRoot", pod_ctx.get("runAsNonRoot"))

        if run_as_user == 0:
            yield Finding(
                rule="run-as-root",
                severity=Severity.CRITICAL,
                message="Container runs as root (runAsUser: 0)",
                resource=resource,
                container=c.get("name"),
            )
        elif run_as_non_root is not True and run_as_user is None:
            yield Finding(
                rule="run-as-root",
                severity=Severity.WARNING,
                message="Non-root not enforced; set runAsNonRoot: true or a non-zero runAsUser",
                resource=resource,
                container=c.get("name"),
            )


def check_probes(resource: Resource) -> Iterator[Finding]:
    for c in containers(resource):
        missing = [p for p in ("readinessProbe", "livenessProbe") if not c.get(p)]
        if missing:
            yield Finding(
                rule="probes",
                severity=Severity.WARNING,
                message=f"Missing {' and '.join(missing)}",
                resource=resource,
                container=c.get("name"),
            )


def check_replicas(resource: Resource) -> Iterator[Finding]:
    if "replicas" not in (resource.body.get("spec") or {}):
        yield Finding(
            rule="replicas",
            severity=Severity.WARNING,
            message="spec.replicas is not set (defaults to 1, no redundancy)",
            resource=resource,
        )


def check_labels(resource: Resource) -> Iterator[Finding]:
    labels = (resource.body.get("metadata") or {}).get("labels") or {}
    missing = [label for label in RECOMMENDED_LABELS if label not in labels]
    if missing:
        yield Finding(
            rule="labels",
            severity=Severity.WARNING,
            message=f"Missing recommended labels: {', '.join(missing)}",
            resource=resource,
        )


def check_service_selector(resource: Resource) -> Iterator[Finding]:
    spec = resource.body.get("spec") or {}
    if spec.get("type") != "ExternalName" and not spec.get("selector"):
        yield Finding(
            rule="service-selector",
            severity=Severity.WARNING,
            message="Service has no selector and will not route to any pods",
            resource=resource,
        )


CHECKS: list[tuple[frozenset[str], Check]] = [
    (WORKLOAD_KINDS, check_image_tag),
    (WORKLOAD_KINDS, check_resources),
    (WORKLOAD_KINDS, check_privileged),
    (WORKLOAD_KINDS, check_run_as_root),
    (WORKLOAD_KINDS, check_probes),
    (REPLICATED_KINDS, check_replicas),
    (ALL_KINDS, check_labels),
    (frozenset({"Service"}), check_service_selector),
]


def validate(resources: Iterable[Resource]) -> list[Finding]:
    """Run every applicable check against every resource."""
    findings: list[Finding] = []
    for resource in resources:
        for kinds, check in CHECKS:
            if resource.kind in kinds:
                findings.extend(check(resource))
    return findings
