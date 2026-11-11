#!/usr/bin/env python3
"""Publish one sealed Koschei Qwen397B train+validation mirror to a fresh HF repo.

The target dataset repository must not already exist. That rule prevents hidden
history from containing a test split. Only train.jsonl and validation.jsonl are
uploaded. The script then downloads both files from the exact new commit,
byte-verifies them, and seals a trainer-mirror receipt.

External dependency: huggingface-hub. Requires HF_TOKEN with dataset write access.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from koschei.native_intelligence_qwen397b_trainer_mirror_v1 import (
    seal_qwen397b_trainer_mirror_v1,
)
from koschei.native_intelligence_training_export_v1 import (
    load_native_training_export_manifest_v1,
    verify_native_training_export_v1,
)


def _load_hub():
    try:
        from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
        from huggingface_hub.errors import RepositoryNotFoundError
    except ImportError as error:
        raise RuntimeError(
            "trainer mirror publisher requires huggingface-hub outside the compiler core"
        ) from error
    return CommitOperationAdd, HfApi, hf_hub_download, RepositoryNotFoundError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish(release_directory: str | Path, dataset_repo_id: str):
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required for private trainer mirror publication")
    release = Path(release_directory).resolve()
    manifest = load_native_training_export_manifest_v1(release / "manifest.json")
    verify_native_training_export_v1(manifest, release)
    CommitOperationAdd, HfApi, hf_hub_download, RepositoryNotFoundError = _load_hub()
    api = HfApi(token=token)

    try:
        api.repo_info(dataset_repo_id, repo_type="dataset")
    except RepositoryNotFoundError:
        pass
    else:
        raise RuntimeError(
            "trainer mirror dataset repo already exists; use a fresh repo per sealed corpus release"
        )

    api.create_repo(
        dataset_repo_id,
        repo_type="dataset",
        private=True,
        exist_ok=False,
    )
    operations = [
        CommitOperationAdd(
            path_in_repo="train.jsonl",
            path_or_fileobj=str(release / "train.jsonl"),
        ),
        CommitOperationAdd(
            path_in_repo="validation.jsonl",
            path_or_fileobj=str(release / "validation.jsonl"),
        ),
    ]
    commit = api.create_commit(
        repo_id=dataset_repo_id,
        repo_type="dataset",
        operations=operations,
        commit_message=f"Koschei trainer mirror {manifest.digest[:16]}",
    )
    revision = str(commit.oid)
    if len(revision) != 40:
        raise RuntimeError("HF trainer mirror did not return a full commit revision")

    remote_files = set(
        api.list_repo_files(
            repo_id=dataset_repo_id,
            repo_type="dataset",
            revision=revision,
        )
    )
    forbidden = {name for name in remote_files if "test" in name.lower()}
    if forbidden:
        raise RuntimeError(f"trainer mirror unexpectedly exposes test-like files: {sorted(forbidden)}")
    required = {"train.jsonl", "validation.jsonl"}
    if not required.issubset(remote_files):
        raise RuntimeError("trainer mirror is missing train or validation bytes")

    rows = {row.split: row for row in manifest.files}
    observed = {}
    for split in ("train", "validation"):
        remote_path = Path(
            hf_hub_download(
                dataset_repo_id,
                f"{split}.jsonl",
                repo_type="dataset",
                revision=revision,
                token=token,
            )
        )
        observed[split] = _sha256(remote_path)
        if observed[split] != rows[split].sha256:
            raise RuntimeError(f"trainer mirror roundtrip digest mismatch: {split}")

    roundtrip_payload = json.dumps(
        {
            "provider": "huggingface-hub",
            "repo_id": dataset_repo_id,
            "revision": revision,
            "training_export_digest": manifest.digest,
            "train_sha256": observed["train"],
            "validation_sha256": observed["validation"],
            "test_exposed": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    roundtrip_digest = hashlib.sha256(
        b"koschei.qwen397b-trainer-mirror-roundtrip/v1\x00" + roundtrip_payload
    ).hexdigest()
    return seal_qwen397b_trainer_mirror_v1(
        manifest,
        dataset_repo_id=dataset_repo_id,
        resolved_revision=revision,
        roundtrip_evidence_digest=roundtrip_digest,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish a fresh private train+validation-only HF mirror"
    )
    parser.add_argument("release_directory")
    parser.add_argument("--dataset-repo", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        receipt = publish(args.release_directory, args.dataset_repo)
        payload = json.dumps(asdict(receipt), sort_keys=True, indent=2) + "\n"
        if args.output:
            destination = Path(args.output)
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f"qwen397b-trainer-mirror: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
