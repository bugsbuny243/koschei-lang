"""Install authenticated Object Space frontend dispatch into compiler commands."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .object_space_frontend_identity_v1 import (
    check_object_space_graph_by_authenticated_frontend,
)


_INSTALLED = False


def install_object_space_frontend_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # Both command layers intentionally resolve this module global at execution
    # time. Replacing it here makes the same authenticated dispatcher feed check,
    # run, mir, caps, emit-go and build without source sniffing in the CLI.
    _check.check_object_space_graph = check_object_space_graph_by_authenticated_frontend
    _commands.check_object_space_graph = check_object_space_graph_by_authenticated_frontend
    _INSTALLED = True
