#!/usr/bin/env python3
"""Measure the exact Koschei Qwen397B train/validation export before GPU compute.

External dependency: transformers. The compiler core remains stdlib-only.
The sealed test split is verified as part of export integrity but is never read
or tokenized by this trainer preflight.
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

from koschei.native_intelligence_qwen397b_base_spec_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_qwen397b_profile_v1 import canonical_qwen397b_koschei_profile_v1
from koschei.native_intelligence_qwen397b_sft_format_v1 import (
    FORMATTING_VERSION_V1,
    canonical_qwen397b_messages_v1,
)
from koschei.native_intelligence_qwen397b_token_profile_v1 import seal_qwen397b_token_profile_v1
from koschei.native_intelligence_training_export_v1 import (
    load_native_training_export_manifest_v1,
    verify_native_training_export_v1,
)
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1


def _load_tokenizer():
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise RuntimeError(
            "qwen397b token preflight requires transformers outside the compiler core"
        ) from error
    return AutoTokenizer.from_pretrained(
        CANONICAL_BASE_MODEL_V1,
        revision=CANONICAL_QWEN397B_REVISION_V1,
        trust_remote_code=False,
    )


def _rows(path: Path, expected_split: str):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"invalid JSONL at {path.name}:{line_number}") from error
            if row.get("split") != expected_split:
                raise RuntimeError(
                    f"split-role mismatch at {path.name}:{line_number}: {row.get('split')!r}"
                )
            yield row


def _measure(tokenizer, release: Path, split: str) -> tuple[int, int, int, int]:
    count = 0
    total = 0
    maximum = 0
    over_limit = 0
    limit = canonical_qwen397b_koschei_profile_v1().max_sequence_length
    for row in _rows(release / f"{split}.jsonl", split):
        messages = canonical_qwen397b_messages_v1(row)
        token_ids = tokenizer.apply_chat_template(
            list(messages),
            tokenize=True,
            add_generation_prompt=False,
        )
        length = len(token_ids)
        count += 1
        total += length
        maximum = max(maximum, length)
        if length > limit:
            over_limit += 1
    if count < 1:
        raise RuntimeError(f"empty trainer split: {split}")
    return count, total, maximum, over_limit


def run_token_preflight(release_directory: str | Path):
    release = Path(release_directory).resolve()
    manifest = load_native_training_export_manifest_v1(release / "manifest.json")
    verify_native_training_export_v1(manifest, release)
    tokenizer = _load_tokenizer()
    train_count, train_tokens, max_train, train_over = _measure(tokenizer, release, "train")
    validation_count, validation_tokens, max_validation, validation_over = _measure(
        tokenizer,
        release,
        "validation",
    )
    if train_over or validation_over:
        raise RuntimeError(
            "Qwen397B zero-truncation preflight failed: "
            f"train_over={train_over}, validation_over={validation_over}, "
            f"max_train={max_train}, max_validation={max_validation}"
        )
    profile = canonical_qwen397b_koschei_profile_v1()
    return seal_qwen397b_token_profile_v1(
        manifest,
        profile,
        tokenizer_revision=CANONICAL_QWEN397B_REVISION_V1,
        formatting_version=FORMATTING_VERSION_V1,
        train_examples=train_count,
        validation_examples=validation_count,
        train_tokens=train_tokens,
        validation_tokens=validation_tokens,
        max_train_tokens=max_train,
        max_validation_tokens=max_validation,
        train_truncated_examples=0,
        validation_truncated_examples=0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and tokenize the sealed Qwen397B Koschei training export"
    )
    parser.add_argument("release_directory")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        evidence = run_token_preflight(args.release_directory)
        payload = json.dumps(asdict(evidence), sort_keys=True, indent=2) + "\n"
        if args.output:
            destination = Path(args.output)
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f"qwen397b-token-preflight: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
