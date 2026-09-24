#!/usr/bin/env python3
"""Seal evidence that two independent candidate artifacts are byte-identical."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "koschei.reproducible-artifact-receipt/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_receipt(first: Path, second: Path, source_commit: str) -> dict[str, object]:
    commit = source_commit.lower()
    if _HEX40.fullmatch(commit) is None:
        raise ValueError("source commit must be a full lowercase Git SHA-1")
    if not first.is_file() or not second.is_file():
        raise ValueError("both reproducibility artifacts must exist")
    first_size = first.stat().st_size
    second_size = second.stat().st_size
    first_sha = _sha256(first)
    second_sha = _sha256(second)
    if first_size != second_size or first_sha != second_sha:
        raise ValueError(
            "independent artifacts are not byte-identical: "
            f"first={first_sha}/{first_size} second={second_sha}/{second_size}"
        )
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "source_commit": commit,
        "artifact_sha256": first_sha,
        "artifact_bytes": first_size,
        "independent_builds": 2,
        "byte_identical": True,
        "authority": False,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = build_receipt(args.first, args.second, args.source_commit)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"reproducibility receipt refused: {exc}") from exc
    if args.output.exists():
        raise SystemExit(f"reproducibility receipt refused: output exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
