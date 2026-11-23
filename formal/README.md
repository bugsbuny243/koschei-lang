# Formal models

TLA+ models of the security rules Koschei's 1.0 claims depend on, checked with
TLC (tla2tools 1.8.0, sha256 pinned in `.github/workflows/formal.yml`).

| Model | Rule | Status |
|---|---|---|
| `tla/PackageUpdate.tla` | `ks pkg sync` update rule | checked |
| `tla/RegistryLog.tla` | `registry_v1.fetch_package` + `check_log` | checked; found a gap, fixed |
| `tla/BrokerConfinement.tla` | native broker request loop | checked; found a gap, fixed |

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

## BrokerConfinement

The worker is honest or compromised. A compromised worker is still under seccomp,
but it can send any frame on its broker socket. The model covers the scope
table, reference-counted release, read-only scopes and which requests the broker
serves.

Properties checked:

1. **Confinement**: the broker performs only effects the compiled program was
   granted.
2. **NoWriteThroughReadOnly**: nothing is written through a read-only scope.
3. **NoStaleScope**: a released scope is never used again.

**What it found:** before this model the broker served disk and environment
requests to any worker that had a broker at all. A compromised worker of a
read-only, or even a network-only, program could ask for a writable scope or
read any environment variable, secrets included. TLC gave the counterexample.
`tests/test_broker_grants_v1.py` reproduced it on a real binary, and both tests
failed before the fix. The broker now serves only the authority the compiler saw
the program create (`mir_go_native._broker_grants`). TLC finds no error for any
grant set, and switching any one of the three checks off gives a counterexample.

Limits: seccomp, Go memory safety and the path rules inside a scope
(`O_NOFOLLOW`, `..`) are trusted, not modelled. Scope *prefixes* are not limited.
A program holding `DiskRoot` may narrow to any directory, as in `ks run`. The
bounds are 2 scopes and 6 requests. The net, serve and persist hooks are not in
the model yet.

## RegistryLog

The registry serves any log and any index entry. The hash chain (`parse_log`)
makes "the hash at the pinned position matches" equivalent to "the log extends
the pinned prefix", provided SHA-256 is collision resistant. So the model
compares prefixes directly.

Properties checked:

1. **NoHiddenYank**: a version the public log records as yanked is never newly
   installed. A lock that already holds it keeps it, as documented.
2. **LockedIsLogged**: what a client locks is the last version the public log
   records as published.
3. **HistoryMonotonic**: a log that drops or rewrites the pinned history is
   refused.

**What it found:** the client read yanks only from the index, never from the
log. A registry could therefore hide a yank. For example, after an owner yanked
a compromised release, an index rolled back to before the yank still served
that release as fresh to new installs, although the log recorded the yank. The
client now derives yank state from the log and refuses an index that disagrees
with it in either direction. `tests/test_registry_v1.py` reproduces both cases
and failed before the fix.

Run locally:

```
KOSCHEI_TLA2TOOLS=/path/to/tla2tools.jar python -m unittest -v tests.test_formal_models_v1
```
