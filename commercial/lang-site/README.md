# Koschei Lang 0.10.0 product site

Self-contained, mobile-responsive, bilingual (English/Turkish) landing page for the **independent Koschei Lang programming language**, not the separate Koschei Sentinel, Web3 Hub or existing founding-pilot consulting offer.

## Preview

Open `commercial/lang-site/index.html` locally or serve the folder:

```sh
cd commercial/lang-site
python -m http.server 8080
```

Open http://127.0.0.1:8080 locally. EN/TR language switch, navigation and copy-to-clipboard controls work without any backend. The terminal illustration is explicitly **not** an interactive compiler.

## Public hosting

1. Verify exact commit CI and `python -m pytest -q tests/test_lang_public_site_v1.py`.
2. Deploy the static directory `commercial/lang-site/` to your authenticated domain/HTTPS provider. GitHub PR creation does **not** deploy the site.
3. Add a verified canonical URL, DNS/SSL, security headers and an actual customer support/privacy policy before major promotion. No domain or legal contact is invented.
4. Verify the existing `$49 USD` Polar payment page and post-purchase ZIP file benefit in an authorized test purchase. Direct checkout is user-supplied and no card/payment data is collected by this site.
5. Test EN/TR and both buy links on real mobile/desktop browsers, then distribute the **real deployed URL** via Product Hunt, DEV, Hacker News and direct outreach.

## Scope

The pricing is Individual 49 USD one time, one named commercial developer. The license is perpetual for acquired versions, with 12 months of released updates. `ks run` is an interpreter; `ks build` presently uses the Go native adapter. The shipped supply-chain fixture rejects unauthorized Disk capability with KS2401 **before execution**. The site is static and does not claim to protect arbitrary OS programs or prevent Binance-style intrusions.

There is no anonymous source-code checkout or public GitHub repo access. This repo is private, and the only external site link is the verified Polar checkout URL.

## Technical article and discovery

The public SEO pages are `/` and `/security-guide.html`. The static Docker image explicitly copies and serves those files plus `/robots.txt` and `/sitemap.xml`; Nginx otherwise returns 404 rather than exposing repository code. The page has a canonical URL on the verified Railway domain, and marketing copy is in `commercial/launch/KOSCHEI_LANG_010_GLOBAL_LAUNCH_KIT.md`.

Changes made on this branch do not change the live website until the Railway service is redeployed from the matching exact commit. Product Hunt or developer-community posts must be submitted by an authorized account owner, and no purchases are made by this site.

## Search and localization (November 2026)

There are now 3 indexable site URLs: `/`, `/security-guide.html` (English), and `/security-guide.tr.html` (Turkish). The homepage language toggle points to the matching guide. Guides include reciprocal hreflang and independent canonical tags. `sitemap.xml` and `robots.txt` are shipped in the container. `index.html` has factual `SoftwareApplication` JSON-LD for Koschei Lang 0.10.0 and the existing USD 49 Individual checkout; do not invent reviews, ratings, customers or endorsements. These files do not establish or guarantee search indexing, and Google Search Console ownership has not been verified.

Product Hunt submission requires an account-owned launch, accurate media and actual authentic screenshots; text drafts are in the separately retained global launch kit. The shipped static tutorial remains **not** a browser-based compiler.
