#!/usr/bin/env python3
"""Measure exact train/validation exports with the pinned Qwen397B tokenizer.

The sealed test split is never opened by this tool. External dependency:
Transformers. This remains outside the stdlib-only Koschei compiler dependency
graph.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from koschei.native_intelligence_qwen397b_profile_v1 import canonical_qwen397b_koschei_profile_v1
from koschei.native_intelligence_qwen397b_token_profile_v1 import (
    FORMATTING_VERSION_V1,
    seal_qwen397b_token_profile_v1,
)
from koschei.native_intelligence_qwen397b_training_plan_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_training_export_v1 import (
    load_native_training_export_manifest_v1,
    verify_native_training_export_v1,
)
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1

SYSTEM_TEXT = (
    "You are Koschei native intelligence. Learn the sealed Koschei language and "
    "Universe decision boundary. Return the canonical target only; never invent authority."
)


def _load_tokenizer():
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise RuntimeError(
            "qwen397b token profile requires transformers outside the compiler core"
        ) from error
    return AutoTokenizer.from_pretrained(
        CANONICAL_BASE_MODEL_V1,
        revision=CANONICAL_QWEN397B_REVISION_V1,
        use_fast=True,
    )


def _messages(row: dict[str, object]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_TEXT},
        {
            "role": "user",
            "content": f"TASK:\n{row['task']}\nINPUT:\n{row['input']}",
        },
        {"role": "assistant", "content": str(row["target"])},
    ]


def _measure(path: Path, tokenizer, max_length: int) -> tuple[int, int, int, int]:
    examples = 0
    bounded_tokens = 0
    bounded_max = 0
    truncated = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            ids = tokenizer.apply_chat_template(
                _messages(row),
                tokenize=True,
                add_generation_prompt=False,
            )
            length = len(ids)
            examples += 1
            if length > max_length:
                truncated += 1
            bounded = min(length, max_length)
            bounded_tokens += bounded
            bounded_max = max(bounded_max, bounded)
    return examples, bounded_tokens, bounded_max, truncated


def run_profile(directory: Path):
    manifest = load_native_training_export_manifest_v1(directory / "manifest.json")
    verify_native_training_export_v1(manifest, directory)
    profile = canonical_qwen397b_koschei_profile_v1()
    tokenizer = _load_tokenizer()

    # Deliberately touch only train and validation. The sealed test file is not a
    # tokenizer/trainer input at this stage.
    train = _measure(directory / "train.jsonl", tokenizer, profile.max_sequence_length)
    validation = _measure(
        directory / "validation.jsonl",
        tokenizer,
        profile.max_sequence_length,
    )
    return seal_qwen397b_token_profile_v1(
        manifest,
        profile,
        tokenizer_revision=CANONICAL_QWEN397B_REVISION_V1,
        formatting_version=FORMATTING_VERSION_V1,
        train_examples=train[0],
        validation_examples=validation[0],
        train_tokens=train[1],
        validation_tokens=validation[1],
        max_train_tokens=train[2],
        max_validation_tokens=validation[2],
        train_truncated_examples=train[3],
        validation_truncated_examples=validation[3],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile Koschei train/validation data with the pinned Qwen397B tokenizer"
    )
    parser.add_argument("directory")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        evidence = run_profile(Path(args.directory))
        payload = json.dumps(asdict(evidence), sort_keys=True, indent=2) + "\n"
        if args.output:
            destination = Path(args.output)
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (RuntimeError, ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"qwen397b-token-profile: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
