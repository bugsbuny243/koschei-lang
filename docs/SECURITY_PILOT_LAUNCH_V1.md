# Koschei Lang — evidence-based security pilot launch gate v1

Status: **internal launch-candidate preparation; NOT production approval.**
Owner: Koschei Lang, independent of Koschei Sentinel and Koschei Web3 Hub.

## Trigger / threat scenario

The 29 October 2026 Binance incident was described in early-November
reporting as a multi-step intrusion: malicious developer tools / an interview
coding task, engineer endpoint compromise, stolen credentials and an abused
internal AI tool, followed by unauthorized wallet-signing transactions.
Sources (context only, not a validated Koschei test):
- TRT Haber, 4 November 2026: https://www.trthaber.com/haber/dunya/binancee-63-milyar-dolarlik-siber-saldirinin-arkasindan-sahte-is-gorusmesi-cikti-962158.html
- Reuters, 3 November 2026:
  https://live.euronext.com/en/financial-news/binance-hackers-used-fake-job-interview-63-billion-attack

**Critical non-claim:** Koschei Lang has not been tested against this real
incident, and cannot claim that running an untrusted Homebrew executable,
Python script, IDE extension, container or agent tool on a compromised host
would be prevented. A language capability constraint is not a universal
endpoint sandbox, wallet signer or human-resistant anti-phishing control.

## What can be offered to customers now — a controlled *evaluation*

1. **Koschei capability checker and language:** demonstrate imported `.ks`
   code unable to acquire disk/network effects without explicit capability
   values; show `KS2401` rejection of the committed supply-chain fixture.
   `ks caps --deny net` can serve as a build gate. A malicious file is
   rejected because the *Koschei compiler* checks its capabilities; never
   execute downloaded interview repositories as a "demo."
2. **Read-only security CLIs:** `examples/apps/secretscan` (credential
   patterns) and `examples/apps/integrity` (directory digest manifest)
   come with tests and limited directory read capabilities. These are
   pilot tools, not malware analysis, endpoint protection or an audit.
3. **Developer tooling:** `ks check`, `ks run`, `ks build`,
   source capability manifest and Core Library reference.
   The native backend still uses a Go bootstrap adapter. The language
   is not independently self-hosted.
4. **Deterministic private download:** `tools/polar_bundle_v1.py` prepares
   the proprietary Polar ZIP. Tests check package structure and interpreter
   examples. Commercial license terms and prices are defined in
   `LICENSING.md`; checkout or payment activation is **not** established
   by the pilot gate.

These are **pre-1.0, non-production** evaluation capabilities. Do not
advertise bank, exchange, wallet custody, or payment infrastructure readiness.

## Executable trusted ZIP gate

The command below is intended for an isolated **internal CI job**. The
expected SHA-256 must come from a separately authenticated release record
and must be recorded with the exact source SHA. **Do not** simply compute
the hash of an unknown/untrusted downloaded ZIP and treat that same
hash as proof of origin.

```sh
python tools/polar_bundle_v1.py --output-dir /tmp/koschei-pilot-candidate
# Obtain and verify the expected release digest from trusted CI provenance.
python tools/pilot_security_gate_v1.py \
  --bundle /tmp/koschei-pilot-candidate/koschei-lang-0.10.0.zip \
  --expected-sha256 "<TRUSTED_64_DIGIT_SHA256_FROM_RELEASE_RECORD>" \
  --output /tmp/koschei-pilot-evidence.json
```

Checks performed **against contents extracted from the same matched ZIP**:

- exact archive SHA256 match, one package root, required product files,
  no duplicate files, ZIP path traversal or ZIP symlinks; size bounded
- example `hello.ks` executes and matches its pinned output
- imported deliberate unauthorized `.ks` disk access is blocked by
  `KS2401` at check time; malicious fixture code is **not run**
- `secretscan` and `integrity` examples each pass `caps --deny net`
  and are detected as requesting disk capability by `caps --deny disk`

