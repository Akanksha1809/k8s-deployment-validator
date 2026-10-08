import pytest

from k8s_validator.loader import ManifestError, find_manifest_files, load_resources, parse_file


def test_multi_document_and_unsupported_kinds(tmp_path):
    manifest = tmp_path / "app.yaml"
    manifest.write_text(
        """
apiVersion: v1
kind: ConfigMap
metadata: {name: cfg}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: web, namespace: prod}
---
apiVersion: v1
kind: Service
metadata: {name: web}
---
"""
    )
    resources = parse_file(manifest)
    assert [(r.kind, r.name, r.namespace) for r in resources] == [
        ("Deployment", "web", "prod"),
        ("Service", "web", "default"),
    ]


def test_list_kind_is_flattened(tmp_path):
    manifest = tmp_path / "list.yml"
    manifest.write_text(
        """
apiVersion: v1
kind: List
items:
  - {apiVersion: apps/v1, kind: DaemonSet, metadata: {name: ds}}
  - {apiVersion: apps/v1, kind: StatefulSet, metadata: {name: sts}}
"""
    )
    assert [r.kind for r in parse_file(manifest)] == ["DaemonSet", "StatefulSet"]


def test_recursive_discovery_ignores_non_yaml(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.yaml").write_text("kind: Service\nmetadata: {name: a}\n")
    (tmp_path / "nested" / "b.yml").write_text("kind: Service\nmetadata: {name: b}\n")
    (tmp_path / "README.md").write_text("# not yaml")

    assert [p.name for p in find_manifest_files(tmp_path)] == ["a.yaml", "b.yml"]
    assert [r.name for r in load_resources(tmp_path)] == ["a", "b"]


def test_invalid_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("kind: Deployment\nmetadata: [unclosed\n")
    with pytest.raises(ManifestError):
        parse_file(bad)


def test_missing_path_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_resources(tmp_path / "does-not-exist")
