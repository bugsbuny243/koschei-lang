"""Build the Koschei Forms download sold on Polar: dist/forms/koschei-forms-<version>.zip.

The zip is deterministic: fixed file order, timestamps and permissions, so two
builds of the same commit are byte-identical.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = ROOT / "products" / "forms"
VERSION = "1.0.0"
FILES = ("README.md", "LICENSE.md", "Dockerfile", "main.ks", "rules.ks", "pages.ks", "csv.ks")
_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def build(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"koschei-forms-{VERSION}.zip"
    folder = f"koschei-forms-{VERSION}"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            info = zipfile.ZipInfo(f"{folder}/{name}", date_time=_TIMESTAMP)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (PRODUCT / name).read_bytes())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "forms")
    print(build(parser.parse_args().output_dir))


if __name__ == "__main__":
    main()
