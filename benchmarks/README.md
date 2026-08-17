# Koschei security benchmark v1

This directory contains reproducible, machine-readable security measurements for Koschei. It exists to support issue #107 without turning project ambition into unsupported marketing claims.

The v1 harness measures what the current compiler can prove directly: capability grants, requested authority domains, exact-vs-dynamic scope, and capability-holder surface for a fixed corpus. Results are deterministic JSON and include the benchmark schema/version plus a SHA-256 digest of every source case.

Cross-language Rust/Go/Python/managed-language adapters are intentionally not fabricated here. They are added only when a reproducible adapter can measure the same semantic question. Until then the output identifies Koschei measurements as `native` and leaves cross-language comparison outside the claim surface.

Run:

```bash
python benchmarks/security_v1.py
python benchmarks/security_v1.py --json
```

The benchmark is a measurement harness, not a claim that Koschei is “100x safer”. Any future comparative claim must name the corpus, metric, denominator and reproduction procedure.
