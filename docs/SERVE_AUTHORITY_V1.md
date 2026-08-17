# Serve Authority v1

Koschei cannot grow into a real backend language by treating server sockets as
ambient process authority. Before a listener exists, the authority to create one
must be explicit, narrow and measurable.

This is a **bootstrap compatibility surface**, not the final Koschei-native grammar
or project vocabulary.

## Authority shape

A `main(caps: SystemCaps)` may access one additional root:

```text
SystemCaps.serve -> ServeRoot
```

The root performs no I/O. It may only be narrowed to a `ServeCaps` token with one
exact policy:

```text
caps.serve.allow(bind, max_connections, max_request_bytes,
                 max_response_bytes, deadline_ms)
```

`ServeCaps` itself exposes **no listener operation in v1**. That is intentional.
The next listener slice must consume this token rather than inventing an ambient
socket API.

## Exact-policy requirement

Every v1 policy field must be a compile-time literal. Dynamic listener scope is
rejected with `KS2410` because the capability manifest would otherwise be unable
to state the process attack surface exactly.

The policy binds all of:

- exact host and port;
- maximum concurrent connections;
- maximum request bytes;
- maximum response bytes;
- request deadline in milliseconds.

## Loopback-only bootstrap

The initial authority accepts only explicit loopback hosts:

- `localhost`
- addresses in `127.0.0.0/8`
- IPv6 `::1`

The port must be in `1..65535`.

Wildcard and public interfaces such as `0.0.0.0` are rejected with `KS2411`.
Public ingress needs a separate reviewed authority contract; it is not smuggled
into the first listener implementation.

## Hard budget envelope

The provisional upper bounds are:

- connections: `1..4096`
- request bytes: `1..16777216`
- response bytes: `1..16777216`
- deadline: `1..120000` ms

These are security limits, not tuning hints. A token outside the envelope is not
created.

## Manifest evidence

For:

```text
caps.serve.allow("127.0.0.1:8080", 64, 65536, 65536, 5000)
```

the capability manifest records one exact `serve` grant containing the bind and
all four budgets. The grant is therefore reviewable without executing the
program.

## Capability type integrity

`ServeRoot` and `ServeCaps` are sensitive capability types. They cannot be hidden
inside untyped/erased List or Map payloads. The interpreter also recognizes the
runtime values as capability-bearing tokens.

A function may receive `ServeCaps` only through an explicit parameter contract.

## Backend fail-closed rule

The interpreter can create and pass the bounded token, but v1 deliberately has no
listener ABI.

Native Go generation rejects every program that uses the provisional Serve
authority with `KS4001`. It must not generate a binary whose `SystemCaps` silently
lacks the field or whose listener semantics differ from the interpreter.

Native support may be enabled only in the listener PR that implements the same
bind and budget contract in that backend.

## Non-claims

This contract does not open a port, accept a request, route HTTP, expose public
interfaces, or claim production server readiness. It establishes the authority
envelope that those operations must obey.
