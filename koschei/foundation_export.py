"""Export authoritative Koschei language material for model foundation training.

The exporter deliberately emits source truth, not synthetic question/answer pairs.
Downstream model training can therefore distinguish continued language-domain
pretraining from later teacher/instruction tuning.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "koschei.language-foundation-corpus.v1"
GENERATOR_VERSION = "koschei-foundation-export/v1"
SOURCE_REPOSITORY = "bugsbuny243/koschei-lang"
_MAX_DOCUMENT_BYTES = 512 * 1024
_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")


class FoundationExportError(ValueError):
    """Raised when authoritative foundation material cannot be exported safely."""


@dataclass(frozen=True)
class FoundationDocument:
    document_id: str
    family: str
    kind: str
    path: str
    source_sha256: str
    text: str


@dataclass(frozen=True)
class FoundationCorpus:
    schema_version: str
    generator_version: str
    source_repository: str
    source_commit: str
    document_count: int
    family_count: int
    total_bytes: int
    corpus_sha256: str
    documents: tuple[FoundationDocument, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["documents"] = [asdict(item) for item in self.documents]
        return payload


def build_foundation_corpus(
    repo_root: str | Path,
    *,
    source_commit: str,
    verify_checkout: bool = True,
) -> FoundationCorpus:
    """Build a deterministic corpus from checked-in language docs and examples."""

    if not _COMMIT_RE.fullmatch(source_commit):
        raise FoundationExportError("source_commit must be a lowercase 40-character git SHA")

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise FoundationExportError(f"repository root does not exist: {root}")
    if verify_checkout:
        _verify_source_checkout(root, source_commit)

    candidates: dict[str, str] = {}
    for name in ("README.md", "README.tr.md"):
        path = root / name
        if path.is_file():
            candidates[name] = "reference"

    docs_root = root / "docs"
    if docs_root.is_dir():
        for path in docs_root.rglob("*.md"):
            if path.is_file():
                candidates[_relative_path(root, path)] = "reference"

    examples_root = root / "examples"
    if examples_root.is_dir():
        for path in examples_root.rglob("*.ks"):
            if path.is_file():
                candidates[_relative_path(root, path)] = "koschei_source"

    if not candidates:
        raise FoundationExportError("no authoritative Koschei docs or example sources were found")

    documents: list[FoundationDocument] = []
    total_bytes = 0
    for relative, kind in sorted(candidates.items()):
        path = root / relative
        _reject_symlink_path(root, path)
        raw = path.read_bytes()
        if len(raw) > _MAX_DOCUMENT_BYTES:
            raise FoundationExportError(f"foundation document exceeds size limit: {relative}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FoundationExportError(f"foundation document is not UTF-8: {relative}") from exc
        source_sha = hashlib.sha256(raw).hexdigest()
        family = _family_for(relative, kind)
        document_id = hashlib.sha256(
            f"{kind}\0{family}\0{relative}\0{source_sha}".encode()
        ).hexdigest()
        documents.append(
            FoundationDocument(
                document_id=document_id,
                family=family,
                kind=kind,
                path=relative,
                source_sha256=source_sha,
                text=text,
            )
        )
        total_bytes += len(raw)

    payload_without_digest = _digest_payload(
        source_commit=source_commit,
        documents=documents,
        total_bytes=total_bytes,
    )
    corpus_sha = hashlib.sha256(canonical_json(payload_without_digest).encode()).hexdigest()
    return FoundationCorpus(
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        source_repository=SOURCE_REPOSITORY,
        source_commit=source_commit,
        document_count=len(documents),
        family_count=len({item.family for item in documents}),
        total_bytes=total_bytes,
        corpus_sha256=corpus_sha,
        documents=tuple(documents),
    )


def verify_foundation_corpus(value: FoundationCorpus | dict[str, Any]) -> FoundationCorpus:
    """Strictly verify hashes, IDs, ordering, grouping and top-level digest."""

    corpus = value if isinstance(value, FoundationCorpus) else _parse_corpus(value)
    if corpus.schema_version != SCHEMA_VERSION:
        raise FoundationExportError("unsupported foundation corpus schema")
    if corpus.generator_version != GENERATOR_VERSION:
        raise FoundationExportError("unsupported foundation corpus generator")
    if corpus.source_repository != SOURCE_REPOSITORY:
        raise FoundationExportError("foundation corpus source repository is not Koschei language")
    if not _COMMIT_RE.fullmatch(corpus.source_commit):
        raise FoundationExportError("foundation corpus source commit is invalid")

    paths = [item.path for item in corpus.documents]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise FoundationExportError("foundation document paths must be unique and sorted")

    total_bytes = 0
    for item in corpus.documents:
        if item.kind not in {"reference", "koschei_source"}:
            raise FoundationExportError(f"unsupported foundation document kind: {item.kind}")
        if item.path.startswith("/") or ".." in Path(item.path).parts or "\\" in item.path:
            raise FoundationExportError(f"unsafe foundation document path: {item.path}")
        raw = item.text.encode()
        total_bytes += len(raw)
        if hashlib.sha256(raw).hexdigest() != item.source_sha256:
            raise FoundationExportError(f"source hash mismatch: {item.path}")
        expected_family = _family_for(item.path, item.kind)
        if item.family != expected_family:
            raise FoundationExportError(f"family mismatch: {item.path}")
        expected_id = hashlib.sha256(
            f"{item.kind}\0{item.family}\0{item.path}\0{item.source_sha256}".encode()
        ).hexdigest()
        if item.document_id != expected_id:
            raise FoundationExportError(f"document id mismatch: {item.path}")

    if corpus.document_count != len(corpus.documents):
        raise FoundationExportError("foundation document count mismatch")
    families = len({item.family for item in corpus.documents})
    if corpus.family_count != families:
        raise FoundationExportError("foundation family count mismatch")
    if corpus.total_bytes != total_bytes:
        raise FoundationExportError("foundation byte count mismatch")

    expected_digest = hashlib.sha256(
        canonical_json(
            _digest_payload(
                source_commit=corpus.source_commit,
                documents=list(corpus.documents),
                total_bytes=total_bytes,
            )
        ).encode()
    ).hexdigest()
    if corpus.corpus_sha256 != expected_digest:
        raise FoundationExportError("foundation corpus digest mismatch")
    return corpus


def load_foundation_corpus(path: str | Path) -> FoundationCorpus:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FoundationExportError("foundation corpus is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise FoundationExportError("foundation corpus must be a JSON object")
    return verify_foundation_corpus(payload)


def write_foundation_corpus(corpus: FoundationCorpus, path: str | Path) -> None:
    verified = verify_foundation_corpus(corpus)
    payload = json.dumps(
        verified.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _atomic_no_replace(Path(path), payload)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_payload(
    *,
    source_commit: str,
    documents: list[FoundationDocument] | tuple[FoundationDocument, ...],
    total_bytes: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source_commit,
        "document_count": len(documents),
        "family_count": len({item.family for item in documents}),
        "total_bytes": total_bytes,
        "documents": [asdict(item) for item in documents],
    }


def _family_for(relative: str, kind: str) -> str:
    path = Path(relative)
    if kind == "koschei_source":
        parts = path.parts
        if len(parts) >= 2 and parts[0] == "examples":
            return f"example:{parts[1]}"
        raise FoundationExportError(f"Koschei source is outside examples/: {relative}")
    return f"reference:{_reference_family_path(relative)}"


def _reference_family_path(relative: str) -> str:
    if relative in {"README.md", "README.tr.md"}:
        return "README"
    path = Path(relative)
    name = path.name
    for suffix in (".tr.md", ".en.md"):
        if name.endswith(suffix):
            base = name[: -len(suffix)] + ".md"
            return path.with_name(base).as_posix()
    return relative


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise FoundationExportError("foundation path escapes repository root") from exc
    _reject_symlink_path(root, path)
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise FoundationExportError("foundation path escapes repository root")
    return relative.as_posix()


def _reject_symlink_path(root: Path, path: Path) -> None:
    current = path
    while current != root:
        if current.is_symlink():
            raise FoundationExportError(f"foundation path contains symlink: {path}")
        current = current.parent


def _verify_source_checkout(root: Path, source_commit: str) -> None:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise FoundationExportError("git is required for trusted foundation export") from exc
    if head.returncode != 0:
        raise FoundationExportError("repository root is not a readable Git checkout")
    if head.stdout.strip() != source_commit:
        raise FoundationExportError("source_commit does not match the checked-out Git HEAD")

    status = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "README.md",
            "README.tr.md",
            "docs",
            "examples",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise FoundationExportError("could not verify foundation source checkout state")
    if status.stdout.strip():
        raise FoundationExportError(
            "foundation source files are dirty or untracked; commit them before export"
        )


def _parse_corpus(payload: dict[str, Any]) -> FoundationCorpus:
    expected = {
        "schema_version",
        "generator_version",
        "source_repository",
        "source_commit",
        "document_count",
        "family_count",
        "total_bytes",
        "corpus_sha256",
        "documents",
    }
    if set(payload) != expected:
        raise FoundationExportError("foundation corpus fields do not match v1 schema")
    rows = payload.get("documents")
    if not isinstance(rows, list):
        raise FoundationExportError("foundation documents must be a list")
    documents: list[FoundationDocument] = []
    document_fields = {"document_id", "family", "kind", "path", "source_sha256", "text"}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict) or set(raw) != document_fields:
            raise FoundationExportError(f"invalid foundation document at index {index}")
        if not all(isinstance(raw[key], str) for key in document_fields):
            raise FoundationExportError(
                f"foundation document fields must be strings at index {index}"
            )
        documents.append(FoundationDocument(**raw))
    scalar_fields = (
        "schema_version",
        "generator_version",
        "source_repository",
        "source_commit",
        "corpus_sha256",
    )
    if not all(isinstance(payload[key], str) for key in scalar_fields):
        raise FoundationExportError("foundation corpus string fields are invalid")
    for key in ("document_count", "family_count", "total_bytes"):
        if not isinstance(payload[key], int) or isinstance(payload[key], bool) or payload[key] < 0:
            raise FoundationExportError(f"foundation corpus {key} is invalid")
    return FoundationCorpus(
        schema_version=payload["schema_version"],
        generator_version=payload["generator_version"],
        source_repository=payload["source_repository"],
        source_commit=payload["source_commit"],
        document_count=payload["document_count"],
        family_count=payload["family_count"],
        total_bytes=payload["total_bytes"],
        corpus_sha256=payload["corpus_sha256"],
        documents=tuple(documents),
    )


def _atomic_no_replace(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            raise FileExistsError(f"foundation corpus already exists: {path}") from None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
