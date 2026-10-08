"""Command-line entry point.

Exit codes:
    0  no critical findings (and no warnings when --strict is used)
    1  at least one critical finding (or any finding with --strict)
    2  usage or manifest parsing error
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from k8s_validator import __version__
from k8s_validator.checks import validate
from k8s_validator.loader import ManifestError, load_resources
from k8s_validator.models import Severity
from k8s_validator.reporter import JsonReporter, TextReporter

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k8s-validator",
        description="Validate Kubernetes Deployment, StatefulSet, DaemonSet and Service manifests.",
    )
    parser.add_argument(
        "path", type=Path, nargs="?", default=Path("."),
        help="Directory (scanned recursively) or single YAML file (default: current directory)",
    )
    parser.add_argument("-o", "--output", choices=("text", "json"), default="text", help="Output format (default: text)")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures (exit 1)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors in text output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        resources = load_resources(args.path)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    findings = validate(resources)

    if args.output == "json":
        JsonReporter().report(resources, findings)
    else:
        TextReporter(color=False if args.no_color else None).report(resources, findings)

    has_critical = any(f.severity == Severity.CRITICAL for f in findings)
    if has_critical or (args.strict and findings):
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
