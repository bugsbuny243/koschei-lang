#!/usr/bin/env python3
"""Build the Koschei Lang download sold on Polar (`koschei-lang-<version>.zip`).

The archive holds what a user needs and nothing internal: the `koschei`
package with its Core Library, the native data core, the installer, the
license and price pages, the customer README, the language guide, the
generated references and the examples the README runs. Everything sits under
one `koschei-lang-<version>/` directory; `./install.sh` there installs `ks`.
The archive is deterministic (`deterministic_release_zip_v1`): the same
sources give the same bytes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deterministic_release_zip_v1 import DeterministicZipError, build_archive

ROOT = Path(__file__).resolve().parent.parent

# (source relative to the repository, destination inside the bundle)
FILES = (
    ("distribution/polar/README.md", "README.md"),
    ("distribution/polar/README.tr.md", "README.tr.md"),
    ("LICENSE", "LICENSE"),
    ("LICENSE.tr.md", "LICENSE.tr.md"),
    ("LICENSING.md", "LICENSING.md"),
    ("LICENSING.tr.md", "LICENSING.tr.md"),
    ("install.sh", "install.sh"),
    ("pyproject.toml", "pyproject.toml"),
    ("native/datajson/json.go", "native/datajson/json.go"),
    ("examples/hello.ks", "examples/hello.ks"),
)
DIRECTORIES = (
    "koschei",
    "docs/guide",
    "docs/reference",
    "examples/apps",
    "examples/supply_chain",
)


def version(root: Path = ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _wanted(path: Path) -> bool:
    return "__pycache__" not in path.parts and path.suffix != ".pyc"


def stage(root: Path, target: Path) -> None:
    for source, destination in FILES:
        path = target / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / source, path)
    for directory in DIRECTORIES:
        for source in sorted((root / directory).rglob("*")):
            if source.is_file() and _wanted(source.relative_to(root)):
                path = target / source.relative_to(root)
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, path)


def build_bundle(output_dir: Path, root: Path = ROOT) -> Path:
    name = f"koschei-lang-{version(root)}"
    output = output_dir / f"{name}.zip"
    with tempfile.TemporaryDirectory(prefix="koschei-polar-") as temporary:
        staging = Path(temporary)
        stage(root, staging / name)
        build_archive(staging, output)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "polar")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        output = build_bundle(args.output_dir)
    except (OSError, DeterministicZipError) as exc:
        raise SystemExit(f"polar bundle refused: {exc}") from exc
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
