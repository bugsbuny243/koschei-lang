# Koschei package registry

Served as static files at `https://koschei.dev/registry/`. Nothing here runs:
`index/<name>.json` lists versions with their digests and capability
surfaces, and `archives/<name>/<name>-<version>.tar` holds each version's
`.ks` sources and `koschei.toml`.

To publish, check out this repository and run

```sh
ks pkg keygen ~/.koschei/publisher.key     # once
ks pkg publish path/to/your-package --registry registry --key ~/.koschei/publisher.key
```

then open a pull request with the files it wrote (archive, index, log). `ks pkg publish`
refuses a version that already exists, a name one edit away from an existing
one (until a maintainer reviews it), a package that does not type-check or
takes `SystemCaps`, and a stated surface that differs from the computed one.
Clients recompute the surface from the sources and refuse a package whose
index entry disagrees.

Every publish, sign and yank is appended to `log.jsonl`, a hash-chained
public log. New versions are signed (`ks pkg publish --key`); the first
signer of a package becomes its owner.

Rules: versions are immutable and never deleted; `ks pkg yank` hides one from
new installs. See `docs/PACKAGES_V1.md`.

## Packages

| Package | Version | Surface | What it does |
|---|---|---|---|
| `hexfmt` | 1.0.0 (unsigned, from before signatures) | pure | `pad_left`, `pad_right`, `to_hex`, `parse_hex` |
| `base64` | 1.0.0 (unsigned) | pure | RFC 4648 `encode`, `encode_bytes`, `decode`, `decode_text` |
| `semver` | 1.0.0 (unsigned) | pure | `parse`, `compare`, `is_compatible`, `to_text` for MAJOR.MINOR.PATCH |

`tests/test_registry_contents_v1.py` checks on every pull request that each
archive matches its index entry and that each listed surface is the one the
compiler computes.
