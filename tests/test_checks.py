import pytest

from k8s_validator import checks
from k8s_validator.models import Severity
from tests.conftest import container


def rules(findings):
    return [(f.rule, f.severity) for f in findings]


def test_good_deployment_has_no_findings(make_resource):
    assert checks.validate([make_resource()]) == []


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("nginx", None),
        ("nginx:latest", "latest"),
        ("nginx:1.27", "1.27"),
        ("localhost:5000/nginx", None),
        ("localhost:5000/nginx:2.0", "2.0"),
        ("nginx@sha256:abc123", "@digest"),
    ],
)
def test_image_tag_parsing(image, expected):
    assert checks.image_tag(image) == expected


@pytest.mark.parametrize("image", ["nginx:latest", "nginx", "localhost:5000/nginx"])
def test_latest_or_untagged_image_is_critical(make_resource, image):
    res = make_resource(lambda b: container(b).update(image=image))
    assert rules(checks.check_image_tag(res)) == [("image-tag", Severity.CRITICAL)]


def test_digest_pinned_image_passes(make_resource):
    res = make_resource(lambda b: container(b).update(image="nginx@sha256:deadbeef"))
    assert list(checks.check_image_tag(res)) == []


def test_init_container_image_is_checked(make_resource):
    def mutate(b):
        b["spec"]["template"]["spec"]["initContainers"] = [{"name": "init", "image": "busybox"}]

    findings = list(checks.check_image_tag(make_resource(mutate)))
    assert [f.container for f in findings] == ["init"]


def test_missing_resources_lists_each_field(make_resource):
    res = make_resource(lambda b: container(b)["resources"].pop("limits"))
    [finding] = checks.check_resources(res)
    assert finding.severity == Severity.WARNING
    assert "limits.cpu" in finding.message and "limits.memory" in finding.message
    assert "requests" not in finding.message


def test_privileged_is_critical(make_resource):
    res = make_resource(lambda b: container(b).update(securityContext={"privileged": True}))
    assert rules(checks.check_privileged(res)) == [("privileged", Severity.CRITICAL)]


def test_run_as_root_container_level_is_critical(make_resource):
    res = make_resource(lambda b: container(b).update(securityContext={"runAsUser": 0}))
    assert rules(checks.check_run_as_root(res)) == [("run-as-root", Severity.CRITICAL)]


def test_run_as_root_pod_level_is_critical(make_resource):
    res = make_resource(lambda b: b["spec"]["template"]["spec"].update(securityContext={"runAsUser": 0}))
    assert rules(checks.check_run_as_root(res)) == [("run-as-root", Severity.CRITICAL)]


def test_container_context_overrides_pod_context(make_resource):
    def mutate(b):
        b["spec"]["template"]["spec"]["securityContext"] = {"runAsUser": 0}
        container(b)["securityContext"] = {"runAsUser": 1000}

    assert list(checks.check_run_as_root(make_resource(mutate))) == []


def test_non_root_not_enforced_is_warning(make_resource):
    res = make_resource(lambda b: b["spec"]["template"]["spec"].pop("securityContext"))
    assert rules(checks.check_run_as_root(res)) == [("run-as-root", Severity.WARNING)]


@pytest.mark.parametrize("probe", ["readinessProbe", "livenessProbe"])
def test_missing_probe_is_warning(make_resource, probe):
    res = make_resource(lambda b: container(b).pop(probe))
    [finding] = checks.check_probes(res)
    assert finding.severity == Severity.WARNING
    assert probe in finding.message


def test_missing_replicas_is_warning(make_resource):
    res = make_resource(lambda b: b["spec"].pop("replicas"))
    assert rules(checks.check_replicas(res)) == [("replicas", Severity.WARNING)]


def test_replicas_not_checked_for_daemonset(make_resource):
    res = make_resource(lambda b: b["spec"].pop("replicas"), kind="DaemonSet")
    assert checks.validate([res]) == []


def test_missing_recommended_labels(make_resource):
    res = make_resource(lambda b: b["metadata"]["labels"].pop("app.kubernetes.io/version"))
    [finding] = checks.check_labels(res)
    assert "app.kubernetes.io/version" in finding.message


def test_service_without_selector_or_labels(make_resource):
    def mutate(b):
        b["metadata"]["labels"] = {}
        b["spec"] = {"ports": [{"port": 80}]}

    res = make_resource(mutate, kind="Service")
    assert sorted(f.rule for f in checks.validate([res])) == ["labels", "service-selector"]


def test_external_name_service_needs_no_selector(make_resource):
    res = make_resource(lambda b: b.update(spec={"type": "ExternalName", "externalName": "db.example.com"}), kind="Service")
    assert list(checks.check_service_selector(res)) == []
