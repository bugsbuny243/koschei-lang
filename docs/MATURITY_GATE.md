# Koschei Language Maturity Gate

`ks maturity` converts integration and release claims into a deterministic evidence check.

The command reads a strict `koschei.maturity-evidence.v1` JSON file and evaluates one of three targets:

- `incubation`: compiler tests, repository truth and capability-security evidence;
- `reference`: adds language stability, package integrity, reproducible builds, backend parity and real programs;
- `production`: adds stable ABI, foreign-boundary parity, fuzzing, adversarial tests, rollback and explicit owner approval.

## Usage

```bash
ks maturity \
  --evidence configs/maturity/incubation.v1.json \
  --target incubation
```

The command returns machine-readable `koschei.maturity-report.v1` JSON.

Exit codes:

- `0`: every required check for the selected target passed;
- `2`: the evidence file is malformed or contains unsupported claims;
- `3`: the evidence is valid but incomplete for the selected target.

Passing `incubation` or `reference` never authorizes production integration. The report sets `production_integration_allowed` only when the `production` target passes every requirement, including `owner_approval`.

## Evidence discipline

The v1 command accepts booleans rather than trying to discover all CI artifacts itself. CI and release tooling should generate the evidence file only after the corresponding test or audit succeeds. Missing checks are false. Unknown checks and non-boolean values fail closed.

The report includes a SHA-256 digest of canonicalized evidence so the exact input used for a claim can be retained with release artifacts.
