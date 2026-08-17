# Secure Alpha — A1 status

Parent: #240

Current canonical execution debt is intentionally measured, not hidden.

- Public compatibility entrypoints: 6
- Native IR / authenticated authority entrypoints: 5
- Public `ks check`, `ks run`, `ks build`: still compatibility migration debt
- Authenticated Object Space -> Native IR: available
- Canonical native check/run over authenticated Object Space: available
- Explicit trusted-session authority admission -> canonical native check/run: available

## Next reduction

The next slice must reduce compatibility debt by migrating one public entrypoint. `ks check` is the safest first public migration because it does not require runtime budget/execution semantics. It must consume only an explicitly supplied trusted authority session/broker capability; it must never infer native mode from filenames, k0/k1 layout, source bytes, parser success, or project metadata.

After `ks check` is proven on exact-head validation, migrate `ks run`, then native build authority. Compatibility deletion comes only after equivalent native coverage and parity/security gates exist.
