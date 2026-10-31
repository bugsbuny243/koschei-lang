# Strange Representation Epoch v1 — bootstrap builder contract

**Status: opt-in issuer prototype only; no production rotation / hardware Trust Plane.**

The visible representation can vary while the canonical MIR/Library identity
remains stable. The `project_strange_epoch_go_v1` function uses an external
seed, a typed Continuity epoch and an external seconds reader to derive opaque
MIR-Go identifiers for an exact deployment, Veyra and 120-second window.

## Security boundaries

- Both the Continuity epoch and seconds reading MUST come from a hardened,
  monotonic, rollback-resistant Trust Plane for production. The Python callbacks
  here do not themselves authenticate hardware or protect against forged time.
- Time intervals are half-open: `[starts_at_seconds, starts_at_seconds + 120)`.
  T=119 is valid, T=120 fails closed **at build-issue time only**.
- A slow build is checked again after generation. If epoch/time changed, the
  result is discarded; no admission or deployment is granted.
- The root seed MUST be private Trust Plane material, never derived from a
  clock value or readable filename, passed through CLI/environment or shipped
  inside the generated Go. It is a representation-diversity seed, not a
  custody/signing key or an execution authority.
- The receipt is a builder-only source digest, not proof of physical separation,
  semantic equivalence, hardware isolation, or runtime expiry.
- There is no automatic two-minute runtime code change, safe cutover, secret
  storage, binary obfuscation, signed deployment manifest, or HSM integration.
- An old binary is **not rendered inert** by this prototype. Real runtime
  fencing, independent signing policy and process replacement are required.

## Tests

`python -m unittest discover -s tests -p 'test_strange_representation_epoch_v1.py' -v`

Coverage: same context determinism, cross-deployment/Veyra/epoch separation,
119/120-second boundary, stale/future epochs, unreadable time source,
and epoch race during source generation.

This is the first non-authoritative, auditable part of
[Issue #317](https://github.com/bugsbuny243/koschei-lang/issues/317). Production
admission remains blocked by that issue's Trust Plane and runtime gates.
