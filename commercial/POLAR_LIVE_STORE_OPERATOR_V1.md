# Koschei Lang 0.10.0 — Polar Commercial Activation Runbook

**Target:** public USD product listings, successful one-time checkout,
licensed file delivery for Koschei Lang 0.10.0. Not the $299 founding
security consulting pilot.

**Product owner/operator:** authenticated Koschei Lang Polar
organization account, not the compiler runtime or this GitHub workflow.

## 1. Obtain the exact commercial deliverable

Open [Koschei Lang Commercial Release Candidate workflow]
(https://github.com/bugsbuny243/koschei-lang/actions/workflows/lang-commercial-release.yml)
on the private GitHub repo. Use the **successful run from the exact
approved release commit**, not a prior or cancelled run.

Download the private artifact
`koschei-lang-0.10.0-commercial-<commit>`. It contains:

- `koschei-lang-0.10.0.zip` — bilingual installer, Core Library,
  license terms, tested examples, release notes
- `SHA256SUMS` — ZIP hash for integrity checks
- `candidate-manifest.json` — source commit, size, digest, workflow evidence
- `customer-security-evidence.json` — built-in interpreter/capability checks
- `full-validation-receipt.json` — exact-head canonical validation receipt

Verify SHA256SUMS using a **trusted** source before attaching the ZIP.
The workflow's digest is not itself an independently signed publisher
attestation. Release signing/authenticity must be verified by the
operator's publishing authority.

## 2. Configure products in Polar

Sources:
- https://polar.apidocumentation.com/documentation/basics/getting-started
- https://docs.polar.sh/docs/products
- https://docs.polar.sh/features/benefits

In the Koschei Lang **organization dashboard**, choose **Products**.
Create the following **one-time** products, not recurring subscriptions:

| Store product | Price (USD) | License scope |
|---|---:|---|
| Koschei Lang Personal | Free | Personal, non-commercial |
| Koschei Lang Individual | $49 | One named commercial developer |
| Koschei Lang Team | $249 | Up to 10 developers, one organization |
| Koschei Lang Enterprise | $999 | Any number of developers, one organization |

Copy the relevant English/Turkish description from
`commercial/KOSCHEI_LANG_010_STORE_LISTING_EN_TR.md`. Include the
published `LICENSE`, `LICENSING.md` links and the supported platform
requirements before a customer pays.

**Pricing decision requiring owner verification:** the authoritative
repository's `LICENSING.md`, `LICENSING.tr.md` and customer README
all say $49/$249/$999. The separate active commercial policy
`commercial/USD_ONLY_SALES_POLICY_V1.md` refers to a proposed $1,000
license target awaiting approval. These two sources are not automatically
equivalent. Do **not** silently replace the Enterprise checkout with
$1,000 or claim both are active. Resolve this source discrepancy before
the live Enterprise listing is enabled.

Polar supports **one-time fixed-price** products and **free** products.
The price currency is USD; set an actual one-time pricing model.
Check the current dashboard terms/merchant requirements before enabling.

## 3. Deliver the download after purchase

Create or reuse Polar **Benefits → File Downloads** for the exact
`koschei-lang-0.10.0.zip` and attach that benefit to each intended
product. If activating **License Keys**, independently configure key
issuance and entitlement counts according to the real license;
do not claim that this repo's compiler itself verifies a Polar key.
Polar offers File Downloads and License Keys as separate benefits.

Never expose the private GitHub repository or internal validation
evidence directory to customers merely to fulfill the ZIP.
Do not attach sensitive signing keys or CI credentials to the product.

## 4. Publish checkout links and end-to-end verify

Polar supports **Checkout Links** in the Products dashboard and
one-time paid products. Generate the actual URL from the live products.
Do not fabricate/store a guessed checkout URL.

Run owner-approved legitimate test orders and verify:
1. Actual checkout displays the intended product, currency and price.
2. Customer receives the correct invoice/receipt.
3. Customer access grants exactly the purchased tier and correct ZIP.
4. Customer extracts, installs and runs `ks version` and
   `ks check examples/supply_chain/main.ks` with expected `KS2401`.
5. Download SHA-256 matches the trusted release record.
6. Support, disclosures, chargeback/refund handling, privacy notices
   and licensing terms are accessible to the buyer.

Only after that check is the checkout **verified live**.
The GitHub release workflow does not claim this happened.

## 5. Launch page and product distribution

Promote the **standalone Koschei Lang product**, not the deprecated
$299 security-pilot page. Use the current `commercial/landing` page
for the legacy consulting service only until a real product landing
page has live purchase URLs. Avoid pretending a GitHub Actions
artifact link is public checkout.

Do not advertise an unverified "Binance breach prevention" claim.
Koschei's evidenced product value is explicit scope-limited
authority for compiled `.ks` code and its tested toolchain.

## 6. Required operator decisions / external systems

- Approved exact Git source SHA and artifact digest
- Final enterprise pricing discrepancy resolved
- Polar merchant organization and billing/onboarding active
- File Downloads and (if used) License Keys benefits configured
- Verified USD checkout links and successful order/fulfillment
- Authenticated release provenance, signed hash/manifest as applicable

The assistant can prepare code, listings, ZIP generators and test
evidence in GitHub but has **no connected Polar merchant action** in
this chat; it cannot truthfully mark the external store live.
