# Koschei Lang 0.10.0 — Release Notes

**Product:** Koschei Lang (independent of Koschei Sentinel and Web3 Hub)  
**Version:** 0.10.0  
**Release line:** commercially licensed, pre-1.0 language/toolchain

## Included

- `ks check` — compile-time diagnostics and explicit capability checks.
- `ks caps`, `ks caps --deny <domain>` — whole-program
  capability manifest and CI policy, including imported `.ks` modules.
- `ks run` — checked interpreter.
- `ks build` — native build using the current Go backend adapter.
- `ks fmt`, `ks lsp`, `ks explain` — developer tools.
- Typed `Option` and `Result`, explicit errors, bounded
  String/List values and Koschei-authored Core Library modules.
- Shipped example apps for secret-pattern scanning and directory
  integrity snapshots, with read-only disk authority and no network.
- A non-executed supply-chain example: unauthorized disk usage
  in an imported module is rejected with `KS2401`.
- English and Turkish language guides, generated Core Library and
  error-code references, licensing and customer installation guide.

## Installation

The included `install.sh` targets Unix-like environments using a shell,
Python 3.12+ and a virtual environment. Go 1.24+ is required only
for native `ks build`.

```sh
./install.sh
ks version
ks run examples/hello.ks
ks check examples/supply_chain/main.ks # expected KS2401, exit code 1
```

Do not run arbitrary third-party installer scripts or
untrusted interview coding projects as a security test.
The installer does not make the host operating system a sandbox.

## Licensing

Personal non-commercial use is free. Commercial licenses are
one-time USD purchases: Individual $49 (one developer),
Team $249 (up to 10 developers) and Enterprise $999
(unlimited developers in one organization). Purchased releases
can be used perpetually; releases in the next 12 months
are included. The authoritative terms are in `LICENSE`,
`LICENSING.md` and their Turkish versions.

## Known limits

This is 1.0-predecessor software, not a completed self-hosted
compiler. The source interpreter and Go native adapter require
their documented host dependencies. Do not interpret Koschei
capability security as protection for arbitrary code executed
outside Koschei, compromised endpoints, stolen credentials,
AI agent misuse, on-chain signing or wallet custody.
No independent bank/exchange production certification is claimed.

## Release authenticity

Verify the supplied ZIP against the SHA-256 value delivered
through an independently authenticated publisher channel.
A hash supplied only alongside an untrusted download is not
proof of provenance. Customer updates, refund and support
arrangements are governed by the seller's published terms.
