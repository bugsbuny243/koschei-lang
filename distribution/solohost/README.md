# Koschei Lang on Pi SoloHost

Status: **sealed-release pipeline in progress — not yet a public SoloHost artifact**

This directory defines the Pi Desktop / SoloHost distribution boundary for Koschei Lang. It remains outside language semantics and must not turn Pi-specific code into a dependency of the compiler core.

## Commercial model

The initial product model is a **one-time Pi purchase**. There is no monthly subscription requirement. The exact Pi price is external commercial configuration and must not be hard-coded into the compiler or release artifact.

See `commercial/PI_SOLOHOST_ONE_TIME_LICENSE_V1.md`.

## Distribution rule

The current bootstrap compiler is packaged as Python. A naive container that copies the repository would expose proprietary compiler/runtime source. The public SoloHost package therefore consumes a **sealed customer executable**, never a source checkout.

The separate Go `native/datajson` source is a build/repository asset and is not included as customer data. The current `ks build` implementation invokes a Go toolchain available on the executing system. Therefore a full SoloHost development environment must provide a compatible Go toolchain as a third-party runtime/build dependency without copying Koschei Go source into the customer artifact.

## Intended release chain

```text
private koschei-lang repository
        |
        v
owner-controlled Nuitka bootstrap build
        |
        +--> narrow canonical CLI entry
        +--> no repository data-dir inclusion
        +--> source-leak scan
        |
        v
functional/security smoke gate
        |
        +--> version / check / run / caps
        +--> KS2401 supply-chain denial
        +--> required native build with Go
        +--> binary SHA-256-bound smoke receipt
        |
        v
source-free executable
        |
        v
SoloHost staging assembler
        |
        +--> verifies same binary bytes were smoked
        +--> verifies binary-reported version
        +--> records full source commit
        +--> executable SHA-256
        +--> smoke receipt SHA-256
        +--> one-time-Pi commercial marker
        |
        v
owner-held Ed25519 release signature
        |
        +--> detached signature
        +--> public-key-derived key id
        |
        v
fail-closed publication verification
        |
        v
SoloHost container/package
        |
        +--> sealed Koschei executable
        +--> compatible Go toolchain for `ks build`
        +--> Pi identity/payment entitlement adapter
        |
        v
Pi Desktop user installs and runs locally
```

## Required properties of a public SoloHost artifact

A publishable artifact MUST:

- contain a runnable Koschei CLI/toolchain entrypoint;
- contain no private Git metadata;
- contain no `koschei/*.py` compiler source;
- contain no Python bytecode or Koschei `.go` source;
- contain no internal test tree;
- contain no owner credentials, payment secrets, wallet private keys, signing private keys, or CI secrets;
- contain no private build-only contracts unless explicitly designated customer-facing;
- carry an immutable version identifier;
- carry a digest that can be checked before publication;
- carry an Ed25519 signature whose signer is anchored outside the artifact;
- keep Pi identity/payment integration outside Koschei language semantics;
- preserve local-first execution for supported operations.

## Release trust anchor

A detached signature does not establish authenticity by itself. If a release ZIP contains
its manifest, signature, and public key, an attacker who can replace the whole ZIP can
replace all three. Therefore an artifact-bundled public key is **transport metadata, not
the production trust anchor**.

Before public sale, the owner release public key (or its `ed25519-sha256:` key id) must be
pinned through an independent official channel controlled separately from the artifact
bytes, for example the official Koschei site/release trust page. Customers and the
publication pipeline must obtain the trusted key from that channel, not learn it only
from the ZIP being checked.

The production publication verifier intentionally requires that external key:

```bash
python tools/verify_solohost_artifact_v1.py \
  <artifact-directory> \
  --trusted-public-key /secure/out-of-band/koschei-release-public.pem
```

The verifier then fails closed unless all of the following hold:

- source/private-file boundary checks pass;
- the release manifest schema/product/channel are valid;
- the manifest is marked `SIGNED` with the expected Ed25519 scheme;
- the manifest-bound executable exists and its byte size and SHA-256 match;
- the manifest signer key id equals the independently supplied trusted key id;
- the detached manifest signature verifies against that trusted key.

The production signing private key must never be committed to this repository or shipped
inside the customer artifact.

## SoloHost beta assumptions

Pi currently describes SoloHost as an open, permissionless self-hosted application framework with structural package checks. Because the beta package format can change, this repository does **not** invent a Pi publisher manifest schema.

When the publisher UI/exported package schema is observed, its exact manifest will be added under this directory without changing the compiler core.

## Release procedure

### 1. Build standalone first

Nuitka is bootstrap deployment tooling only; it is not a Koschei language dependency. The builder refuses release-controlled output/mode overrides and refuses Nuitka data-inclusion switches that could copy repository source/data into the customer distribution.

```bash
python tools/build_solohost_binary_v1.py \
  --mode standalone \
  --output /secure/build/koschei-standalone
```

Nuitka's recommended workflow is to prove standalone mode before onefile because missing dependency/data problems are easier to diagnose there.

### 2. Smoke the standalone executable

First prove the compiled CLI still behaves like Koschei:

```bash
python tools/smoke_solohost_binary_v1.py \
  /secure/build/koschei-standalone/<dist>/ks
```

For a SoloHost release candidate, native build is mandatory and the smoke receipt must be retained. The release/container environment must expose `go`:

