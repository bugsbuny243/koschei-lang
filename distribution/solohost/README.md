# Koschei Lang on Pi SoloHost

Status: **sealed-release pipeline in progress — not yet a public SoloHost artifact**

This directory defines the Pi Desktop / SoloHost distribution boundary for Koschei Lang. It remains outside language semantics and must not turn Pi-specific code into a dependency of the compiler core.

## Commercial model

The initial product model is a **one-time Pi purchase**. There is no monthly subscription requirement. The exact Pi price is external commercial configuration and must not be hard-coded into the compiler or release artifact.

See `commercial/PI_SOLOHOST_ONE_TIME_LICENSE_V1.md`.

## Why the customer artifact is not built from the repository checkout

The current bootstrap compiler is packaged as Python. A naive Dockerfile such as `COPY koschei /app/koschei` would place proprietary compiler source directly in a customer-installable image.

That is not an acceptable SoloHost release boundary.

The public SoloHost image must be assembled from a **sealed release artifact**, not from a source checkout.

## Intended release chain

```text
private koschei-lang repository
        |
        v
owner-controlled compiler packaging
        |
        +--> local validation / evidence
        |
        +--> source-free executable
        |
        v
SoloHost staging assembler
        |
        +--> executable SHA-256
        +--> immutable release metadata
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
- contain no internal test tree;
- contain no owner credentials, payment secrets, wallet private keys, signing private keys, or CI secrets;
- contain no private build-only contracts unless explicitly designated customer-facing;
- carry an immutable version identifier;
- bind the executable bytes to SHA-256 release metadata;
- carry a detached owner-controlled Ed25519 signature;
- pass signature verification against an explicitly trusted public key;
- keep Pi identity/payment integration outside Koschei language semantics;
- preserve local-first execution for supported operations.

## SoloHost beta assumptions

Pi currently describes SoloHost as an open, permissionless self-hosted application framework with structural package checks. Because the beta package format can change, this repository does **not** invent a Pi publisher manifest schema.

When the publisher UI/exported package schema is observed, its exact manifest will be added under this directory without changing the compiler core.

## Current release tooling

### 1. Build a customer executable

The customer input to this pipeline must already be a built executable. Python source/bytecode is rejected.

The initial bootstrap packaging candidate is Nuitka. The validation order is:

1. build/test a standalone executable first;
2. run Koschei CLI smoke tests;
3. only then produce a one-file customer executable;
4. feed that executable into the source-free SoloHost staging assembler.

This use of Nuitka is a bootstrap deployment mechanism, not a Koschei language dependency and not a claim that ordinary compiled binaries are impossible to reverse engineer. Stronger commercial IP-hardening remains a separate release decision.

### 2. Assemble unsigned staging

```bash
python tools/assemble_solohost_staging_v1.py \
  --binary /secure/build/ks \
  --output /secure/release/koschei-solohost \
  --version 0.10.0 \
  --platform linux-x86_64 \
  --source-commit <commit-sha>
```

The assembler creates:

```text
koschei-solohost/
  ks
  koschei-release-manifest.json
```

The manifest binds the exact executable SHA-256 and size. It is deliberately marked `UNSIGNED-STAGING`.

Validate staging only:

```bash
python tools/verify_solohost_artifact_v1.py \
  /secure/release/koschei-solohost \
  --allow-unsigned-staging
```

This may pass structural/digest checks but is explicitly **NOT PUBLISHABLE**.

### 3. Sign with the owner-held release key

Generate/store the production private key outside the repository. Never copy it into the artifact or SoloHost package.

Release signing:

```bash
python tools/sign_solohost_release_v1.py \
  /secure/release/koschei-solohost \
  --private-key /secure/keys/koschei-solohost-ed25519.pem
```

The signer writes:

```text
koschei-release-manifest.sig
```

and records a public-key-derived `key_id` in the exact manifest bytes that are signed.

### 4. Run the publication gate

```bash
python tools/verify_solohost_artifact_v1.py \
  /secure/release/koschei-solohost \
  --public-key /secure/keys/koschei-solohost-ed25519.pub.pem
```

Publication verification checks:

- source/private-repository leak policy;
- product/channel/version metadata;
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

### Stage B — in progress

- staging assembler implemented;
- executable SHA-256 binding implemented;
- Ed25519 detached signing implemented;
- trusted-public-key verification implemented;
- actual Koschei Nuitka customer binary build and CLI smoke validation still required.

### Stage C — next

- wrap **only the verified sealed artifact** in the exact SoloHost beta package format;
- expose only the local service/port required by the observed SoloHost contract;
- run as a non-root user where the platform permits it;
- mount only explicit user workspace/storage paths;
- deny unrelated host filesystem access by default.

### Stage D — after packaging

- authenticate the purchaser through the sanctioned Pi identity boundary;
- verify completed Pi payment outside the compiler core;
- issue a durable entitlement for the purchased artifact;
- unlock/download the signed artifact;
- never place Pi wallet/private-key custody in Koschei.
