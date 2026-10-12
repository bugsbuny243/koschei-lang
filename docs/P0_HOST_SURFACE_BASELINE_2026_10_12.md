# P0.1 — Go host authority surface baseline (2026-10-12)

Status: **PARTIAL / SOURCE REVIEW ONLY**. This is not a binary reachability or isolation proof.

## Scope and evidence

Source inspected on main: `koschei/codegen_go.py` (2,493 lines), specifically the generated `CAPABILITY_RUNTIME` Go template; `koschei/runtime_authority_surface_v1.py` derives language-visible capability members from the canonical contract. These are separate mechanisms: a member allowlist is not OS-level isolation.

| Host symbol | Observed source role | Reachability class (provisional) | Binary presence verified? |
| --- | --- | --- | --- |
| `http.NewRequest` | `ksNetGet` HTTP request | Capability-associated network operation | No |
| `io.ReadAll` | HTTP body and disk file read | Shared helper in capability-associated paths | No |
| `syscall.Openat` | Descriptor-relative disk traversal/read/write | Capability-associated disk operation | No |
| `syscall.Close` | Descriptor cleanup | Runtime internal helper for disk operations | No |
| `os.NewFile` | Wrap already-open disk descriptor | Runtime internal helper for disk operations | No |
| `os.LookupEnv` | Environment lookup | Environment capability-associated path; full call chain unverified | No |

`Openat`, `O_NOFOLLOW`, `O_CLOEXEC`, and symlink/error handling are existing defensive measures; their presence is not itself a vulnerability.

## Required next measurement

1. Enumerate all host imports and call sites in the **generated** Go output of a fixed `.ks` fixture, with exact source line and containing function.
2. Map each to the corresponding canonical Koschei capability member or mark it `runtime-internal` / `unreachable-unproven`. Never infer reachability from symbol spelling.
3. Compile the fixture for the declared platform and collect `go version`, `go tool nm`, `readelf -d`, and static/dynamic linkage metadata. Record missing tools separately from test failures.
4. Build negative fixtures denying disk, network, env and process effects; measure compiler rejection and independent runtime boundary where available.
5. Define the minimal host import allowlist from **observed supported operations**, not from the name of a registry.
6. Only after that baseline, prototype a second WASI backend with a single-file parity test; Go remains supported.

## Security honesty (§12)

- **PROTECTS AGAINST:** No new protection in this document. Existing descriptor-relative `openat` and `O_NOFOLLOW` can help resist path/symlink traversal within their supported threat model.
- **DOES NOT PROTECT:** A compromised host runtime, compiler, signing key, broad host imports, side channels or malicious behavior within granted authority.
- **ASSUMPTIONS:** The observed source template matches the generated artifact for the selected fixture and the capability boundary is not bypassed elsewhere; neither is proven here.
- **FAILURE MODE:** An ambient OS call remains reachable outside the intended capability boundary, or a host can supply overly broad authority.

## Gate result

- **A or B?** This audit is preparatory for **B** (blast-radius reduction); no reduction achieved.
- **Syntax-only?** No.
- **Runtime enforcement?** Not established by this source inspection.
- **Priority/debt:** P0.1; adds no `koschei/*.py` module or semantic authority.
- **Acceptance:** Not passed. No generated binary symbol absence list, no host import allowlist and no quantitative B reduction yet.
- **Tests executed:** 0. Real failures: not measured. Infrastructure failures: not measured.
