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
- be capable of being signed by the owner-controlled release process;
- keep Pi identity/payment integration outside Koschei language semantics;
- preserve local-first execution for supported operations.

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

Before any image/package is submitted to SoloHost, run:

```bash
python tools/verify_solohost_artifact_v1.py <artifact-directory>
```

A failing gate means the artifact is not publishable.
