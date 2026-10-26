"""Workspace-aware module resolution with explicit package boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ast_nodes import SourceLocation
from .modules import MODULE_SUFFIX, ModuleError, ModuleGraph, load_graph
from .workspace import WorkspaceConfig, WorkspaceMember, WorkspaceError


@dataclass(frozen=True, slots=True)
class WorkspaceImportResolver:
    workspace: WorkspaceConfig

    def __post_init__(self) -> None:
        roots = [member.project.root.resolve() for member in self.workspace.members]
        if len(roots) != len(set(roots)):
            raise WorkspaceError("workspace member roots are not unique")
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if _contains(left, right) or _contains(right, left):
                    raise WorkspaceError(
                        "workspace member roots cannot be nested when package imports are enabled"
                    )

    def __call__(
        self,
        importer: Path,
        name: str,
        location: SourceLocation,
    ) -> Path:
        owner = self.owner_for(importer)
        local = importer.parent / (name + MODULE_SUFFIX)
        dependency = (
            self.workspace.by_name.get(name)
            if name in owner.dependencies
            else None
        )

        local_exists = local.exists()
        if local_exists and dependency is not None:
            raise ModuleError(
                "KS1601",
                f"Belirsiz import '{name}': hem paket-içi {local.name} dosyası hem de "
                "aynı adlı workspace dependency var. Gölgeleme güvenlik nedeniyle kapalıdır.",
                location,
            )

        if local_exists:
            if local.is_symlink():
                raise ModuleError(
                    "KS1601",
                    f"Workspace paket-içi import symlink olamaz: {local.name}",
                    location,
                )
            resolved = local.resolve()
            if not _contains(owner.project.root.resolve(), resolved, include_equal=True):
                raise ModuleError(
                    "KS1601",
                    f"Paket-içi import workspace üyesinin dışına kaçıyor: {name}",
                    location,
                )
            return resolved

        if dependency is not None:
            return dependency.project.entry

        existing_package = self.workspace.by_name.get(name)
        if existing_package is not None:
            raise ModuleError(
                "KS1601",
                f"Workspace paketi '{name}' doğrudan dependency olarak ilan edilmemiş. "
                f"'{owner.name}' yalnız [dependencies].{owner.name} listesindeki paketleri "
                "import edebilir.",
                location,
            )

        # Preserve the ordinary module loader's missing-sibling diagnostic for
        # names that are neither local files nor workspace packages.
        return local

    def owner_for(self, source: Path) -> WorkspaceMember:
        resolved = source.resolve(strict=False)
        matches = [
            member
            for member in self.workspace.members
            if _contains(member.project.root.resolve(), resolved, include_equal=True)
        ]
        if len(matches) != 1:
            raise WorkspaceError(
                f"source has no unique workspace package owner: {resolved}"
            )
        return matches[0]


def load_workspace_member_graph(
    workspace: WorkspaceConfig,
    member_name: str,
) -> ModuleGraph:
    member = workspace.by_name.get(member_name)
    if member is None:
        raise WorkspaceError(f"unknown workspace package: {member_name}")
    resolver = WorkspaceImportResolver(workspace)
    return load_graph(member.project.entry, import_resolver=resolver)


def graph_uses_workspace_packages(
    workspace: WorkspaceConfig,
    member: WorkspaceMember,
    graph: ModuleGraph,
) -> bool:
    own_root = member.project.root.resolve()
    return any(
        not _contains(own_root, module.path.resolve(), include_equal=True)
        for module in graph.modules.values()
    )


def _contains(root: Path, path: Path, *, include_equal: bool = False) -> bool:
    if include_equal and path == root:
        return True
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root
