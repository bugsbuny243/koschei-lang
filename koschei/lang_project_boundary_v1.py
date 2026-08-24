"""Repository boundary: Koschei Lang must not depend on frozen Sentinel code."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys
import tomllib

_TOKEN = "sentinel"


class LangProjectBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundaryViolationV1:
    path: str
    line: int
    kind: str
    detail: str


def _contains_sentinel(value: object) -> bool:
    return isinstance(value, str) and _TOKEN in value.lower()


def _python_violations(repo_root: Path) -> list[BoundaryViolationV1]:
    package = repo_root / "koschei"
    if not package.is_dir():
        raise LangProjectBoundaryError("Koschei package directory is missing")

    violations: list[BoundaryViolationV1] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        if _contains_sentinel(path.name):
            violations.append(BoundaryViolationV1(relative, 1, "module-name", path.name))

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeDecodeError, SyntaxError) as error:
            raise LangProjectBoundaryError(f"cannot inspect {relative}: {error}") from error

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _contains_sentinel(alias.name):
                        violations.append(
                            BoundaryViolationV1(relative, node.lineno, "import", alias.name)
                        )
            elif isinstance(node, ast.ImportFrom):
                if _contains_sentinel(node.module):
                    violations.append(
                        BoundaryViolationV1(relative, node.lineno, "import-from", str(node.module))
                    )
                for alias in node.names:
                    if _contains_sentinel(alias.name):
                        violations.append(
                            BoundaryViolationV1(relative, node.lineno, "import-symbol", alias.name)
                        )
            elif isinstance(node, ast.Call):
                function = node.func
                dynamic_import = (
                    isinstance(function, ast.Name) and function.id == "__import__"
                ) or (
                    isinstance(function, ast.Attribute) and function.attr == "import_module"
                )
                if dynamic_import and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and _contains_sentinel(first.value):
                        violations.append(
                            BoundaryViolationV1(
                                relative,
                                node.lineno,
                                "dynamic-import",
                                str(first.value),
                            )
                        )
    return violations


def _dependency_violations(repo_root: Path) -> list[BoundaryViolationV1]:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        raise LangProjectBoundaryError("pyproject.toml is missing")
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise LangProjectBoundaryError(f"cannot inspect pyproject.toml: {error}") from error

    project = data.get("project", {})
    candidates: list[str] = []
    if isinstance(project, dict):
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            candidates.extend(item for item in dependencies if isinstance(item, str))
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    candidates.extend(item for item in values if isinstance(item, str))

    return [
        BoundaryViolationV1("pyproject.toml", 1, "dependency", dependency)
        for dependency in candidates
        if _contains_sentinel(dependency)
    ]


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
