# Koschei Lang 0.10.0 — Global launch package

**Public product website:** https://koschei.dev/  
**Technical article:** https://koschei.dev/security-guide.html  
**Individual checkout:** https://buy.polar.sh/polar_cl_H3mMbTpBdziezC3ooJARCQIMHqzVHEeM15E1v0C7XlR  
**Price:** 49 USD one-time, **not** EUR. Individual covers one named developer.

> Status: copy pack prepared, **not posted** to any third-party service. Koschei Lang is pre-1.0. The public site is deployed, and the user completed a Polar sandbox purchase, saw the ZIP entitlement and reported the ZIP download beginning. This is not evidence of a successful live customer payment or independently authenticated downloaded bytes.

## Positioning / messaging baseline

**Category:** Security-first, capability-secure general-purpose programming language.

**One-sentence value:** Imported Koschei modules do not implicitly inherit disk, network, environment or process authority; explicit capabilities can be checked before execution.

**Demonstrable proof:** `ks check examples/supply_chain/main.ks` rejects an import without disk authority with `KS2401`. `ks caps --deny net` provides a checkable CI policy.

**Boundaries:** No supported claim of EVM-native smart contracts, exchange-security certification, self-hosted native compiler, arbitrary malware sandboxing or preventing unrelated wallet/endpoint attacks. Don't call the static website preview a live compiler.

## Product Hunt submission — copy ready

**Product name:** Koschei Lang 0.10.0

**Tagline (60-character cap):** A programming language with explicit permissions

**Short description (260-character cap):**
Koschei Lang checks what imported code can access. Audit disk, network, environment and process authority with ks caps; reject unauthorized operations with ks check. Includes a native build path, a Core Library and practical examples.

**Product URL:** https://koschei.dev/

**Suggested topics:** Developer Tools; Programming Languages; Security

**Maker's first comment:**

Hi Product Hunt,

I'm sharing Koschei Lang 0.10.0, an early version of a new capability-secure programming language.

The problem we're exploring is ambient authority: when dependencies run with permissions they weren't explicitly intended to use. In Koschei source, a function needs an appropriate capability value. The included supply-chain example intentionally tries to read a secret without one; the compiler rejects it with KS2401 before execution.

The public technical guide shows the example and the exact local commands. This is pre-1.0 software and is not a claim that the host operating system or arbitrary third-party programs become safe.

An Individual commercial license is $49 USD paid once for one developer and includes acquired versions perpetually plus the following 12 months of releases. Personal, non-commercial use is free under the license.

I'd especially appreciate feedback on the capability model, the compiler diagnostics and the developer experience.

Product: https://koschei.dev/

**Before submitting:** Product Hunt requires a personal account and product gallery asset; use authentic product screenshots and a real demo video. Avoid asking for votes, incentivizing reactions or mass-messaging strangers. Do not claim the submission has been published.

## DEV Community — technical article draft

**Title:** Why should an imported module inherit all your permissions?

**Tags:** security, programming, devtools, compilers

Imported code often gets the ambient permissions of the process that loads it. That makes a small dependency a potentially large authority boundary.

Koschei Lang 0.10.0 experiments with a different model: permissions are values. If a module does not receive disk, network, environment or process authority, it should not be able to use that authority through the supported Koschei language path.

The repository includes a small supply-chain demonstration: an imported analytics module attempts to read a secret without being passed disk authority.

Run:

```sh
ks check examples/supply_chain/main.ks
```

The expected result is `KS2401`: a required capability was unavailable. The checker rejects the code before execution.

You can also inspect a whole program's reachable authority:

```sh
ks caps examples/apps/secretscan/main.ks
ks caps --deny net examples/apps/secretscan/main.ks
```

The second command is suitable for CI policy checks: it fails when forbidden network authority is present.

This is deliberately narrower than a general-purpose host sandbox. It does not guarantee the safety of arbitrary native executables, compromised endpoints or external wallets. The current native build path uses a Go-based adapter and Koschei remains pre-1.0.

The full explanation, requirements, licensing and supported examples are documented here:

https://koschei.dev/security-guide.html

## LinkedIn — short technical launch

I'm releasing Koschei Lang 0.10.0, an early capability-secure programming language focused on explicit authority in software.

The idea: imported Koschei code should not silently inherit access to disk, network, environment variables or process execution.

With `ks check`, developers can identify unauthorized capability use before execution. With `ks caps`, they can inspect accessible permissions and enforce policy in CI.

See the `KS2401` technical walkthrough:
https://koschei.dev/security-guide.html

Individual commercial license: **$49 USD, one-time, for one developer**. Pre-1.0 software; features and constraints are explained on the site.

#ProgrammingLanguages #SoftwareSecurity #DeveloperTools

## Community posting checklist

- Publish as a real developer account, not as a bot or purchased engagement.
- Use a genuine screenshot of the shipped terminal example, clearly labelled as recorded output.
- Link to the public technical guide for substantive discussion; checkout is secondary.
- Engage in technical Q&A. Record feedback and prioritize actionable issues.
- No HN "Show HN" claim of a runnable public demo: the site only displays static illustrative output, and the source repo is private. For HN, wait until a public hands-on sample is available or share a candid technical discussion in the appropriate format.

## Measurement

Use product-site visits, click-throughs to Polar and actual purchases as three separate metrics. The page currently has no analytics pixel or server-side conversion instrumentation, so **do not invent impression counts, conversion rates or sales**. A privacy-respecting measurement plan can be added later with user approval.
