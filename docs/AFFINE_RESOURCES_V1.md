# Affine Resources v1

Koschei's first ownership layer makes authority-bearing values **move-only**.

This is an assurance feature, not an ergonomics feature. The goal is to make it
harder for security-critical programs to accidentally duplicate live authority.

## Core rule

A capability-bearing binding may have at most one live owner.

Ordinary method invocation **borrows** the binding:

```ks
fn inspect(authority: NetCaps) {
    let first = authority.get("https://example.com/a") or return
    let second = authority.get("https://example.com/b") or return
}
```

Ownership transfer **moves** it:

```ks
fn handoff(authority: NetCaps) -> NetCaps {
    return authority
}

fn main(caps: SystemCaps) {
    let current = caps.net.allow("https://example.com")
    let next = handoff(current)

    // current is moved and cannot be referenced here.
    let response = next.get("https://example.com/status") or return
    println(response.status())
}
```

The following are move sites in v1:

- binding an affine value to another `let`
- passing an affine value as a function argument
- returning an affine value
- placing an affine value into an aggregate field
- extracting an affine field as an owned value

A move followed by use fails with `KS3931`.

## Structural sensitivity

Affine classification comes from Typed HIR structural types. It is not a list of
variable names.

Direct capability types are affine, and a struct containing an affine field is
affine as well:

```ks
struct SettlementAuthority {
    authority: NetCaps
}
```

Moving `SettlementAuthority.authority` conservatively moves the whole owner in
v1. Partial moves/borrows are a later ownership feature.

## Root projection

`SystemCaps` remains the unique runtime-injected authority root. Projecting a
specific root such as `caps.net` or `caps.disk` does not consume the complete
`SystemCaps` handle. The projected root value itself is affine and cannot be
copied into multiple live owners.

## Mutable affine bindings

`let mut` on an affine resource is rejected with `KS3930`.

This keeps ownership transfer explicit while the language does not yet have a
full borrow/reassignment checker.

## Control-flow join

V1 is conservative:

- if an outer affine binding is moved in either branch, it is unavailable after
  the branch join;
- moving an outer affine binding from a repeating `while`/`for` body is rejected
  with `KS3932` because another iteration could double-move the same owner.

Later borrow-checking work may prove more programs safe, but v1 never guesses in
favor of aliasing authority.

## Affine, not linear

Affine means **at most once**: a resource may be dropped without consumption.

Future transaction/settlement resources will also need **linear** contracts —
for example a transaction handle that must end in exactly one of `commit` or
`abort`. That stronger exactly-once property is deliberately separate from this
first ownership layer.

## Security boundary

Affine Resources v1 is a compile-time ownership gate run after Typed HIR and
before legacy semantic/MIR lowering. It does not claim memory safety for
arbitrary FFI code and it does not implement revocation by itself.

It establishes the ownership invariant needed by later:

- capability delegation/revocation,
- transaction typestate,
- linear settlement handles,
- isolated FFI resources,
- deterministic distributed execution handles.
