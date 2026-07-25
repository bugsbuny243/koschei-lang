from __future__ import annotations

import base64
import subprocess
import tempfile
import zlib
from pathlib import Path

EXPECTED_BASE = "4d19495eb34da9a4b36935232a90b56eb9ecca49"
PARTS = [Path(f".security/p023/part{index:02d}.txt") for index in range(4)]


def main() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != EXPECTED_BASE:
        raise SystemExit(
            f"refusing to patch unexpected base: {head} != {EXPECTED_BASE}"
        )
    encoded = "".join(path.read_text(encoding="utf-8") for path in PARTS)
    patch = zlib.decompress(base64.b64decode(encoded))
    with tempfile.NamedTemporaryFile(suffix=".patch", delete=False) as stream:
        stream.write(patch)
        patch_path = Path(stream.name)
    try:
        subprocess.run(
            ["git", "apply", "--index", "--whitespace=error-all", str(patch_path)],
            check=True,
        )
    finally:
        patch_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
