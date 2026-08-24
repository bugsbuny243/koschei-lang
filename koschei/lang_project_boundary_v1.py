"""Repository boundary: Koschei Lang must not depend on frozen Sentinel code."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tomllib
from typing import Iterable

_TOKEN = "sentinel"
_TOKEN_SPLIT = re.compile(r"[._/\\-]+")
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXCLUDED_PYTHON_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)


class LangProjectBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundaryViolationV1:
    path: str
    line: int
    kind: str
    detail: str


def _mentions_sentinel_token(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _TOKEN in (part.lower() for part in _TOKEN_SPLIT.split(value) if part)


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _importlib_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    importlib_aliases: set[str] = set()
    import_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or "importlib")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)
    return importlib_aliases, import_module_aliases


def _dynamic_import_target(
    node: ast.Call,
    *,
    importlib_aliases: set[str],
    import_module_aliases: set[str],
) -> str | None:
    if not node.args:
        return None

    function = node.func
    is_dynamic_import = isinstance(function, ast.Name) and (
        function.id == "__import__" or function.id in import_module_aliases
    )
    if (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id in importlib_aliases
    ):
        is_dynamic_import = True

    if not is_dynamic_import:
        return None
    return _literal_string(node.args[0])


def _inspect_python_file(repo_root: Path, path: Path) -> list[BoundaryViolationV1]:
    relative = path.relative_to(repo_root).as_posix()
    violations: list[BoundaryViolationV1] = []
    if _mentions_sentinel_token(path.name):
        violations.append(BoundaryViolationV1(relative, 1, "module-name", path.name))

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise LangProjectBoundaryError(f"cannot inspect {relative}: {error}") from error

    importlib_aliases, import_module_aliases = _importlib_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _mentions_sentinel_token(alias.name):
                    violations.append(
                        BoundaryViolationV1(relative, node.lineno, "import", alias.name)
                    )
        elif isinstance(node, ast.ImportFrom):
            if _mentions_sentinel_token(node.module):
                violations.append(
                    BoundaryViolationV1(relative, node.lineno, "import-from", str(node.module))
                )
            for alias in node.names:
                if _mentions_sentinel_token(alias.name):
                    violations.append(
                        BoundaryViolationV1(relative, node.lineno, "import-symbol", alias.name)
                    )
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(
                node,
                importlib_aliases=importlib_aliases,
                import_module_aliases=import_module_aliases,
            )
            if _mentions_sentinel_token(target):
                violations.append(
                    BoundaryViolationV1(relative, node.lineno, "dynamic-import", str(target))
                )
    return violations


def _iter_repository_python_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*.py")):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root)
        if any(part in _EXCLUDED_PYTHON_DIRS for part in relative.parts[:-1]):
            continue
        yield path


def _python_violations(repo_root: Path) -> list[BoundaryViolationV1]:
    package_root = repo_root / "koschei"
    if not package_root.is_dir():
        raise LangProjectBoundaryError("Koschei package directory is missing")

    violations: list[BoundaryViolationV1] = []
    for path in _iter_repository_python_files(repo_root):
        violations.extend(_inspect_python_file(repo_root, path))
    return violations


def _require_dependency_list(value: object, *, location: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise LangProjectBoundaryError(f"{location} must be a list of dependency strings")
    return list(value)


def _dependency_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise LangProjectBoundaryError(
            f"cannot determine dependency name from pyproject requirement: {requirement!r}"
        )
    return match.group(1)


def _dependency_candidates(data: object) -> list[str]:
    if not isinstance(data, dict):
        raise LangProjectBoundaryError("pyproject.toml root must be a table")

    candidates: list[str] = []
    project = data.get("project", {})
    if not isinstance(project, dict):
        raise LangProjectBoundaryError("[project] must be a table")
    candidates.extend(
        _require_dependency_list(project.get("dependencies", []), location="project.dependencies")
    )

    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise LangProjectBoundaryError("project.optional-dependencies must be a table")
    for group, values in sorted(optional.items()):
        candidates.extend(
            _require_dependency_list(
                values,
                location=f"project.optional-dependencies.{group}",
            )
        )

    build_system = data.get("build-system", {})
    if not isinstance(build_system, dict):
        raise LangProjectBoundaryError("[build-system] must be a table")
    candidates.extend(
        _require_dependency_list(build_system.get("requires", []), location="build-system.requires")
    )
    return candidates


def _dependency_violations(repo_root: Path) -> list[BoundaryViolationV1]:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        raise LangProjectBoundaryError("pyproject.toml is missing")
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise LangProjectBoundaryError(f"cannot inspect pyproject.toml: {error}") from error

    violations: list[BoundaryViolationV1] = []
    for dependency in _dependency_candidates(data):
        if _mentions_sentinel_token(_dependency_name(dependency)):
            violations.append(
                BoundaryViolationV1("pyproject.toml", 1, "dependency", dependency)
            )
    return violations


def audit_lang_project_boundary_v1(repo_root: str | Path) -> tuple[BoundaryViolationV1, ...]:
    root = Path(repo_root).resolve()
    return tuple(_python_violations(root) + _dependency_violations(root))


def require_lang_project_boundary_v1(repo_root: str | Path) -> None:
    violations = audit_lang_project_boundary_v1(repo_root)
    if violations:
        detail = "; ".join(
            f"{item.path}:{item.line}:{item.kind}:{item.detail}" for item in violations
        )
        raise LangProjectBoundaryError(
            "Koschei Lang must remain independent from frozen Sentinel code: " + detail
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-lang-boundary",
        description="Verify that Koschei Lang has no code/dependency import on frozen Sentinel",
    )
    parser.add_argument("--repo-root", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_lang_project_boundary_v1(args.repo_root)
        print("KOSCHEI LANG / SENTINEL SEPARATION: PASS")
        return 0
    except LangProjectBoundaryError as error:
        print(f"ks-lang-boundary: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
