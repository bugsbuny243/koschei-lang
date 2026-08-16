# Koschei Native Relationships v1

Status: experimental native-language slice stacked on authenticated frontend identity.

A native relationship is not an import, namespace, module lookup, or filesystem edge.
A pure leaf Object Space object resolves one immutable Int64 witness reality. The sealed
relationship table may admit that one value into the root object's graph through a local
`conduit` slot.

The source knows only the local slot:

```text
witness remote conduit 0
witness fee 2
witness total sum remote fee
resolve total
```

The source does **not** name the target object, a file, module, package, path, extension,
or runtime namespace.

The sealed relation binds:

- random relationship identity;
- canonical root/source object identity;
- local conduit ordinal;
- canonical target object identity;
- exact target artifact digest;
- exact target frontend identity;
- issued and expiry Object Space epochs;
- authority ceiling;
- effect ceiling;
- maximum target witness count;
- maximum absolute resolved value.

v1 intentionally admits only zero authority and zero effect ceilings because the witness
kernel itself has no capability/effect surface. A non-zero ceiling would reserve authority
that no native source construct can justify and therefore fails closed.

Every non-root object must be exactly one related leaf and every source conduit must have
exactly one sealed relationship. Hidden relations, orphan objects, duplicate slots,
duplicate targets, root-as-target edges, stale relations, target digest/frontend mismatch,
and resource-ceiling violations fail closed.

v1 is deliberately a root-to-leaf star. Leaf-to-leaf or recursive relationship composition
is not silently mapped onto legacy `import`; it requires a later native relationship graph
semantics with explicit cycle/resource/authority propagation.

The current backend performs sealed compile-time value composition: leaf realities are
validated and resolved, their admitted values are materialized into the root graph, and
only the materialized root is lowered to the existing MIR compatibility backend. There is
no runtime module API or target-name lookup.

This design intentionally makes an ordinary `import` translation lossy: an import cannot
represent the sealed relationship id, exact artifact/frontend binding, temporal validity,
authority/effect ceilings, or resource ceilings that decide whether the value is admitted.
