"""Install native value-domain dispatch ahead of older frontend compatibility."""

from __future__ import annotations

from . import object_space_check_v1 as _check
from . import object_space_commands_v1 as _commands
from .native_relationship_alignment_v1 import check_object_space_graph_with_native_relationships
from .native_value_domain_backend_alignment_v1 import (
    install_native_value_domain_backend_alignment_v1,
)
from .native_value_domain_canonicality_v1 import (
    install_native_value_domain_canonicality_v1,
)
from .object_space_value_domains_v1 import (
    check_native_value_domain_object_space,
    is_native_value_domain_graph_secret,
)


_INSTALLED = False


def check_object_space_graph_with_native_value_domains(project):
    if is_native_value_domain_graph_secret(project.graph_secret):
        return check_native_value_domain_object_space(project)
    return check_object_space_graph_with_native_relationships(project)


def install_native_value_domain_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    install_native_value_domain_canonicality_v1()
    install_native_value_domain_backend_alignment_v1()
    _check.check_object_space_graph = check_object_space_graph_with_native_value_domains
    _commands.check_object_space_graph = check_object_space_graph_with_native_value_domains
    _INSTALLED = True