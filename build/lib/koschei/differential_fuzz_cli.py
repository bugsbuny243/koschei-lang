from __future__ import annotations

import argparse
import json

from .differential_fuzz import (
    DifferentialFuzzError,
    run_differential_fuzz,
    write_differential_fuzz_report,
)


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--cases", type=int, default=16)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--output", required=True)
    parser.add_argument("--json", action="store_true")


def add_differential_fuzz_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "differential-fuzz",
        help="Run deterministic grammar-generated interpreter/native differential fuzzing",
    )
    _add_arguments(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-differential-fuzz",
        description="Run deterministic grammar-generated interpreter/native differential fuzzing",
    )
    _add_arguments(parser)
    return parser


def command_differential_fuzz(args: argparse.Namespace) -> int:
    try:
        report = run_differential_fuzz(
            seed=args.seed,
            case_count=args.cases,
            timeout_seconds=args.timeout_seconds,
        )
        write_differential_fuzz_report(report, args.output)
    except (DifferentialFuzzError, OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"KS DIFFERENTIAL FUZZ: BLOCKED — {error}")
        return 3

    result = {
        "ok": True,
        "path": args.output,
        "seed": report["seed"],
        "case_count": report["case_count"],
        "corpus_sha256": report["corpus_sha256"],
        "report_digest": report["report_digest"],
        "adversarial_capability_tests_observed": False,
        "production_integration_allowed": False,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("KOSCHEI DIFFERENTIAL FUZZ: PASS")
        print(f"CASES: {report['case_count']}")
        print(f"SEED: {report['seed']}")
        print(f"CORPUS SHA256: {report['corpus_sha256']}")
        print(f"REPORT SHA256: {report['report_digest']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return command_differential_fuzz(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
