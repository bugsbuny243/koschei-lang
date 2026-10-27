"""Measure the same three workloads in Koschei, Python, Go and Rust.

    python3 bench/compare/run_v1.py --output docs/benchmarks

Every implementation must print the same line, or the run fails. Koschei is
measured twice: `ks run` (checked and run on sealed MIR by the Python host)
and the `ks build` native binary. The Go and Rust programs copy a list on
every append in the text workload, because Koschei lists are values.

Times are wall-clock medians of several runs on this machine, including
process start. They describe this machine and these workloads only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
PROGRAMS = HERE / "programs"
ROOT = HERE.parent.parent
WORKLOADS = {
    "fib": "recursive fib(24): about 150,000 calls",
    "loop": "300,000 iterations of Int arithmetic with overflow checks",
    "text": "3,000 value-semantics list appends, then join and split",
}


def _version(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "missing"
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _cpu() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _measure(command: list[str], runs: int, env: dict[str, str]) -> tuple[float, str]:
    samples: list[float] = []
    output = ""
    for _ in range(runs):
        start = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
        samples.append(time.perf_counter() - start)
        if completed.returncode != 0:
            raise RuntimeError(f"{command} failed: {completed.stderr}")
        output = completed.stdout.strip()
    return statistics.median(samples), output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)

    env = dict(os.environ, PYTHONPATH=str(ROOT))
    go = shutil.which("go")
    rustc = shutil.which("rustc")
    results: dict[str, dict[str, float]] = {}
    with tempfile.TemporaryDirectory(prefix="koschei-bench-") as workspace:
        build = Path(workspace)
        for name in WORKLOADS:
            commands: dict[str, list[str]] = {
                "koschei_run": [
                    sys.executable, "-m", "koschei", "run", "--max-steps", "100000000",
                    str(PROGRAMS / f"{name}.ks"),
                ],
                "python": [sys.executable, str(PROGRAMS / f"{name}.py")],
            }
            native = build / f"{name}_ks"
            subprocess.run(
                [sys.executable, "-m", "koschei", "build", str(PROGRAMS / f"{name}.ks"), "-o", str(native)],
                env=env, check=True, capture_output=True,
            )
            commands["koschei_native"] = [str(native)]
            if go:
                binary = build / f"{name}_go"
                subprocess.run([go, "build", "-o", str(binary), str(PROGRAMS / f"{name}.go")],
                               env=dict(env, GO111MODULE="off"), check=True, capture_output=True)
                commands["go"] = [str(binary)]
            if rustc:
                binary = build / f"{name}_rs"
                subprocess.run([rustc, "-O", "-o", str(binary), str(PROGRAMS / f"{name}.rs")],
                               check=True, capture_output=True)
                commands["rust"] = [str(binary)]
            outputs: dict[str, str] = {}
            results[name] = {}
            for label, command in commands.items():
                seconds, output = _measure(command, args.runs, env)
                results[name][label] = round(seconds * 1000, 1)
                outputs[label] = output
            if len(set(outputs.values())) != 1:
                raise RuntimeError(f"{name}: implementations disagree: {outputs}")

    metadata = {
        "cpu": _cpu(),
        "cores": os.cpu_count(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "go": _version([go, "version"]) if go else "missing",
        "rustc": _version([rustc, "--version"]) if rustc else "missing",
        "runs": args.runs,
        "unit": "milliseconds, wall-clock median including process start",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    raw = {"metadata": metadata, "workloads": WORKLOADS, "results": results}
    (args.output / "compare_v1.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    labels = ["koschei_run", "koschei_native", "python", "go", "rust"]
    lines = [
        "# Koschei Benchmark Dossier v1",
        "",
        "Generated by `python3 bench/compare/run_v1.py --output docs/benchmarks`; raw",
        "numbers in `compare_v1.json`. Every implementation printed the same result.",
        "",
        "| Workload | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for name in WORKLOADS:
        cells = [f"{results[name][label]:.1f}" if label in results[name] else "n/a" for label in labels]
        lines.append(f"| {name}: {WORKLOADS[name]} | " + " | ".join(cells) + " |")
    lines += ["", "Machine:", ""] + [f"- {key}: {value}" for key, value in metadata.items()] + [""]
    (args.output / "BENCHMARKS_V1.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
