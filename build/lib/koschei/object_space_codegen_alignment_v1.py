"""Align native MIR flattening with Koschei graph identity.

The legacy native flattener historically keyed modules by ``str(module.path)``.
That assumption is invalid once authenticated Object Space uses canonical object
identity while ``Module.path`` is diagnostics-only.  This installer keeps the
existing backend implementation but feeds it a path-free identity view whose
internal names are deterministic per dependency order and do not embed stable
Object Space ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import codegen_go as _go


_INSTALLED = False
_ORIGINAL_FLATTENER = None


@dataclass(frozen=True, slots=True)
class _ModuleView:
    key: str
    path: Path
    name: str
    program: Any
    imports: Any


class _GraphView:
    def __init__(self, root: str, ordered: tuple[_ModuleView, ...]) -> None:
        self.root = root
        self._ordered = ordered

    def in_dependency_order(self) -> list[_ModuleView]:
        return list(self._ordered)


def _identity_aligned_flatten(graph: object):
    assert _ORIGINAL_FLATTENER is not None
    ordered = tuple(graph.in_dependency_order())
    if not ordered or not all(isinstance(getattr(module, "key", None), str) for module in ordered):
        return _ORIGINAL_FLATTENER(graph)

    root = getattr(graph, "root", None)
    if not isinstance(root, str):
        return _ORIGINAL_FLATTENER(graph)

    keys = tuple(module.key for module in ordered)
    if len(set(keys)) != len(keys) or root not in set(keys):
        return _ORIGINAL_FLATTENER(graph)

    # The existing flattener is otherwise correct.  Give it an identity view in
    # which its historical path-key lookup equals the sealed graph key, and make
    # non-root internal prefixes order-derived rather than object-id-derived.
    views: list[_ModuleView] = []
    for index, module in enumerate(ordered):
        key = module.key
        views.append(
            _ModuleView(
                key=key,
                path=Path(key),
                name="root" if key == root else f"cell{index}",
                program=module.program,
                imports=module.imports,
            )
        )
    return _ORIGINAL_FLATTENER(_GraphView(root, tuple(views)))


def install_object_space_codegen_alignment_v1() -> None:
    global _INSTALLED, _ORIGINAL_FLATTENER
    if _INSTALLED:
        return
    _ORIGINAL_FLATTENER = _go._flatten_module_graph
    _go._flatten_module_graph = _identity_aligned_flatten
    _INSTALLED = True
