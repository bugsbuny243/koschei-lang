"""Koschei Core Library v1: library modules written in Koschei itself.

The Core Library ships with the toolchain as ordinary `.ks` source under
``koschei/core_library/``. Its modules are checked, lowered and executed by the
same compiler pipeline as user code, so a library function has exactly one
implementation instead of a Python interpreter copy plus a generated Go copy.

Resolution rules (enforced by ``modules._resolve_sibling_import``):

* only the names in ``CORE_LIBRARY_MODULES_V1`` are library modules; a stray
  ``.ks`` file placed in the library directory is never importable by users;
* a project file with the same name as a library module is an ambiguous import
  and fails closed instead of silently shadowing either side;
* library modules may import each other, never project files; and
* importing a library module grants no authority: library functions are
  ordinary Koschei code and receive capabilities only as explicit arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

SCHEMA = "koschei.core-library/v1"
MODULE_SUFFIX = ".ks"
CORE_LIBRARY_ROOT = (Path(__file__).resolve().parent / "core_library").resolve()

# Explicit registry. Adding a module is a reviewed change, not a side effect of
# dropping a file into the package directory.
CORE_LIBRARY_MODULES_V1: tuple[str, ...] = ("list", "text")


@dataclass(frozen=True, slots=True)
class LibraryFunction:
    name: str
    parameters: tuple[str, ...]
    returns: str
    generic: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LibraryModule:
    name: str
    path: str
    sha256: str
    imports: tuple[str, ...]
    functions: tuple[LibraryFunction, ...]


def core_library_module(name: str) -> Path | None:
    """Return the source path of a registered library module, if any."""

    if name not in CORE_LIBRARY_MODULES_V1:
        return None
    return CORE_LIBRARY_ROOT / (name + MODULE_SUFFIX)


def is_core_library_path(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return resolved.parent == CORE_LIBRARY_ROOT and any(
        resolved == core_library_module(name) for name in CORE_LIBRARY_MODULES_V1
    )


def describe_core_library() -> tuple[LibraryModule, ...]:
    """Parse every registered module and report its public surface."""

    from .parser import parse

    modules: list[LibraryModule] = []
    for name in CORE_LIBRARY_MODULES_V1:
        path = core_library_module(name)
        assert path is not None
        source = path.read_bytes()
        program = parse(source.decode("utf-8"))
        functions = tuple(
            LibraryFunction(
                name=declaration.name,
                parameters=tuple(
                    f"{parameter.name}: {parameter.type_ref}"
                    for parameter in declaration.parameters
                ),
                returns=(
                    "Unit"
                    if declaration.return_type is None
                    else str(declaration.return_type)
                ),
                generic=tuple(getattr(declaration, "type_parameters", ()) or ()),
            )
            for declaration in program.declarations
        )
        modules.append(
            LibraryModule(
                name=name,
                path=f"core_library/{name}{MODULE_SUFFIX}",
                sha256=hashlib.sha256(source).hexdigest(),
                imports=tuple(item.name for item in program.imports),
                functions=functions,
            )
        )
    return tuple(modules)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ks-core-library",
        description="List the Koschei Core Library modules written in Koschei.",
    )
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    modules = describe_core_library()
    if arguments.json:
        payload = {
            "schema": SCHEMA,
            "modules": [asdict(module) for module in modules],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    for module in modules:
        print(f"{module.name}  ({module.path}, sha256 {module.sha256[:16]})")
        for function in module.functions:
            generic = f"<{', '.join(function.generic)}>" if function.generic else ""
            parameters = ", ".join(function.parameters)
            print(f"  fn {function.name}{generic}({parameters}) -> {function.returns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
