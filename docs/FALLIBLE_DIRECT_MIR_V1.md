# Fallible Direct MIR Service Contract v1

This contract moves a real Koschei service graph further away from AST
compatibility execution and into explicit normalized MIR behavior.

It is stacked on Direct MIR Modules v1. The production-reference workload is the
acceptance target; features are not removed from that workload merely to make the
direct executor pass.

## `or return` normalization

`value or return [replacement]` no longer needs an `MirAstFallback` in this
contract. Lowering emits explicit control flow:

1. evaluate the fallible value once;
2. test whether the value is an Error;
3. on failure, return either the original Error or the explicit replacement;
4. on success, unwrap the value on the success edge and continue.

The initial direct-MIR runtime contract covers Error-union propagation. Option and
Result remain outside this slice because enum execution is still an explicitly
unsupported direct-MIR surface.

## Bounded Data JSON

`parse_json(String)` and `encode_json(Data)` are available to the direct executor
through the existing bounded `data-json/v1` implementation. Data stays opaque;
printing a Data value is not a public language operation and the runtime string
view is redacted as `<data>` for defense in depth.

## Deterministic parallel List shape

Normalized MIR represents List as an immutable tuple-shaped runtime value. The
`parallel_map` direct adapter now accepts that normalized representation and
returns the same representation, so its result can feed MIR iterators without a
host list/tuple ABI split.

This does not weaken the existing scalar/capability checks around parallel workers.

## Integer division

The direct runtime implementation uses the same integer division arithmetic as the
aligned interpreter/native backends: Int / Int truncates toward zero, zero is an
Error, and `INT_MIN / -1` is signed-64 overflow.

Admission is intentionally narrower than the runtime implementation in v1. The
direct-MIR support inspector accepts division only when the denominator is a
compile-time numeric constant that is non-zero. Int division by `-1` additionally
requires a compile-time numerator proven not to be `INT_MIN`. Dynamic divisors
remain unsupported until fallible arithmetic and function-return runtime contracts
are fully normalized.

This conservative rule is sufficient for the production-reference fee path, whose
denominator is the literal `10000`, without claiming unsafe dynamic division is
already AST-free production surface.

## Interpolated strings

Interpolated strings lower to one normalized MIR instruction whose input values
are explicit MIR dependencies. Rendering uses Koschei runtime string semantics;
it does not reopen or evaluate the source AST.

## Production-reference gate

The `order_worker` package in `examples/production_reference_v1` has an 11-module
transitive graph. The twelfth workspace member, `market_feed`, is deliberately not
a dependency of the worker because its network authority must stay outside the
capability-free order-processing core.

The direct-MIR acceptance test requires the full 11-module worker graph to:

1. pass semantic checking;
2. report no unsupported direct-MIR instructions;
3. execute through `run_mir_native()` only; and
4. produce byte-for-byte the same deterministic reference output, including
   settlement arithmetic, canonical JSON and structured parallel dispatch.

## Non-claims

This contract does not mean every Koschei construct is direct-MIR executable.
Structs, enums, arbitrary value-member access, dynamic/fallible division, other
fallible operators and other explicitly unsupported MIR surfaces remain
fail-closed. The locked workspace runner also remains a separate compatibility
execution path until it is intentionally switched after equivalent coverage
exists.
