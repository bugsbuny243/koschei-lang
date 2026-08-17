# Direct MIR Type Integrity v1

Koschei's direct MIR executor is an AST-free runtime path. Static checking remains
the first line of defense, but a supported runtime boundary must not trust host
values or Python's numeric representation merely because the source graph was
checked earlier.

This contract adds defense-in-depth for the direct-native representations that v1
can currently prove.

## Checked runtime boundary

Before a direct MIR function body executes, supported parameter values are checked
against the structural type sealed into the `MirFunction`. After the function
returns, its value is checked against the sealed return type.

The v1 runtime checker has explicit representations for:

- `Void`
- `Bool`
- `Int`
- `Float`
- `String`
- `Error`
- opaque `Data`
- normalized `List<T>`
- unions composed from those types

Unknown/type-variable/custom aggregate representations are not invented by this
bridge. Structs and enums remain outside the direct-MIR support surface until their
own representation contracts are sealed.

The root `main` function retains one intentional process-error edge: a returned
`Error` may reach `run_mir_native()`, which converts it to `MirNativeProgramError`.
That does not authorize ordinary functions declared as `Int`, `String`, etc. to
return an Error silently.

## Signed 64-bit Int

Direct MIR no longer inherits Python's unbounded integer behavior for Koschei
`Int` arithmetic.

For `Int + Int`, `Int - Int`, and `Int * Int`:

- results inside the signed 64-bit range remain `Int`;
- results outside the range become a `KS3501` Error value;
- a function declared as plain `Int` cannot return that Error through its runtime
  type boundary;
- a function explicitly declared as `Int or Error` may propagate the Error into
  normal Koschei fallible control flow.

Unary negation of `INT_MIN` follows the same checked overflow rule.

Division remains governed by the narrower Direct MIR division admission contract:
only proven-safe constant denominators are currently admitted.

## Runtime host-value defense

The executor's private call boundary also rejects a host value that does not match
a supported parameter type. This is defense-in-depth for backend/adaptor mistakes;
it is not a substitute for source semantic checking.

## Production-reference compatibility

This contract is stacked on the fallible direct-MIR production service work. The
existing 11-module `order_worker` direct-MIR acceptance gate must remain green: the
new boundary checks may expose hidden representation drift, but the workload must
not be weakened to avoid those checks.

## Non-claims

This does not make every Koschei type direct-MIR executable. Generic aggregates
other than `List<T>`, custom structs, enums, capabilities and future resource types
need explicit sealed runtime representations before this checker may claim them.
