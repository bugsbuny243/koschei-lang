# Koschei Package Ecosystem v1

Koschei users need a usable library ecosystem without inheriting the ambient-authority model of traditional package managers.

## Three layers

### 1. Core Library
Ships with the language/toolchain. Intended families include text, collections, data/JSON, HTTP, filesystem, database, crypto, time, concurrency, testing, logging and observability. Security-sensitive operations remain unavailable until their resource budgets and interpreter/native parity are actually enforced.

### 2. Secure Packages
Third-party packages are admitted through a versioned package manifest containing:

- exact artifact digest;
- provenance digest;
- exact dependency digests;
- declared effects;
- exact targets for authority-bearing effects;
- resource-budget digest.

Installing or importing a package grants **zero ambient authority**. Declared effects describe requested/possible behavior; they are not execution permission. Execution authority must still come from explicit application admission/capability flow.

### 3. Universe SDK
Advanced security/system users may directly use Reality, Matrix Portal, Wanda commitments, Strange future-path simulation, Loki deception, Hela authority death, Captain Marvel blast-radius limits, Vormir sacrifice and Gauntlet convergence. These primitives are optional at the application surface; normal application developers should receive safe defaults through the standard library.

## Package law

`package metadata != application authority != runtime effect`

A registry compromise must not be able to turn package installation alone into disk/network/process/secret/signing access.

## Developer-experience target

A normal developer should be able to build an HTTP service, parse data, access a database, run tasks and write tests without understanding every Multiverse primitive. The toolchain/compiler should synthesize and display the resulting authority manifest and reject hidden widening.

## Near-term implementation order

1. finish bounded `text/list/map/data` primitives;
2. make HTTP client/server budgets complete and parity-tested;
3. implement secure hashing/verification and non-printable secret values;
4. add task/channel structured concurrency;
5. add database query-scoped capabilities;
6. add package manifest/lockfile/registry verification;
7. expose Universe SDK only after the ordinary path is usable.
