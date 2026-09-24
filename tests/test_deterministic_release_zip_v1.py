from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import time
import zipfile

from tools.deterministic_release_zip_v1 import FIXED_TIMESTAMP, build_archive


def _stage(root: Path, *, reverse: bool) -> Path:
    root.mkdir()
    entries = [
        ("manifest.json", b'{"version":"0.10.0"}\n', False),
        ("bin/ks", b"fixture-binary\n", True),
        ("evidence/sbom.json", b'{"schema":"fixture"}\n', False),
    ]
    if reverse:
        entries.reverse()
    for index, (relative, payload, executable) in enumerate(entries):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o755 if executable else 0o644)
        timestamp = time.time() - (index + 1) * 86400
        os.utime(path, (timestamp, timestamp))
    return root


def test_release_zip_is_byte_identical_across_mtime_and_creation_order(tmp_path: Path):
    first_stage = _stage(tmp_path / "first-stage", reverse=False)
    second_stage = _stage(tmp_path / "second-stage", reverse=True)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    build_archive(first_stage, first)
    build_archive(second_stage, second)

    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()

    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        for info in archive.infolist():
            assert info.date_time == FIXED_TIMESTAMP
        binary = archive.getinfo("bin/ks")
        mode = (binary.external_attr >> 16) & 0o777
        assert mode == 0o755
        manifest = archive.getinfo("manifest.json")
        manifest_mode = (manifest.external_attr >> 16) & 0o777
        assert manifest_mode == 0o644


def test_release_zip_refuses_to_overwrite_existing_output(tmp_path: Path):
    stage = _stage(tmp_path / "stage", reverse=False)
    output = tmp_path / "release.zip"
    output.write_bytes(b"already-here")

    try:
        build_archive(stage, output)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("deterministic release archive must refuse overwrite")
