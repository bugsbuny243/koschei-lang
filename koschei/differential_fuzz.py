"""Deterministic grammar-generated interpreter/native differential fuzzing."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = "koschei.differential-fuzz-report.v1"
_GENERATOR_VERSION = "koschei-differential-fuzz/v1"
_MIN_CASES = 1
_MAX_CASES = 256


class DifferentialFuzzError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedCase:
    case_id: str
    template: str
    source: str


def generate_cases(*, seed: int, case_count: int) -> list[GeneratedCase]:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise DifferentialFuzzError("seed must be an integer")
    if not isinstance(case_count, int) or isinstance(case_count, bool):
        raise DifferentialFuzzError("case_count must be an integer")
    if not _MIN_CASES <= case_count <= _MAX_CASES:
        raise DifferentialFuzzError(f"case_count must be {_MIN_CASES}..{_MAX_CASES}")

    rng = random.Random(seed)
    templates = (_arithmetic_case, _branch_case, _loop_case, _function_case)
    cases: list[GeneratedCase] = []
    for index in range(case_count):
        template_index = index % len(templates)
        name, source = templates[template_index](rng, index)
        cases.append(
            GeneratedCase(
                case_id=f"fuzz-{index:04d}",
                template=name,
                source=source,
            )
        )
    return cases


def run_differential_fuzz(
    *,
    seed: int,
    case_count: int,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    if shutil.which("go") is None:
        raise DifferentialFuzzError("Go toolchain is required for native differential fuzzing")
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise DifferentialFuzzError("timeout_seconds must be 1..120")

    generated = generate_cases(seed=seed, case_count=case_count)
    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="koschei-diff-fuzz-") as directory:
        root = Path(directory)
        for case in generated:
            source_path = root / f"{case.case_id}.ks"
            binary_path = root / case.case_id
            if os.name == "nt":
                binary_path = binary_path.with_suffix(".exe")
            source_raw = case.source.encode("utf-8")
            source_path.write_bytes(source_raw)

            interpreted = _run(
                [sys.executable, "-m", "koschei", "run", str(source_path)],
                timeout_seconds,
            )
            if interpreted.returncode != 0:
                raise DifferentialFuzzError(
                    f"{case.case_id} interpreter failed: {_short(interpreted.stderr)}"
                )
            if interpreted.stderr:
                raise DifferentialFuzzError(f"{case.case_id} interpreter emitted stderr")

            built = _run(
                [
                    sys.executable,
                    "-m",
                    "koschei",
                    "build",
                    str(source_path),
                    "--output",
                    str(binary_path),
                ],
                timeout_seconds,
            )
            if built.returncode != 0:
                raise DifferentialFuzzError(
                    f"{case.case_id} native build failed: {_short(built.stderr or built.stdout)}"
                )

            native = _run([str(binary_path)], timeout_seconds)
            if native.returncode != 0:
                raise DifferentialFuzzError(
                    f"{case.case_id} native execution failed: {_short(native.stderr)}"
                )
            if native.stderr:
                raise DifferentialFuzzError(f"{case.case_id} native execution emitted stderr")
            if interpreted.stdout != native.stdout:
                raise DifferentialFuzzError(
                    f"{case.case_id} interpreter/native stdout bytes differ"
                )

            records.append(
                {
                    "case_id": case.case_id,
                    "template": case.template,
                    "source_sha256": hashlib.sha256(source_raw).hexdigest(),
                    "output_sha256": hashlib.sha256(interpreted.stdout).hexdigest(),
                }
            )

    corpus_sha256 = _digest(records)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA,
        "state": "passed_differential_fuzz",
        "generator_version": _GENERATOR_VERSION,
        "seed": seed,
        "case_count": case_count,
        "cases": records,
        "corpus_sha256": corpus_sha256,
        "interpreter_native_byte_identical": True,
        "adversarial_capability_tests_observed": False,
        "production_integration_allowed": False,
    }
    return {**payload, "report_digest": _digest(payload)}


def write_differential_fuzz_report(payload: dict[str, object], destination: str | Path) -> None:
    path = Path(destination)
    if path.exists():
        raise DifferentialFuzzError(f"differential fuzz report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _run(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise DifferentialFuzzError(f"command timed out: {command[0]}") from error


def _arithmetic_case(rng: random.Random, index: int) -> tuple[str, str]:
    a, b, c = rng.randint(1, 30), rng.randint(1, 30), rng.randint(2, 6)
    return (
        "arithmetic",
        f"fn main() {{\n    let a = {a}\n    let b = {b}\n    let c = {c}\n"
        f"    println(a + b)\n    println(a * b)\n    println((a + b) * c - {index % 5})\n}}\n",
    )


def _branch_case(rng: random.Random, index: int) -> tuple[str, str]:
    a, b = rng.randint(0, 50), rng.randint(0, 50)
    return (
        "branch",
        f"fn main() {{\n    let a = {a}\n    let b = {b}\n"
        "    if a > b {\n        println(a - b)\n    } else {\n        println(b - a)\n    }\n"
        f"    if a == b {{\n        println({index})\n    }} else {{\n        println(a + b)\n    }}\n}}\n",
    )


def _loop_case(rng: random.Random, index: int) -> tuple[str, str]:
    start, step, loops = rng.randint(0, 15), rng.randint(1, 5), rng.randint(2, 9)
    return (
        "loop",
        f"fn main() {{\n    let mut value = {start}\n    let mut remaining = {loops}\n"
        f"    while remaining > 0 {{\n        value = value + {step}\n        remaining = remaining - 1\n    }}\n"
        f"    println(value)\n    println(remaining + {index % 3})\n}}\n",
    )


def _function_case(rng: random.Random, index: int) -> tuple[str, str]:
    a, b, factor = rng.randint(1, 20), rng.randint(1, 20), rng.randint(2, 5)
    return (
        "function",
        f"fn mix(a: Int, b: Int) -> Int {{\n    return a * {factor} + b\n}}\n\n"
        f"fn main() {{\n    println(mix({a}, {b}))\n    println(mix({b}, {index % 7 + 1}))\n}}\n",
    )


def _short(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip().replace("\n", " ")[:240]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


__all__ = [
    "DifferentialFuzzError",
    "GeneratedCase",
    "generate_cases",
    "run_differential_fuzz",
    "write_differential_fuzz_report",
]
