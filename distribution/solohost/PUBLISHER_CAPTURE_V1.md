# Pi SoloHost Publisher Capture Checklist V1

Status: **WAITING FOR OBSERVED PI DESKTOP BETA CONTRACT**

Purpose: record the actual Pi Network SoloHost publisher/package contract before adding any Pi-specific package manifest to Koschei Lang.

Do not infer fields from unrelated projects, third-party Pi-named desktop applications, generic Docker marketplaces, or older Node tooling. Only values directly observed in the current official Pi Desktop / SoloHost publisher flow or current official Pi Network documentation may become the package contract.

## Capture from the publisher UI

Record the exact labels, allowed values, required/optional state, validation messages, and examples for:

- application/package name;
- application id or slug;
- publisher identity/account field;
- version field and accepted version format;
- description/summary fields and length limits;
- category/tags;
- icon/logo/screenshots and required formats/dimensions;
- package submission mechanism: file upload, image reference, repository, registry, compose text, or other;
- accepted archive/package extensions if upload based;
- supported CPU architectures and operating-system constraints;
- container image requirements and permitted registries if image based;
- entry command/start command;
- exposed local ports and protocol expectations;
- health-check declaration;
- persistent storage/volume declarations;
- user-selected workspace/folder mount model;
- environment-variable declaration and secret-input mechanism;
- outbound network declaration/permissions if present;
- hardware requirements fields if present;
- Pi Browser/mobile access fields if present;
- Pi Sign-in fields if present;
- Pi payment/wallet fields if present;
- license/terms/privacy/security links if present;
- package digest/signature/provenance fields if present;
- draft/unlisted/listed states;
- structural validation rules and exact rejection messages;
- update/version replacement flow;
- uninstall/data-retention behavior exposed to publisher;
- pricing or paid-download controls, if any.

## Koschei mapping rules

When the real fields are known:

1. map only the minimum permissions/resources required by Koschei;
2. consume only the already verified sealed customer artifact — never the private repository;
3. include a compatible third-party Go toolchain only if the package model allows it and the full `ks build` smoke remains green;
4. mount user workspaces explicitly and narrowly;
5. keep the Koschei language core independent of Pi identity/payment code;
6. keep the commercial model one-time Pi purchase unless the owner makes a new explicit commercial decision;
7. do not hard-code the Pi price inside the compiler/runtime;
8. preserve the signed release manifest and trusted-key verification chain;
9. fail publication if the actual SoloHost structural checks conflict with Koschei's source-free/security boundary rather than weakening the boundary silently.

## Evidence to retain

For the first accepted draft submission retain privately:

- Pi Desktop/Node version;
- publisher UI screenshots or exported schema where permitted;
- exact submitted package metadata;
- exact sealed artifact SHA-256;
- smoke receipt SHA-256;
- signed Koschei release manifest and detached signature;
- trusted release public-key id;
- structural validation result/rejection text;
- SoloHost draft/unlisted listing identifier once issued.

This document is intentionally a capture checklist, not a fabricated SoloHost manifest specification.
