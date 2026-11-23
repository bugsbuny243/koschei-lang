# Formal models

TLA+ models of the security rules Koschei's 1.0 claims depend on, checked with
TLC (tla2tools 1.8.0, sha256 pinned in `.github/workflows/formal.yml`).

| Model | Rule | Status |
|---|---|---|
| `tla/PackageUpdate.tla` | `ks pkg sync` update rule | checked |
| registry log hash chain | `registry_v1.check_log` | planned |
| broker confinement | native broker / `_ksAsk` protocol | planned |

## PackageUpdate

The attacker controls the registry: it publishes any version, lies about a
version's surface in the index, signs with its own key or not at all, and forks
or truncates the public log. It cannot forge the owner's key. The user runs
`sync` with any `--allow` set and `--allow-new-signer` flag.

Properties checked:

1. **NoSilentWidening**: a locked package never holds a capability the user did
   not consent to (adding the dependency, or `--allow`).
2. **IndexTruthful**: every locked version was listed with the surface the
   compiler computes.
3. **DenyHolds** / **SignedHolds**: `[policy] deny` and `require_signed` always hold.
4. **SignerPinned**: once signed, the lock moves to another signer (or to
   unsigned) only on a run with `--allow-new-signer`.
5. **HistoryMonotonic**: a forked or truncated registry log is never accepted.

Every check in the implementation is a switch in the model. With all switches on
TLC finds no error (735,613 distinct states). With any one switched off TLC finds
a counterexample to the property above that depends on it. So every check is
needed, and the properties are not vacuous. `tests/test_formal_models_v1.py` runs
all of this. It also fails in normal CI if the code drops a modelled check.

### What this does not show

- This is a model of the rule, not a proof of the Python code. The link test only
  checks that each modelled check is still present in the code.
- The bounds are small: one package, capabilities `{disk, net}`, and a log of at
  most 2 records. Signature cryptography, hash collisions and the surface
  computation itself are trusted, not modelled.
- `IndexTruthful` is defence in depth. The lock always stores the compiler's
  surface, whatever the index says.

Run locally:

```
KOSCHEI_TLA2TOOLS=/path/to/tla2tools.jar python -m unittest -v tests.test_formal_models_v1
```
