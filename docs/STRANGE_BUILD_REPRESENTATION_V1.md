# Strange Native Representation v1

Status: **implemented opt-in compiler projection prototype; NOT production protection**

Koschei Lang's canonical MIR and its Library/Universe authority contracts remain
unchanged. A trusted builder may call
`generate_go_mir_native(mir, representation_seed=seed)` with an independent,
32-byte-or-longer deployment seed to produce deterministic, opaque Go function
and parameter identifiers. Equal MIR + equal seed yields equal generated Go;
equal MIR + distinct seed yields different symbol representations.

## Invariants

- The public `ks build` / `ks emit-go` interface remains unchanged and unseeded.
- The seed is **not** read from source, CLI flags, environment variables, or a
  source-level capability. Future deployment must obtain it from the Trust Plane.
- Opaque symbols do **not** replace canonical MIR identity, Veyra, Aevra,
  authorization, execution proofs, or signed artifact provenance.
- Name diversification cannot create execution authority or bypass compiler
  checks. The generator still rejects unsupported MIR; no AST fallback.
- This is **only symbol diversification**, not source encryption, a fresh epoch,
  runtime code mutation, memory isolation, or proof of anti-reversing resistance.
- Diagnostic strings, literals, and other runtime metadata may still reveal
  names or meaning. Real code can still be reverse-engineered.
- No automatic two-minute timer is present. Wall-clock time and representation
  expiry must be bounded by a trusted deployment epoch contract and established
  release/restart/rollback behavior rather than by rotating labels alone.

## Acceptance tests

`python -m unittest discover -s tests -p 'test_strange_build_representation_v1.py' -v`

The tests check same-seed determinism, different-seed diversification,
domain separation, malformed seed denial, canonical MIR stability, and native
output parity when Go is installed.

## Next gates (not complete)

1. Bind seed provenance, build input, version, deployment, and epoch to an
   authenticated representation-equivalence receipt; do not expose seed.
2. Eliminate diagnostic and symbol-table leakage on the protected build path
   without changing canonical language behavior.
3. Add real separate Trust Plane custody and deployment-specific seed storage.
4. Establish expiry/replay invalidation for observer/code *representations*
   and test safe rotation across in-flight requests, restarts and rollbacks.
5. Independently verify that compromise of one deployment cannot create
   authority for another; test executable artifacts, not only HMAC labels.

Related: `docs/design/GORUNMEZ_DEGISEN_KOD_V1.md` and
`KOSCHEI_WEB4_WEB10_ARCHITECTURE_ROADMAP_V1.md`.
