"""Route sealed native-cell Object Space graphs ahead of prior native frontends."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .native_cell_realities_v1 import (
    check_native_cell_object_space,
    is_native_cell_graph_secret,
)
from .native_reusable_alignment_v1 import check_object_space_graph_with_native_reuse


_INSTALLED = False


def check_object_space_graph_with_native_cells(project):
    if is_native_cell_graph_secret(project.graph_secret):
        return check_native_cell_object_space(project)
    return check_object_space_graph_with_native_reuse(project)


def install_native_cell_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _check.check_object_space_graph = check_object_space_graph_with_native_cells
    _commands.check_object_space_graph = check_object_space_graph_with_native_cells
    _INSTALLED = True
