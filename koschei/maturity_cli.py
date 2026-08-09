"""CLI adapter for the Koschei language maturity evidence gate."""

from __future__ import annotations

import argparse
import sys

from .maturity import (
    TARGET_REQUIREMENTS,
    evaluate_maturity,
    load_maturity_evidence,
    render_maturity_report,
)


def add_maturity_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "maturity",
        help="Evaluate evidence for a Koschei maturity target",
        description=(
            "Evaluate strict Koschei maturity evidence against incubation, reference, "
            "or production requirements. Protected reproducibility checks require "
            "attested koschei.maturity-evidence.v2 input."
        ),
    )
    parser.add_argument(
        "--evidence",
        required=True,
        help="Path to Koschei maturity evidence JSON (v1 or attested v2)",
    )
    parser.add_argument(
        "--target",
        choices=tuple(TARGET_REQUIREMENTS),
        default="incubation",
        help="Maturity target to evaluate",
    )


def command_maturity(args: argparse.Namespace) -> int:
    try:
        evidence = load_maturity_evidence(args.evidence)
        report = evaluate_maturity(evidence, args.target)
    except (OSError, ValueError) as error:
        print(f"ks maturity: {error}", file=sys.stderr)
        return 2

    print(render_maturity_report(report), end="")
    return 0 if report.ready else 3
