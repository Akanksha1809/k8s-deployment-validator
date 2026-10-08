# k8s-deployment-validator

[![CI](https://github.com/Akanksha1809/k8s-deployment-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/Akanksha1809/k8s-deployment-validator/actions/workflows/ci.yml)

A small, dependency-light CLI that statically validates Kubernetes manifests against production best practices **before** they reach a cluster. Point it at a directory of YAML files and it reports security and reliability problems in `Deployment`, `StatefulSet`, `DaemonSet` and `Service` resources, exiting non-zero when anything critical is found, so it drops straight into a CI pipeline.

- No cluster access required, purely static analysis
- Single runtime dependency (`PyYAML`)
- Human-readable colored output or machine-readable JSON
- Ships as a Python package and a non-root Docker image

---

## Checks

| Rule               | Applies to                         | Severity     | What it detects |
|--------------------|------------------------------------|--------------|-----------------|
| `image-tag`        | Deployment, StatefulSet, DaemonSet | **CRITICAL** | Image uses `:latest` or has no tag (implicit `latest`). Digest-pinned images (`@sha256:…`) pass. Includes init containers. |
| `privileged`       | Deployment, StatefulSet, DaemonSet | **CRITICAL** | `securityContext.privileged: true` on any container. |
| `run-as-root`      | Deployment, StatefulSet, DaemonSet | **CRITICAL** | Effective `runAsUser: 0` (container setting overrides pod setting). |
| `run-as-root`      | Deployment, StatefulSet, DaemonSet | WARNING      | Non-root not enforced: neither `runAsNonRoot: true` nor a `runAsUser` is set, so the image's default user (often root) is used. |
| `resources`        | Deployment, StatefulSet, DaemonSet | WARNING      | Any of `requests.cpu`, `requests.memory`, `limits.cpu`, `limits.memory` is missing. |
| `probes`           | Deployment, StatefulSet, DaemonSet | WARNING      | Missing `readinessProbe` and/or `livenessProbe`. |
| `replicas`         | Deployment, StatefulSet            | WARNING      | `spec.replicas` not set (defaults to 1). |
| `labels`           | All supported kinds                | WARNING      | Missing any of the [recommended labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/): `app.kubernetes.io/name`, `app.kubernetes.io/instance`, `app.kubernetes.io/version`. |
| `service-selector` | Service                            | WARNING      | Service (other than `ExternalName`) has no selector. |

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | No critical findings (warnings allowed unless `--strict`) |
| `1`  | At least one critical finding, or any finding with `--strict` |
| `2`  | Usage error, missing path, or unparseable YAML |

---

## Architecture

```
            ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
  path ───▶ │  loader.py   │───▶ │   checks.py   │───▶ │ reporter.py  │───▶ stdout
            │ find + parse │     │ rule registry │     │ text / json  │
            └──────────────┘     └───────────────┘     └──────────────┘
                        shared types: models.py (Resource, Finding, Severity)
                        orchestration + exit code: cli.py
```

```
k8s-deployment-validator/
├── k8s_validator/
│   ├── cli.py         # argparse entry point, exit-code policy
│   ├── loader.py      # recursive YAML discovery, multi-doc + kind: List support
│   ├── checks.py      # one function per rule + CHECKS registry
│   ├── reporter.py    # colored text and JSON output
│   └── models.py      # Resource, Finding, Severity dataclasses
├── tests/             # pytest suite (checks, loader, CLI)
├── examples/
│   ├── good/          # compliant manifests: pass with --strict
│   └── bad/           # intentionally broken manifests: exit 1
├── .github/workflows/ci.yml
├── Dockerfile
└── pyproject.toml
```

**Design notes**

- **Loader** walks the path recursively for `*.yaml` / `*.yml`, parses every document with `yaml.safe_load_all`, flattens `kind: List`, and keeps only supported kinds. Other kinds (ConfigMap, Ingress, …) are skipped.
- **Checks** are plain functions `(Resource) -> Iterable[Finding]`. The `CHECKS` registry maps each function to the kinds it applies to. To add a rule, write a function and add one line to the registry.
- **Reporter** groups findings per resource, sorts critical first, and prints a summary. Color is enabled automatically on a TTY and respects `NO_COLOR` / `FORCE_COLOR`.
- **CLI** owns the exit-code policy, keeping the rule logic free of process concerns and easy to unit-test.

---

## Usage

### Install (Python 3.12+)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run

```bash
k8s-validator ./manifests                 # scan a directory recursively
k8s-validator deploy.yaml                 # scan a single file
k8s-validator ./manifests --strict        # fail on warnings too
k8s-validator ./manifests -o json         # JSON for tooling
python -m k8s_validator ./manifests       # without the console script
```

```
usage: k8s-validator [-h] [-o {text,json}] [--strict] [--no-color] [--version] [path]
```

`path` defaults to the current directory.

### Docker

```bash
docker build -t k8s-deployment-validator .
docker run --rm -v "$PWD/examples/bad:/manifests:ro" k8s-deployment-validator
docker run --rm -v "$PWD/examples/good:/manifests:ro" k8s-deployment-validator --strict
```

The image is multi-stage, based on `python:3.12-slim`, and runs as UID `10001`. Its working directory is `/manifests`, which is scanned by default; any arguments are passed to the CLI.

---

## Examples

### Failing manifests

```console
$ k8s-validator examples/bad
WARN  StatefulSet/redis  examples/bad/incomplete-statefulset.yaml
      WARNING  labels           Missing recommended labels: app.kubernetes.io/instance, app.kubernetes.io/version
      WARNING  probes           [redis] Missing readinessProbe
      WARNING  replicas         spec.replicas is not set (defaults to 1, no redundancy)
      WARNING  resources        [redis] Missing resource settings: limits.cpu, limits.memory
      WARNING  run-as-root      [redis] Non-root not enforced; set runAsNonRoot: true or a non-zero runAsUser
FAIL  Deployment/api  examples/bad/insecure-deployment.yaml
      CRITICAL image-tag        [api] Image 'mycompany/api:latest' uses the 'latest' tag; pin a version or digest
      CRITICAL image-tag        [sidecar] Image 'busybox' has no tag (implicit :latest); pin a version or digest
      CRITICAL privileged       [api] Container runs in privileged mode
      CRITICAL run-as-root      [api] Container runs as root (runAsUser: 0)
      WARNING  labels           Missing recommended labels: app.kubernetes.io/name, app.kubernetes.io/instance, app.kubernetes.io/version
      ...
FAIL  DaemonSet/node-exporter  examples/bad/node-exporter-daemonset.yaml
      CRITICAL image-tag        [setup] Image 'alpine' has no tag (implicit :latest); pin a version or digest
      CRITICAL run-as-root      [setup] Container runs as root (runAsUser: 0)
      CRITICAL run-as-root      [node-exporter] Container runs as root (runAsUser: 0)

------------------------------------------------------------------------
Scanned 4 resource(s): 7 critical, 14 warning(s)
$ echo $?
1
```

### Passing manifests

```console
$ k8s-validator examples/good --strict
PASS  DaemonSet/log-agent  examples/good/log-agent-daemonset.yaml
PASS  StatefulSet/postgres  examples/good/postgres-statefulset.yaml
PASS  Deployment/web  examples/good/web-deployment.yaml
PASS  Service/web  examples/good/web-deployment.yaml

------------------------------------------------------------------------
Scanned 4 resource(s): 0 critical, 0 warning(s)
$ echo $?
0
```

### JSON output

```bash
k8s-validator examples/bad -o json | jq '.findings[] | select(.severity=="CRITICAL")'
```

```json
{
  "rule": "privileged",
  "severity": "CRITICAL",
  "message": "Container runs in privileged mode",
  "kind": "Deployment",
  "name": "api",
  "namespace": "default",
  "file": "examples/bad/insecure-deployment.yaml",
  "container": "api"
}
```

---

## Testing

```bash
pytest -v
```

The suite covers each rule (positive and negative cases, pod- vs container-level security context precedence, image reference parsing including registry ports and digests), the loader (multi-document files, `kind: List`, recursive discovery, invalid YAML), and the CLI end to end against `examples/` (exit codes, `--strict`, JSON output).

---

## CI/CD workflow

`.github/workflows/ci.yml` runs on **every push and pull request** with three jobs:

```
          ┌─────────────┐
          │    test     │  pytest on Python 3.12
          └──────┬──────┘
         ┌───────┴────────┐
┌────────▼───────┐ ┌──────▼──────┐
│    validate    │ │   docker    │
│ good → exit 0  │ │ build image │
│ bad  → exit 1  │ │ run on good │
└────────────────┘ └─────────────┘
```

1. **test**: installs the package with dev extras and runs `pytest`.
2. **validate**: installs the CLI, asserts `examples/good` passes with `--strict`, and asserts `examples/bad` exits with **exactly** `1`. This proves the tool still catches what it should, not just that it runs.
3. **docker**: builds the image and validates `examples/good` inside the container to confirm the shipped artifact works.

`validate` and `docker` only run once `test` has passed.

### Using it in your own pipeline

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install git+https://github.com/Akanksha1809/k8s-deployment-validator.git
- run: k8s-validator k8s/
```

---

## Limitations

- Validates raw manifests only. Render Helm charts (`helm template`) or Kustomize overlays (`kustomize build`) to a directory first.
- `run-as-root` cannot inspect the image's `USER` directive; it relies on what the manifest enforces.
- Rule severities and recommended labels are fixed in code (`checks.py`) to keep the tool simple.

## License

MIT
