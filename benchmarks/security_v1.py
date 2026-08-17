from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from dataclasses import dataclass
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koschei.capabilities import analyze, to_dict
from koschei.parser import parse
from koschei.semantic import check

SCHEMA = "koschei.security-benchmark/v1"


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    source: str
    expected_domains: tuple[str, ...]


CASES: tuple[Case, ...] = (
    Case(
        name="pure",
        source='fn main() { println("hello") }',
        expected_domains=(),
    ),
    Case(
        name="disk_read_only",
        source=(
            'fn main(caps: SystemCaps) { '
            'let disk = caps.disk.allow_read_only("/etc/app/") '
            'let content = disk.read("/etc/app/config.json") or "" '
            'println(content) '
            '}'
        ),
        expected_domains=("disk",),
    ),
    Case(
        name="network",
        source=(
            'fn main(caps: SystemCaps) { '
            'let api = caps.net.allow("https://api.example") '
            '}'
        ),
        expected_domains=("net",),
    ),
    Case(
        name="environment",
        source=(
            'fn main(caps: SystemCaps) { '
            'let home = caps.env.allow("HOME") '
            'let value = home.get() or "" '
            'println(value) '
            '}'
        ),
        expected_domains=("env",),
    ),
    Case(
        name="dynamic_disk_scope",
        source=(
            'fn main(caps: SystemCaps) { '
            'let path = "/tmp/runtime" '
            'let disk = caps.disk.allow(path) '
            '}'
        ),
        expected_domains=("disk",),
    ),
)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def measure_case(case: Case) -> dict[str, object]:
    program = parse(case.source)
    check(program)
    manifest = analyze(program)
    payload = to_dict(manifest, f"benchmark:{case.name}")
    observed_domains = sorted({grant["domain"] for grant in payload["grants"]})
    expected_domains = sorted(case.expected_domains)
    if observed_domains != expected_domains:
        raise AssertionError(
            f"benchmark case {case.name!r} drifted: expected domains "
            f"{expected_domains!r}, observed {observed_domains!r}"
        )
    return {
        "name": case.name,
        "source_sha256": _sha256_text(case.source),
        "expected_domains": expected_domains,
        "observed_domains": observed_domains,
        "grant_count": len(payload["grants"]),
        "exact": bool(payload["exact"]),
        "holder_functions": sorted(payload.get("holder_functions", [])),
        "native_manifest": payload,
    }


def build_report(cases: Iterable[Case] = CASES) -> dict[str, object]:
    measured = [measure_case(case) for case in cases]
    return {
        "schema": SCHEMA,
        "language": "koschei",
        "measurement_mode": "native",
        "claim_policy": {
            "cross_language_claims_enabled": False,
            "reason": "No cross-language adapter is admitted until it measures the same semantic question reproducibly.",
        },
        "cases": measured,
    }


def render_text(report: dict[str, object]) -> str:
    lines = ["Koschei security benchmark v1"]
    for case in report["cases"]:
        domains = ",".join(case["observed_domains"]) or "none"
        lines.append(
            f"- {case['name']}: domains={domains}; grants={case['grant_count']}; exact={case['exact']}"
        )
    lines.append("cross-language claims: disabled until equivalent adapters exist")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
