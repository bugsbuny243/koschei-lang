"""Install native decision reality dispatch ahead of value-domain compatibility."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .native_decision_reservation_v1 import install_native_decision_reservation_v1
from .native_value_domain_alignment_v1 import check_object_space_graph_with_native_value_domains
from .object_space_decision_realities_v1 import (
    check_native_decision_object_space,
    is_native_decision_graph_secret,
)


_INSTALLED = False


def check_object_space_graph_with_native_decisions(project):
    if is_native_decision_graph_secret(project.graph_secret):
        return check_native_decision_object_space(project)
    return check_object_space_graph_with_native_value_domains(project)


def install_native_decision_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    install_native_decision_reservation_v1()
    _check.check_object_space_graph = check_object_space_graph_with_native_decisions
    _commands.check_object_space_graph = check_object_space_graph_with_native_decisions
    _INSTALLED = True