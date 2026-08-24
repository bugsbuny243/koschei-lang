#!/usr/bin/env python3
"""Resolve and seal the pinned Qwen3.5-397B-A17B base artifact before training.

External dependency: huggingface-hub. This tool intentionally lives outside the
stdlib-only compiler package dependency graph.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from koschei.native_intelligence_qwen397b_preflight_v1 import seal_qwen397b_preflight_v1
from koschei.native_intelligence_qwen397b_training_plan_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1


def _load_hub():
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as error:
        raise RuntimeError(
            "qwen397b preflight requires huggingface-hub; install it outside the compiler core"
        ) from error
    return HfApi, hf_hub_download


def run_preflight():
    HfApi, hf_hub_download = _load_hub()
    api = HfApi()
    info = api.model_info(
        CANONICAL_BASE_MODEL_V1,
        revision=CANONICAL_QWEN397B_REVISION_V1,
        files_metadata=True,
    )
    files = tuple(info.siblings or ())
    shards = tuple(
        sorted(
            row
            for row in files
            if row.rfilename.startswith("model.safetensors-")
            and row.rfilename.endswith(".safetensors")
        )
    )
    weight_bytes = sum(int(getattr(row, "size", 0) or 0) for row in shards)

    config_path = hf_hub_download(
        CANONICAL_BASE_MODEL_V1,
        "config.json",
        revision=CANONICAL_QWEN397B_REVISION_V1,
    )
    index_path = hf_hub_download(
        CANONICAL_BASE_MODEL_V1,
        "model.safetensors.index.json",
        revision=CANONICAL_QWEN397B_REVISION_V1,
    )
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    index_sha256 = hashlib.sha256(Path(index_path).read_bytes()).hexdigest()
    text = config["text_config"]

    return seal_qwen397b_preflight_v1(
        repo_id=CANONICAL_BASE_MODEL_V1,
        requested_revision=CANONICAL_QWEN397B_REVISION_V1,
        resolved_revision=str(info.sha),
        shard_count=len(shards),
        weight_bytes=weight_bytes,
        safetensors_index_sha256=index_sha256,
        architecture=config["model_type"],
        text_hidden_size=text["hidden_size"],
        text_layers=text["num_hidden_layers"],
        experts=text["num_experts"],
        experts_per_token=text["num_experts_per_tok"],
        native_context=text["max_position_embeddings"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and seal the pinned Qwen3.5-397B-A17B base artifact"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        evidence = run_preflight()
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
        print(f"qwen397b-preflight: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
