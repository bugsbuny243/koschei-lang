"""Materialize a sealed native-intelligence corpus into split JSONL files.

The export is a transport artifact, not a new source of truth. It verifies the
sealed oracle-backed corpus against its constitutional holdout, writes one file
per split, hashes exact bytes, and seals those file identities into a manifest.
The test split remains physically separate from train and validation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .native_intelligence_holdout_v1 import NativeIntelligenceHoldoutV1
from .native_intelligence_training_corpus_v1 import NativeTrainingCorpusReleaseV1, SPLITS

_CTX = b"koschei.native-intelligence-training-export/v1\x00"
SCHEMA = "koschei.native-intelligence-training-export/v1"


class NativeTrainingExportError(ValueError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(kind: bytes, payload: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(payload).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _d64(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise NativeTrainingExportError(f"{label} must be a 64-character digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise NativeTrainingExportError(f"{label} must be hexadecimal") from error
    if value == "0" * 64:
        raise NativeTrainingExportError(f"{label} cannot be zero")
    return value.lower()


@dataclass(frozen=True, slots=True)
class NativeTrainingSplitFileV1:
    split: str
    filename: str
    example_count: int
    byte_count: int
    sha256: str
    corpus_split_digest: str


@dataclass(frozen=True, slots=True)
class NativeTrainingExportManifestV1:
    schema: str
    source_commit: str
    constitutional_holdout_digest: str
    corpus_digest: str
    corpus_example_count: int
    files: tuple[NativeTrainingSplitFileV1, ...]
    authority: bool
    digest: str
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        return json.loads(_canonical_json(asdict(self)))

    def assert_sealed(self) -> None:
        if self.version != 1 or self.schema != SCHEMA:
            raise NativeTrainingExportError("unsupported native training export manifest")
        if not isinstance(self.source_commit, str) or len(self.source_commit) != 40:
            raise NativeTrainingExportError("training export source_commit must be 40 hexadecimal characters")
        try:
            int(self.source_commit, 16)
        except ValueError as error:
            raise NativeTrainingExportError("training export source_commit must be hexadecimal") from error
        _d64(self.constitutional_holdout_digest, "constitutional_holdout_digest")
        _d64(self.corpus_digest, "corpus_digest")
        if self.authority is not False:
            raise NativeTrainingExportError("native training export cannot carry authority")
        if tuple(row.split for row in self.files) != SPLITS:
            raise NativeTrainingExportError("training export must contain train/validation/test in canonical order")
        if len({row.filename for row in self.files}) != len(SPLITS):
            raise NativeTrainingExportError("training export filenames must be distinct")
        if len({row.sha256 for row in self.files}) != len(SPLITS):
            raise NativeTrainingExportError("training export split file digests must be distinct")
        if sum(row.example_count for row in self.files) != self.corpus_example_count:
            raise NativeTrainingExportError("training export example count mismatch")
        for row in self.files:
            if row.example_count < 1 or row.byte_count < 1:
                raise NativeTrainingExportError("training export split cannot be empty")
            _d64(row.sha256, f"{row.split} file sha256")
            _d64(row.corpus_split_digest, f"{row.split} corpus split digest")
        expected = _hash(
            b"manifest",
            {
                "schema": self.schema,
                "source_commit": self.source_commit,
                "constitutional_holdout_digest": self.constitutional_holdout_digest,
                "corpus_digest": self.corpus_digest,
                "corpus_example_count": self.corpus_example_count,
                "files": [asdict(row) for row in self.files],
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingExportError("native training export manifest seal mismatch")

    def assert_for(
        self,
        holdout: NativeIntelligenceHoldoutV1,
        corpus: NativeTrainingCorpusReleaseV1,
    ) -> None:
        self.assert_sealed()
        holdout.assert_sealed()
        corpus.assert_sealed(holdout)
        if self.source_commit != corpus.source_commit:
            raise NativeTrainingExportError("training export belongs to a different source commit")
        if self.constitutional_holdout_digest != holdout.digest:
            raise NativeTrainingExportError("training export belongs to a different constitutional holdout")
        if self.corpus_digest != corpus.digest:
            raise NativeTrainingExportError("training export belongs to a different corpus release")
        if self.corpus_example_count != corpus.example_count:
            raise NativeTrainingExportError("training export corpus example count mismatch")
        for row in self.files:
            if row.corpus_split_digest != corpus.split_digest(row.split):
                raise NativeTrainingExportError(f"training export split identity mismatch: {row.split}")


def _training_row(example) -> dict[str, object]:
    return {
        "schema": "koschei.native-intelligence-supervised-example/v1",
        "id": example.example_id,
        "stage": example.stage,
        "family": example.family,
        "split": example.split,
        "task": example.task,
        "input": example.input_text,
        "target": example.target_text,
        "oracle": example.oracle,
        "oracle_digest": example.oracle_digest,
        "example_digest": example.digest,
        "authority": False,
    }


def _write_split(path: Path, corpus: NativeTrainingCorpusReleaseV1, split: str) -> NativeTrainingSplitFileV1:
    examples = tuple(row for row in corpus.examples if row.split == split)
    if not examples:
        raise NativeTrainingExportError(f"cannot export empty split: {split}")
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for example in examples:
            handle.write(_canonical_json(_training_row(example)))
            handle.write("\n")
    return NativeTrainingSplitFileV1(
        split=split,
        filename=path.name,
        example_count=len(examples),
        byte_count=path.stat().st_size,
        sha256=_file_sha256(path),
        corpus_split_digest=corpus.split_digest(split),
    )


def write_native_training_export_v1(
    holdout: NativeIntelligenceHoldoutV1,
    corpus: NativeTrainingCorpusReleaseV1,
    output_directory: str | Path,
) -> NativeTrainingExportManifestV1:
    """Atomically materialize a verified corpus without overwriting existing data."""

    holdout.assert_sealed()
    corpus.assert_sealed(holdout)
    destination = Path(output_directory)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    root = Path(tempfile.mkdtemp(prefix=".koschei-training-", dir=destination.parent))
    try:
        files = tuple(_write_split(root / f"{split}.jsonl", corpus, split) for split in SPLITS)
        manifest = NativeTrainingExportManifestV1(
            schema=SCHEMA,
            source_commit=corpus.source_commit,
            constitutional_holdout_digest=corpus.constitutional_holdout_digest,
            corpus_digest=corpus.digest,
            corpus_example_count=corpus.example_count,
            files=files,
            authority=False,
            digest="",
        )
        object.__setattr__(
            manifest,
            "digest",
            _hash(
                b"manifest",
                {
                    "schema": manifest.schema,
                    "source_commit": manifest.source_commit,
                    "constitutional_holdout_digest": manifest.constitutional_holdout_digest,
                    "corpus_digest": manifest.corpus_digest,
                    "corpus_example_count": manifest.corpus_example_count,
                    "files": [asdict(row) for row in manifest.files],
                    "authority": False,
                },
            ),
        )
        manifest.assert_for(holdout, corpus)
        (root / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        root.rename(destination)
    except Exception:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        raise
    return manifest


def load_native_training_export_manifest_v1(path: str | Path) -> NativeTrainingExportManifestV1:
    """Load and self-verify a materialized training export manifest."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        files = tuple(NativeTrainingSplitFileV1(**row) for row in value["files"])
        manifest = NativeTrainingExportManifestV1(
            schema=value["schema"],
            source_commit=value["source_commit"],
            constitutional_holdout_digest=value["constitutional_holdout_digest"],
            corpus_digest=value["corpus_digest"],
            corpus_example_count=value["corpus_example_count"],
            files=files,
            authority=value["authority"],
            digest=value["digest"],
            version=value.get("version", 1),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise NativeTrainingExportError(f"invalid native training export manifest: {error}") from error
    manifest.assert_sealed()
    return manifest


def verify_native_training_export_v1(manifest: NativeTrainingExportManifestV1, directory: str | Path) -> None:
    """Verify exact split bytes against one sealed export manifest."""

    manifest.assert_sealed()
    root = Path(directory)
    for row in manifest.files:
        path = root / row.filename
        if not path.is_file():
            raise NativeTrainingExportError(f"training export split missing: {row.filename}")
        if path.stat().st_size != row.byte_count:
            raise NativeTrainingExportError(f"training export byte count mismatch: {row.filename}")
        if _file_sha256(path) != row.sha256:
            raise NativeTrainingExportError(f"training export file digest mismatch: {row.filename}")
        lines = sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
        if lines != row.example_count:
            raise NativeTrainingExportError(f"training export example count mismatch: {row.filename}")
