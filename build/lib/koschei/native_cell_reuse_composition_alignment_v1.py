"""Route sealed cell/reuse composition graphs ahead of projection/cell frontends."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .native_cell_projection_alignment_v1 import (
    check_object_space_graph_with_native_cell_projection,
)
from .native_cell_reuse_composition_v1 import (
    check_native_cell_reuse_composition_object_space,
    is_native_cell_reuse_composition_graph_secret,
)


_INSTALLED = False


def check_object_space_graph_with_native_cell_reuse_composition(project):
    if is_native_cell_reuse_composition_graph_secret(project.graph_secret):
        return check_native_cell_reuse_composition_object_space(project)
    return check_object_space_graph_with_native_cell_projection(project)


def install_native_cell_reuse_composition_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _check.check_object_space_graph = check_object_space_graph_with_native_cell_reuse_composition
    _commands.check_object_space_graph = check_object_space_graph_with_native_cell_reuse_composition
    _INSTALLED = True
