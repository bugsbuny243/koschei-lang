"""Install native relationship dispatch ahead of frontend/legacy compatibility."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .native_relationship_v1 import (
    check_native_relationship_object_space,
    is_native_relationship_graph_secret,
)
from .object_space_frontend_identity_v1 import (
    check_object_space_graph_by_authenticated_frontend,
)


_INSTALLED = False


def check_object_space_graph_with_native_relationships(project):
    if is_native_relationship_graph_secret(project.graph_secret):
        return check_native_relationship_object_space(project)
    return check_object_space_graph_by_authenticated_frontend(project)


def install_native_relationship_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _check.check_object_space_graph = check_object_space_graph_with_native_relationships
    _commands.check_object_space_graph = check_object_space_graph_with_native_relationships
    _INSTALLED = True
