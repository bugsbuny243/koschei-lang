"""Backend alignment for closed Koschei native value-domain graphs.

Native value graphs are completely closed and are already evaluated under the
frontend's domain, overflow, Unicode canonicality, and resource rules before MIR
lowering.  The legacy compatibility backend must therefore not reinterpret
native operations with host-style ``+``/``==`` semantics: doing so can change a
canonical glyph value at an operand boundary.

This alignment materializes each *proven* canonical witness value into the
compatibility AST while retaining dependency order and witness identities for
compiler diagnostics/MIR shape.  It is constant materialization, not an implicit
source-language coercion.
"""

from __future__ import annotations

from . import native_value_domains_v1 as _domains


_INSTALLED = False


def _lower_canonical_value_graph(
    graph: _domains.NativeValueGraph,
    values: dict[str, _domains.NativeValue],
):
    by_name = graph.by_name()
    statements = []
    for name in _domains.dependency_order_value_graph(graph):
        witness = by_name[name]
        value = values[name]
        statements.append(
            _domains.LetStatement(
                witness.name,
                False,
                _domains._lower_value(value, witness.location),
                witness.location,
                _domains._type_ref(value.domain, witness.location),
            )
        )

    statements.append(
        _domains.ReturnStatement(
            _domains.Identifier(graph.resolve, graph.resolve_location),
            graph.resolve_location,
        )
    )
    resolved = values[graph.resolve]
    origin = _domains.GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=_domains._type_ref(
            resolved.domain,
            _domains.SourceLocation(1, 1),
        ),
        body=_domains.Block(tuple(statements)),
        location=_domains.SourceLocation(1, 1),
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    return _domains.Program((origin,))


def install_native_value_domain_backend_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _domains.lower_native_value_graph = _lower_canonical_value_graph
    _INSTALLED = True
