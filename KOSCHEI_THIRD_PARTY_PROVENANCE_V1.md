# Koschei Third-Party Provenance Inventory v1

Status: **INITIAL EVIDENCE INVENTORY — NOT YET A COMPLETE SBOM**

Purpose: separate the small compiler/runtime dependency surface from the larger build, packaging, container, native-toolchain and optional-model supply chain. Acquisition diligence must cover all of them.

## 1. Compiler/runtime dependency surface

### Python package runtime

`pyproject.toml` currently declares:

```toml
dependencies = []
```

Evidence status: **VERIFIED_SLICE**.

This proves only that the packaged Python compiler core declares no runtime Python dependencies. It does not prove that build, test, container, native, deployment or optional intelligence paths are dependency-free.

### Python build backend

`pyproject.toml` currently declares:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

Evidence status: **THIRD_PARTY BUILD DEPENDENCY**.

Acquisition closure:
- resolve exact version used for candidate build;
- record artifact hash/source;
- include license/provenance in SBOM/NOTICE evidence.

## 2. Native Go module

`native/go.mod` currently contains only:

```text
module github.com/bugsbuny243/koschei-lang/native

go 1.22
```

There are no external `require` directives in this module file.

Evidence status: **VERIFIED_SLICE — NO DECLARED EXTERNAL GO MODULE REQUIREMENTS**.

Acquisition closure:
- record exact Go toolchain distribution/version/hash used for candidate build;
- retain `go env`/toolchain evidence;
- verify generated/native code does not fetch undeclared modules during clean-room build.

## 3. Container/build supply chain

Current `Dockerfile` introduces the following external build/runtime roots.

### Base images

- `golang:1.24-bookworm`
- `python:3.12-bookworm`
- `python:3.12-slim-bookworm`

Status: **BLOCKER FOR REPRODUCIBLE ACQUISITION CANDIDATE**.

Reason: these are tag references rather than immutable image digests. The same tag may resolve to different bytes over time.

Closure requirement:
- pin each acquisition-candidate base image by digest;
- record registry, image digest, architecture and retrieval date;
- include image package inventory in candidate SBOM.

### Debian/apt build packages

The container build installs:

- `build-essential`
- `ca-certificates`
- `openssl`
- `patchelf`
- `zip`

Status: **UNPINNED BUILD DEPENDENCIES**.

Closure requirement:
- capture the exact Debian snapshot/repository state or exact resolved package versions;
- retain package manifest and licenses for candidate build;
- avoid claiming byte-for-byte reproducibility while repository/package resolution is mutable.

### Python build/packaging tools installed in Docker

The container build installs/upgrades:

- `pip`
- `nuitka`
- `ordered-set`
- `zstandard`

Status: **BLOCKER FOR REPRODUCIBLE ACQUISITION CANDIDATE**.

Reason: the Dockerfile currently does not pin exact versions or hashes for these packages.

Closure requirement:
- use a locked acquisition-build requirements file with exact versions and hashes;
- retain wheel/sdist provenance and licenses;
- fail closed when a required artifact/hash is unavailable.

## 4. Build signing scope

The current Dockerfile generates an ephemeral Ed25519 key during testnet packaging and explicitly labels it:

> TESTNET RELEASE: ephemeral build signing identity; not a production trust anchor.

Status: **CORRECTLY SCOPED TESTNET EVIDENCE, NOT PRODUCTION SIGNING**.

Acquisition closure:
- do not present the ephemeral testnet key as production provenance;
- define a production/acquisition signing identity and custody model, or explicitly state that production signing is not yet deployed;
- bind candidate archive/checksums/SBOM/validation receipt to the immutable candidate commit.

## 5. Required complete SBOM scope

The final buyer data-room SBOM must include at minimum:

1. Koschei source/package identity and immutable commit.
2. Python build backend and all build/test tooling.
3. Go toolchain and any resolved Go modules.
4. Container base images by digest.
5. OS packages resolved into build/runtime images.
6. Nuitka and transitive packaging inputs.
7. Vendored/generated/native source that is shipped in wheels or binaries.
8. VS Code/editor tooling if transferred as part of the acquisition.
9. Optional model/training/inference dependencies if transferred.
10. Deployment tooling/configuration whose artifacts are part of the product delivery.

For each third-party component record:

- canonical name;
- version;
- source URL/registry identity;
- immutable digest/hash where possible;
- license identifier/text source;
- direct/transitive role;
- build/runtime/test/deployment scope;
- whether redistributed in shipped artifacts;
- provenance evidence location.

## 6. Buyer gate

This inventory changes the acquisition interpretation from “compiler has no dependencies” to the more precise statement:

**The Python compiler core declares no runtime Python dependencies and the native Go module declares no external Go module requirements, but the current acquisition build/release supply chain still relies on unpinned third-party container, OS and Python build dependencies.**

The `Third-party code/license inventory` acquisition gate remains **BLOCKER** until a generated, hash-bound SBOM and NOTICE/provenance set exists for an immutable candidate.
