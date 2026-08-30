# Koschei Lang — Pi SoloHost One-Time License Decision V1

Status: **ACTIVE COMMERCIAL DECISION**

## Decision

Koschei Lang's initial Pi/SoloHost commercial model is a **one-time purchase denominated in Pi**.

It is **not** a monthly or recurring subscription product.

The exact Pi price is intentionally not hard-coded in the compiler, runtime, repository, or distributable artifact. Pricing is a commercial configuration controlled outside the language core so it can be changed without rebuilding or weakening Koschei semantics.

## Product flow

1. A Pioneer discovers Koschei Lang through Pi Desktop / SoloHost.
2. The user sees the current one-time Pi purchase price before acquisition.
3. Payment is verified through the sanctioned Pi payment/identity adapter boundary.
4. Successful payment creates a durable Koschei entitlement for that purchase.
5. The user receives or unlocks the signed Koschei distributable artifact.
6. The installed artifact verifies its entitlement without giving Pi payment code authority over the language core.

## Non-goals

V1 does not introduce:

- monthly billing;
- recurring subscription smart contracts;
- time-expiring compiler access merely to force renewal;
- Pi-specific semantics inside `.ks`;
- Pi wallet/private-key custody inside Koschei;
- public redistribution of the proprietary compiler source;
- hard-coded commercial pricing inside the compiler/runtime.

## Distribution boundary

SoloHost is a distribution and discovery channel, not the owner of Koschei language semantics.

The public/customer artifact MUST NOT contain the private Git repository, Python compiler source tree, tests, internal security contracts, private build credentials, signing keys, or owner-only operational material.

Customer distribution should converge on signed, reproducible, source-free release artifacts. Development containers that include private source are internal-only and MUST NOT be submitted to SoloHost.

## Entitlement semantics

A completed one-time purchase grants a durable entitlement to the purchased Koschei product/release according to the commercial terms attached to that release. V1 does not impose periodic expiration.

Upgrade policy, refund policy, transfer policy, device limits, enterprise rights, and future major-version pricing are separate commercial decisions and are deliberately not invented here.

## Trust separation

Pi identity/payment evidence is external evidence. It can authorize delivery or activation only through the sanctioned external-adapter boundary. It MUST NOT become ambient authority inside the language or silently widen disk, network, environment, process, build, or deployment capabilities.

The commercial layer answers **who has purchased which artifact**. Koschei core answers **what code is allowed to do**. Those responsibilities remain separate.
