# Typestate Resources v1

Koschei typestate makes protocol state part of a resource's type and seals
non-initial state construction behind compiler-validated transitions.

This is a general high-assurance language mechanism. Settlement is one proof
workload; the same mechanism is intended for authenticated sessions, order
lifecycle handles, recovery protocols, custody operations and other state
machines where invalid calls should fail before execution.

## Declaration

A v1 stateful resource has one state axis, an explicit initial state and a
physical `state: S` marker field:

```ks
struct Open {}
struct Closed {}

stateful struct Session<S> starts Open {
    id: String,
    state: S,
}
```

State markers are zero-field, non-generic, non-stateful structs. They carry no
ambient authority and exist to make state identity structural in Typed HIR.

## Initial construction

Only the declared initial state may be constructed directly from an ordinary
function. This fragment depends on the `Open` / `Session` declarations above:

<!-- verify: skip — fragment depends on declaration block above -->
```ks
fn new_session(id: String) -> Session<Open> {
    return Session { id: id, state: Open {} }
}
```

Trying to directly construct `Session<Closed>` outside a transition is rejected
with `KS3953`. This prevents typestate from degrading into a forgeable runtime
tag.

## Transition

A state change is explicit. This fragment also depends on the declaration block
above:

<!-- verify: skip — fragment depends on declaration block above -->
```ks
transition fn close(session: Session<Open>) -> Session<Closed> {
    return Session { id: session.id, state: Closed {} }
}
```

The compiler validates that a v1 transition:

- has exactly one direct stateful source parameter;
- returns the same stateful resource family in a different concrete marker;
- emits exactly one stateful target literal;
- emits that target directly from the final `return`;
- does not move/alias/pass the complete source owner somewhere else while also
  minting the target state;
- may borrow source fields while constructing the target.

`pure transition fn` is valid syntax. Purity remains independently enforced by
the effect system; transition syntax does not grant an effect exemption.

## Ownership composition

Every stateful resource is affine through the A0 ownership checker.

Calling `close(open)` moves the `Session<Open>` owner into the transition. The
caller cannot use `open` again. Passing the resulting `Session<Closed>` to a
function that expects `Session<Open>` is a structural type error.

A normal user struct containing a stateful field becomes affine as a whole. In
v1, moving the stateful field conservatively moves the owner aggregate. Partial
borrows/moves are future ownership work.

## Constructor sealing

The initial-state rule and `transition fn` rule are both necessary.

A generic type such as `Resource<Open>` / `Resource<Closed>` without constructor
sealing would still allow a programmer to write a `Closed` literal directly and
bypass the intended state machine. Koschei rejects that shortcut.

Typestate v1 is therefore not merely a phantom generic convention: the compiler
knows which declarations are stateful, which marker is initial and which
functions are state transitions.

## Container boundary

The following are intentionally rejected in v1:

- `List<Resource<Open>>`
- `Map<String, Resource<Open>>`
- `Option<Resource<Open>>`
- `Result<Resource<Open>, ...>`
- `BoundedQueue<Resource<Open>>`
- enum payloads carrying a stateful resource

Those containers do not yet expose move-aware element extraction / match payload
ownership. Allowing them early would create an alias/partial-move escape hatch.
User-defined owner structs are allowed because extracting a stateful field moves
the complete owner under A0.

## What v1 proves

- invalid state arguments fail structural type checking;
- non-initial direct constructor forgery fails;
- a source owner cannot transition twice;
- transition source and target must be the same resource family;
- transition source cannot escape while a new target state is minted;
- stateful resource aliases obey affine ownership;
- interpreter and native execution agree for the proof workload.

## What v1 does not yet prove

Typestate is not yet a full linear transaction protocol.

Still required for later high-assurance gates:

- exactly-once linear termination such as commit **or** abort;
- path-sensitive transitions with multiple validated terminal returns;
- move-aware containers and pattern payloads;
- multi-axis protocol state where it is justified;
- durable transaction identity / WAL / recovery semantics;
- information-flow labels on state and transition data;
- delegated/revocable authority bound to protocol state.

The A2 foundation established here is narrower: **state identity is in the type,
non-initial state cannot be forged, and transitions compose with affine
ownership.**
