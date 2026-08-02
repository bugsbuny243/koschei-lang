"""Public CLI surface for sealed foreign-contract validation."""

from __future__ import annotations

import argparse
import json
import sys

from .foreign_contract import ForeignContractError, load_foreign_contract


def add_foreign_parser(subcommands: argparse._SubParsersAction) -> None:
    foreign = subcommands.add_parser(
        "foreign",
        help="Validate sealed, capability-free foreign language contracts",
        description=(
            "Validate a Koschei Foreign Contract v1 without loading or executing "
            "the foreign artifact."
        ),
    )
    commands = foreign.add_subparsers(dest="foreign_command", required=True)

    validate = commands.add_parser(
        "validate",
        help="Validate schema, types, budgets, artifact path, and SHA-256 identity",
    )
    validate.add_argument("contract", help="Path to a *.foreign.json contract")
    validate.add_argument("--json", action="store_true", help="Emit stable JSON")

    fingerprint = commands.add_parser(
        "fingerprint",
        help="Print the deterministic contract fingerprint after full validation",
    )
    fingerprint.add_argument("contract", help="Path to a *.foreign.json contract")


def command_foreign(args: argparse.Namespace) -> int:
    try:
        contract = load_foreign_contract(args.contract)
    except ForeignContractError as error:
        if args.foreign_command == "validate" and getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": error.code,
                        "message": error.message,
                        "source": str(args.contract),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1

    if args.foreign_command == "fingerprint":
        print(contract.fingerprint)
        return 0

    if getattr(args, "json", False):
        print(json.dumps(contract.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0

    locale = getattr(args, "lang", "en")
    if locale == "tr":
        print(
            "KOSCHEI FOREIGN: PASS "
            f"({contract.module}, {contract.language}/{contract.isolation}, "
            f"{contract.functions} fonksiyon, artifact doğrulandı)"
        )
    else:
        print(
            "KOSCHEI FOREIGN: PASS "
            f"({contract.module}, {contract.language}/{contract.isolation}, "
            f"{contract.functions} functions, artifact verified)"
        )
    print(f"FINGERPRINT: {contract.fingerprint}")
    return 0
