# Platform foundation — four pure Koschei libraries

This is a working `.ks` CLI example for the independent Core Library
modules `platform_web`, `platform_web3`, `platform_ai`, and `platform_kernel`.
Every module is *only* a bounded, fail-closed admission helper.
It does not make an HTTP request, sign a transaction, run a model or access
a physical frame. `ks caps` reports no disk/network/serve/process authority.

```sh
ks check examples/platform_foundation_v1/main.ks
ks run examples/platform_foundation_v1/main.ks
ks build examples/platform_foundation_v1/main.ks -o /tmp/koschei-platform-foundation
/tmp/koschei-platform-foundation
```

Expected output:

```text
web=health denied=DENY
web3=block-number signed=DENY
ai=local-model denied=DENY
kernel-claimed=true forged=false
```

Read `docs/PLATFORM_FOUNDATION_V1.md` for exact implementation gates,
runtime/backend restrictions and what is *not yet supported*.
