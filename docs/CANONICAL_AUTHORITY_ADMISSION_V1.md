# Canonical Authority Admission v1

Parent: #240
Work item: #256

## Security boundary

Canonical Object Space execution does not discover authority from source text, a `.ks` suffix, `k0/k1` appearance, parser success, environment variables, or project-controlled provider names.

A trusted host/session broker supplies a process-local `CanonicalAuthoritySessionV1` containing:

- an already selected `ObjectSpaceCryptoProvider` capability bound to the registered crypto profile;
- a 64-byte temporal key;
- a 64-byte short-lived temporal handle;
- the expected 16-byte project identity;
- the expected reality epoch;
- the temporal policy.

The session representation redacts secret material. Admission exceptions deliberately collapse provider/crypto/session detail into a stable public error so secret bytes and provider internals do not enter ordinary logs.

## Native-only routing

`check_with_canonical_authority_v1()` and `run_with_canonical_authority_v1()` first call `load_object_space_project()` with the explicit authority bundle. Only a successfully authenticated `ObjectSpaceProject` is passed to `check_canonical_native_v1()` or `run_canonical_native_v1()`.

There is no compatibility parser or ModuleGraph fallback in this boundary.

## Deliberate non-goal

This slice does **not** serialize secrets into command-line flags and does not invent a production crypto provider. A later CLI/session-broker integration must pass this process-local authority through a trusted channel (for example an already established broker/agent capability), never through project metadata or raw secret command-line arguments.

## Adversarial gates

Tests cover provider substitution, wrong project identity, wrong epoch, expired temporal handles, redacted failures/repr, misleading `.ks` path names, and direct native check/run while legacy parser/graph loaders are patched to fail if reached.
