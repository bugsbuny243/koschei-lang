"""Workspace lock adapter for declared cross-package module graphs."""

from __future__ import annotations

from .module_lock import build_module_lock
from .workspace import (
    WorkspaceConfig,
    WorkspaceError,
    WorkspaceLock,
    WorkspaceLockedMember,
    _digest,
    _sha256_file,
    _workspace_lock_payload,
)
from .workspace_modules import (
    graph_uses_workspace_packages,
    load_workspace_member_graph,
)


def build_workspace_package_lock(workspace: WorkspaceConfig) -> WorkspaceLock:
    """Build one workspace lock over package-aware source graphs.

    A member without cross-package imports retains the legacy member module-lock
    root so Workspace v1 digests stay stable. Once a graph crosses a package
    boundary, the workspace root becomes the only lock root and all imported
    package source paths are represented workspace-relatively.
    """

    locked: list[WorkspaceLockedMember] = []
    by_name = workspace.by_name
    for name in workspace.build_order:
        member = by_name[name]
        graph = load_workspace_member_graph(workspace, name)
        if graph.root_module.path.resolve() != member.project.entry.resolve():
            raise WorkspaceError(f"workspace package graph root mismatch: {name}")
        lock_root = (
            workspace.root
            if graph_uses_workspace_packages(workspace, member, graph)
            else member.project.entry.parent
        )
        module_lock = build_module_lock(
            member.project.entry,
            graph=graph,
            root=lock_root,
        )
        entry = member.project.entry.relative_to(member.project.root).as_posix()
        locked.append(
            WorkspaceLockedMember(
                name=name,
                path=member.path,
                version=member.project.version,
                entry=entry,
                dependencies=member.dependencies,
                manifest_sha256=_sha256_file(member.project.manifest),
                module_lock_digest=module_lock.lock_digest,
            )
        )

    ordered_members = tuple(locked)
    manifest_sha256 = _sha256_file(workspace.manifest)
    payload = _workspace_lock_payload(
        manifest_sha256=manifest_sha256,
        members=ordered_members,
        build_order=workspace.build_order,
    )
    return WorkspaceLock(
        manifest_sha256=manifest_sha256,
        members=ordered_members,
        build_order=workspace.build_order,
        workspace_digest=_digest(payload),
    )


def verify_workspace_package_lock(
    workspace: WorkspaceConfig,
    locked: WorkspaceLock,
) -> WorkspaceLock:
    """Verify through the immutable source index when one exists for this lock."""

    from .workspace_lock_index import DEFAULT_LOCK_INDEX_DIR, verify_or_create_lock_index

    return verify_or_create_lock_index(
        workspace,
        locked,
        cache_root=workspace.root / DEFAULT_LOCK_INDEX_DIR,
    )


def verify_workspace_package_lock_full(
    workspace: WorkspaceConfig,
    locked: WorkspaceLock,
) -> WorkspaceLock:
    """Reconstruct every package module graph and compare the complete lock.

    This is the authoritative slow path used on a source-index miss. Keeping it
    separate makes it possible to prove that an index hit does not invoke parser,
    semantic, typed-HIR, or MIR work for unrelated workspace packages.
    """

    current = build_workspace_package_lock(workspace)
    if current.to_dict() == locked.to_dict():
        return current
    if current.manifest_sha256 != locked.manifest_sha256:
        raise WorkspaceError("workspace manifest digest changed")

    expected = {member.name: member for member in locked.members}
    actual = {member.name: member for member in current.members}
    if set(expected) != set(actual):
        raise WorkspaceError("workspace member set changed")
    for name in current.build_order:
        if expected[name] != actual[name]:
            raise WorkspaceError(f"workspace member identity changed: {name}")
    if current.build_order != locked.build_order:
        raise WorkspaceError("workspace dependency build order changed")
    raise WorkspaceError("workspace lock digest changed")
