# Koschei Lang on Pi SoloHost

Status: **distribution scaffold — not yet a public artifact**

This directory defines the Pi Desktop / SoloHost distribution boundary for Koschei Lang. It must remain outside language semantics and must not turn Pi-specific code into a dependency of the compiler core.

## Commercial model

The initial product model is a **one-time Pi purchase**. There is no monthly subscription requirement. The exact Pi price is external commercial configuration and must not be hard-coded into the compiler or release artifact.

See `commercial/PI_SOLOHOST_ONE_TIME_LICENSE_V1.md`.

## Why there is no public Dockerfile yet

The current bootstrap compiler is packaged as Python. A naive Dockerfile such as `COPY koschei /app/koschei` would place proprietary compiler source directly in a customer-installable image.

That is not an acceptable SoloHost release boundary.

The public SoloHost image must be assembled from a **sealed release artifact**, not from a source checkout.

## Intended release chain

```text
private koschei-lang repository
        |
        v
owner-controlled release build
        |
        +--> tests / local validation / evidence
        |
        +--> source-free executable artifact
        |
        +--> checksums + signed release manifest
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

Pi currently describes SoloHost as an open, permissionless self-hosted application framework with structural package checks. Because the beta format can change, this repository does **not** invent a Pi manifest schema.

When the publisher UI/exported package schema is available, its exact manifest will be added under this directory without changing the compiler core.

## Build stages

### Stage A — current

- lock the one-time Pi commercial decision;
- lock the source-free publication boundary;
- add a machine-checkable artifact leak gate;
- keep work on the existing Pi integration branch.

### Stage B — sealed binary

- produce a customer executable without shipping the private Python source tree;
- generate SHA-256 digests and release metadata;
- sign the release manifest;
- pin the owner release trust anchor outside the artifact;
- prove CLI smoke tests against the sealed artifact.

### Stage C — SoloHost package

- wrap only the sealed artifact in the SoloHost container/package;
- expose the minimum local port/UI required by the SoloHost package contract;
- run as a non-root user where the platform permits it;
- mount only explicit user workspace/storage paths;
- deny unrelated host filesystem access by default.

### Stage D — Pi purchase activation

- authenticate the purchaser through the sanctioned Pi identity boundary;
- verify completed Pi payment outside the compiler core;
- issue a durable entitlement for the purchased artifact;
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
