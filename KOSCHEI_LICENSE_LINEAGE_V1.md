# Koschei License Lineage v1

Status: **EVIDENCE MAP — NOT LEGAL ADVICE**

Purpose: give an acquisition reviewer a precise source-control boundary between historical MIT-licensed revisions and the current proprietary code line. This document records repository evidence; it does not by itself prove complete chain of title.

## Evidence-backed transition

Repository history for `LICENSE` shows two relevant commits:

1. `00ca777e50e18d7c36e8d983d206c3ba7ee5a3ff` — initial repository commit, 2026-06-18. The repository began with an MIT License.
2. `661798a8cf059c88b93de1e79a651e72c923398d` — `license: transition current Koschei source to proprietary terms`, 2026-08-13.

The immediate parent of the proprietary transition is:

`30086337c6c8c56702436905810a75a17f5f891c`

At that parent revision, `LICENSE` is still the MIT License. The transition commit replaces that text with the Koschei Proprietary License Notice and explicitly preserves rights already granted for older MIT-released revisions.

## Canonical repository boundary

For technical due diligence, the source-control boundary is therefore:

- **MIT historical line:** revisions reachable in the repository history up to and including `30086337c6c8c56702436905810a75a17f5f891c`, to the extent those revisions were actually released/distributed under the MIT terms in force at the time.
- **Proprietary line:** `661798a8cf059c88b93de1e79a651e72c923398d` and later revisions, subject to the proprietary notice and any separate written agreements.

Important limitation: Git history proves the license file changed at this point. It does **not** independently prove which historical commits were actually made public, downloaded, mirrored, packaged, or separately licensed. A buyer data room should retain release/publication evidence for that question.

## Current proprietary notice

The current notice states that current Koschei source, binaries, documentation, security mechanisms, model integrations, build artifacts and related materials are proprietary and confidential unless separately licensed. It also says historical MIT grants are not revoked.

This means an acquisition must not represent the historical MIT code as newly exclusive. The value transferred is the current proprietary lineage, later proprietary changes, related confidential materials, brands/accounts where included, and whatever rights the seller can validly transfer.

## Buyer data-room evidence required

Before an acquisition candidate is marked IP-ready, retain:

- this source-control transition map;
- the pre-transition MIT `LICENSE` from commit `30086337...`;
- the proprietary `LICENSE` from commit `661798a8...`;
- a list of public releases/tags and their exact commit SHAs;
- any archived package/release publication records;
- contributor/contractor IP assignments, if any contributors other than the owner supplied protectable code;
- owner chain-of-title attestation;
- third-party code/model/tooling license inventory;
- acquisition agreement language that distinguishes proprietary rights from surviving historical MIT grants.

## Acquisition gate interpretation

The historical-license gate may move from **PARTIAL / unknown boundary** to **PARTIAL / repository boundary documented**.

It remains not fully VERIFIED until publication history and chain-of-title evidence are retained outside the mutable repository.
