"""Export a provenance-pinned Koschei language foundation corpus for Sentinel.

The exporter never reads selected training documents from the mutable working tree.
It enumerates and reads blobs from one exact Git commit so the recorded provenance
cannot silently describe dirty or untracked bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

SOURCE_SCHEMA = "koschei.language-foundation-corpus.v1"
GENERATOR_VERSION = "koschei-foundation-export/v1"
SOURCE_REPOSITORY = "bugsbuny243/koschei-lang"
_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
_ALLOWED_BLOB_MODES = {"100644", "100755"}
_ROOT_REFERENCES = {"README.md", "README.tr.md", "README.en.md"}


class LanguageFoundationExportError(ValueError):
    """Raised when a safe, provenance-bound corpus cannot be exported."""


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_language_foundation_corpus(
    repo_root: str | Path,
    *,
    source_commit: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    _verify_exact_commit(root, source_commit)

    documents: list[dict[str, str]] = []
    for mode, object_type, object_sha, relative in _git_tree_entries(root, source_commit):
        if not _included_source(relative):
            continue
        _verify_relative_path(relative)
        if object_type != "blob" or mode not in _ALLOWED_BLOB_MODES:
            raise LanguageFoundationExportError(
                f"selected foundation source is not a regular tracked file: {relative}"
            )
        raw = _git(root, "cat-file", "blob", object_sha)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LanguageFoundationExportError(
                f"selected foundation source is not UTF-8: {relative}"
            ) from exc
        if text.startswith("\ufeff"):
            raise LanguageFoundationExportError(
                f"selected foundation source has a UTF-8 BOM: {relative}"
            )

        kind = "koschei_source" if relative.startswith("examples/") else "reference"
        family = _family(relative, kind)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        material = f"{kind}\0{family}\0{relative}\0{source_sha256}"
        documents.append(
            {
                "document_id": hashlib.sha256(material.encode()).hexdigest(),
                "family": family,
                "kind": kind,
                "path": relative,
                "source_sha256": source_sha256,
                "text": text,
            }
        )

    documents.sort(key=lambda item: item["path"])
    if not documents:
        raise LanguageFoundationExportError("foundation source selection is empty")
    paths = [item["path"] for item in documents]
    if len(paths) != len(set(paths)):
        raise LanguageFoundationExportError("foundation source selection contains duplicate paths")
    families = {item["family"] for item in documents}
    if len(families) < 3:
        raise LanguageFoundationExportError(
            "foundation corpus requires at least three families for leakage-safe splits"
        )

    total_bytes = sum(len(item["text"].encode("utf-8")) for item in documents)
    payload: dict[str, Any] = {
        "schema_version": SOURCE_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source_commit,
        "document_count": len(documents),
        "family_count": len(families),
        "total_bytes": total_bytes,
        "documents": documents,
    }
    payload["corpus_sha256"] = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    return payload


def write_language_foundation_corpus(
    corpus: dict[str, Any],
    output: str | Path,
) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(corpus, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise FileExistsError(f"language foundation corpus already exists: {destination}") from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _verify_exact_commit(root: Path, source_commit: str) -> None:
    if not _COMMIT_RE.fullmatch(source_commit):
        raise LanguageFoundationExportError(
            "source commit must be an exact lowercase 40-character Git SHA"
        )
    object_type = _git(root, "cat-file", "-t", source_commit).decode("ascii").strip()
    if object_type != "commit":
        raise LanguageFoundationExportError(f"source object is not a Git commit: {source_commit}")


def _git_tree_entries(root: Path, source_commit: str) -> list[tuple[str, str, str, str]]:
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", source_commit)
    entries: list[tuple[str, str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode_bytes, type_bytes, sha_bytes = metadata.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            object_type = type_bytes.decode("ascii")
            object_sha = sha_bytes.decode("ascii")
            relative = path_bytes.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise LanguageFoundationExportError("Git tree contains an invalid path record") from exc
        entries.append((mode, object_type, object_sha, relative))
    return entries


def _included_source(relative: str) -> bool:
    if relative in _ROOT_REFERENCES:
        return True
    if relative.startswith("docs/") and relative.endswith(".md"):
        return True
    return relative.startswith("examples/") and relative.endswith(".ks")


def _family(relative: str, kind: str) -> str:
    _verify_relative_path(relative)
    parts = Path(relative).parts
    if kind == "koschei_source":
        if len(parts) >= 3 and parts[0] == "examples":
            return f"example:{parts[1]}"
        if len(parts) == 2 and parts[0] == "examples":
            return "example:top-level"
        raise LanguageFoundationExportError(f"Koschei source is outside examples/: {relative}")
    return f"reference:{_reference_family_path(relative)}"


def _reference_family_path(relative: str) -> str:
    if relative in _ROOT_REFERENCES:
        return "README"
    path = Path(relative)
    name = path.name
    for suffix in (".tr.md", ".en.md"):
        if name.endswith(suffix):
            return path.with_name(name[: -len(suffix)] + ".md").as_posix()
    return relative


def _verify_relative_path(relative: str) -> None:
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or relative.startswith("~")
    ):
        raise LanguageFoundationExportError(f"unsafe foundation source path: {relative}")


def _git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise LanguageFoundationExportError(f"cannot execute git: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise LanguageFoundationExportError(
            f"git {' '.join(arguments[:2])} failed: {message or 'unknown git error'}"
        )
    return result.stdout