JSON schema: `koschei.customer-pilot-evidence/v1`. Every check records
success and output hashes, not raw potentially sensitive logs. The receipt
**always** has `approved_for_production: false`. The tool exits nonzero
when any test fails and cannot approve a release.

CI additionally tests tampered hash, path traversal, symlink, missing
mandatory product files, canonical expected-hash formatting and expected
negative exit codes. The gate is tested with a freshly built source ZIP.
A hash calculated from the same build in CI proves only *build-local*
integrity and behavior, not independent release authenticity.

## Prelaunch decision gates

| Gate | Measurable rule | Currently supported? |
|---|---|---|
| A. Product boundary | Lang license/distribution separate from Sentinel/Web3 | Documented |
| B. Reproducible candidate | Exact source commit and deterministic ZIP digest | Existing build/test; pilot receipt added |
| C. Executed security claims | Negative KS2401 check, manifest gate, demo runtime, adversarial regression in CI | Pilot candidate; require exact-head green CI |
| D. Runtime parity | Native `ks build` vs interpreted `ks run`; scope explicitly described | Existing CI tests; not independent runtime |
| E. Artifact authentication | Authentic, independently published signed hash/manifest, protected publishing identity | **Separate acceptance required** |
| F. External review | Independent secure code review and supported-platform end-to-end tests | **Not established** |
| G. Customer assurance | Private evaluation license, data protection, support, disclosure and incident-response channels | **Operational review required** |
| H. Production | Signed release, security remediation, measurable SLOs and production pilot evidence | **Not approved** |

Passing A–D allows only a **controlled evaluation pilot**, subject to
owner approval and customer onboarding. It never automatically satisfies E–H.

## Pilot threat-to-evidence matrix

| Threat / failure | Koschei-evidenced mechanism | Limitation / next gate |
|---|---|---|
| Imported `.ks` module asks for ungranted disk access | `ks check` denies fixture with `KS2401` | Does not block arbitrary shell or host-language code |
| Dependency silently adds network access | `ks caps --deny net` fails for graph that requests network | Origin/target authorization must also be designed |
| Secrets accidentally checked into a directory | `secretscan` read-only scanning example | Not exhaustive credential discovery or secret revocation |
| Artifact files silently changed | `integrity` digest snapshot/verify and ZIP SHA gate | Digest without trusted origin cannot authenticate publisher |
| Malware execution on developer laptop | **No protection claim** | OS sandbox, endpoint security, isolated build workers |
| Internal AI tool abuses wallet-signing access | **No protection claim** | Agent capabilities, independent high-value signing policy, audit and key isolation |
| Stolen session/production credentials | **No protection claim** | Credential revocation, MFA, least-privilege runtime identities |
| Replay, multi-party transactions, on-chain authorizations | Separate experimental Matrix work in unmerged PRs | Security review, chain-specific policy and production proofs |

## Commercial sequencing — launch speed without false promises

**Stage 1: technical demonstration.** Publish an evidence-supported product
description and show only the bundled `KS2401`, `ks caps`, `secretscan`
and `integrity` results. Request review from security engineering teams.
Never claim to have prevented the Binance incident.

**Stage 2: controlled early-adopter evaluation.** Provide licensed
pre-release artifacts via the established private channel only after
candidate checks, artifact authenticity, confidentiality and support
readiness are reviewed. Track portability, installation success, false
positives, permission policy drift and requested integrations.

**Stage 3: production eligibility review.** Require the independent review
and production gates E–H. Critical financial transaction execution and
wallet signing remain out of scope until they have their own threat models,
formal acceptance tests and evidence.

## Explicit prohibited launch claims

- "Koschei would have prevented the Binance attack."
- "All malicious developer dependencies are safe."
- "Koschei is a production-ready banking or exchange runtime."
- "An SHA checksum is a digital signature or wallet authorization."
- "Full canonical compiler CI makes software hack-proof."