```bash
python tools/smoke_solohost_binary_v1.py \
  /secure/build/koschei-standalone/<dist>/ks \
  --require-native-build \
  --receipt /secure/evidence/koschei-standalone-smoke.json
```

The smoke gate requires:

- `ks version --json` succeeds and reports `koschei-lang` plus a non-empty version;
- `ks check examples/hello.ks` succeeds;
- `ks run examples/hello.ks` succeeds;
- `ks caps examples/hello.ks` succeeds;
- the supply-chain attack example still fails with `KS2401`;
- `ks build` produces an executable and that executable runs successfully;
- the receipt records the exact tested binary SHA-256 and size plus Go toolchain identity.

### 3. Build onefile customer executable

Only after standalone passes:

```bash
python tools/build_solohost_binary_v1.py \
  --mode onefile \
  --output /secure/build/koschei-onefile
```

Run the full smoke gate again against the exact onefile binary that will be staged:

```bash
python tools/smoke_solohost_binary_v1.py \
  /secure/build/koschei-onefile/ks \
  --require-native-build \
  --receipt /secure/evidence/koschei-onefile-smoke.json
```

Ordinary compiled binaries are not claimed to be impossible to reverse engineer. Stronger commercial IP-hardening remains a separate release decision. The V1 boundary is: no raw proprietary Python/Go source in the customer package, digest-bound release bytes, owner signature, and functional/security parity.

### 4. Assemble unsigned staging from proven bytes

The assembler refuses untested/different bytes, a mismatched release version, an incomplete smoke receipt, or a short/unrecorded source commit.

```bash
python tools/assemble_solohost_staging_v1.py \
  --binary /secure/build/koschei-onefile/ks \
  --smoke-receipt /secure/evidence/koschei-onefile-smoke.json \
  --output /secure/release/koschei-solohost \
  --version 0.10.0 \
  --platform linux-x86_64 \
  --source-commit <full-commit-sha>
```

The assembler creates:

```text
koschei-solohost/
  ks
  koschei-release-manifest.json
```

The manifest binds the exact executable SHA-256/size, full source commit, smoke receipt digest, binary-reported version evidence, Go toolchain identity, and the one-time Pi commercial mode. It is deliberately marked `UNSIGNED-STAGING`.

Validate staging only:

```bash
python tools/verify_solohost_artifact_v1.py \
  /secure/release/koschei-solohost \
  --allow-unsigned-staging
```

This may pass structural/digest/evidence checks but is explicitly **NOT PUBLISHABLE**.

### 5. Sign with the owner-held release key

Generate/store the production private key outside the repository. Never copy it into the artifact or SoloHost package.

```bash
python tools/sign_solohost_release_v1.py \
  /secure/release/koschei-solohost \
  --private-key /secure/keys/koschei-solohost-ed25519.pem
```

The signer writes `koschei-release-manifest.sig` and records a public-key-derived `key_id` in the exact manifest bytes that are signed.

### 6. Run the publication gate

```bash
python tools/verify_solohost_artifact_v1.py \
  /secure/release/koschei-solohost \
  --public-key /secure/keys/koschei-solohost-ed25519.pub.pem
```

Publication verification checks:

- source/private-repository leak policy;
- product/channel/version metadata;
- full source commit identity;
- required smoke evidence and Go toolchain identity;
- one-time Pi billing marker;
- executable SHA-256 and byte size;
- signature scheme;
- public-key-derived key id;
- detached Ed25519 signature over the exact manifest bytes.

A failing gate means the artifact is not publishable.

## Build stages

### Stage A — complete

- one-time Pi commercial decision locked;
- source-free publication boundary locked;
- machine-checkable source/private-material leak gate added.

### Stage B — implementation complete, release-environment proof pending

- narrow customer binary entry implemented;
- controlled Nuitka standalone/onefile builder implemented;
- Nuitka data-inclusion escape paths blocked;
- Python/Python-bytecode/Go source-leak policy implemented;
- functional/security smoke gate implemented;
- required Go-backed native build smoke implemented;
- binary SHA-256-bound smoke receipt implemented;
- staging assembler requires exact smoke evidence and full source commit;
- executable SHA-256 binding implemented;
- Ed25519 detached signing implemented;
- trusted-public-key verification implemented.

- produce a customer executable without shipping the private Python source tree;
- generate SHA-256 digests and release metadata;
- sign the release manifest;
- pin the owner release trust anchor outside the artifact;
- prove CLI smoke tests against the sealed artifact.

### Stage C — next after Stage B proof

- wrap **only the verified sealed artifact** in the exact observed SoloHost beta package format;
- include a compatible third-party Go toolchain for full `ks build` support;
- expose only the local service/port required by the observed SoloHost contract;
- run as a non-root user where the platform permits it;
- mount only explicit user workspace/storage paths;
- deny unrelated host filesystem access by default.

### Stage D — after packaging

- authenticate the purchaser through the sanctioned Pi identity boundary;
- verify completed Pi payment outside the compiler core;
- issue a durable one-time purchase entitlement for the purchased artifact;
- unlock/download the signed artifact;
- never place Pi wallet/private-key custody in Koschei.

## Publication gate

Before any image/package is submitted to SoloHost, run the fail-closed verifier with the
independently pinned owner public key:

```bash
python tools/verify_solohost_artifact_v1.py \
  <artifact-directory> \
  --trusted-public-key /secure/out-of-band/koschei-release-public.pem
```

A failing gate means the artifact is not publishable. A key copied only from the artifact
being verified does not satisfy the production trust model.
