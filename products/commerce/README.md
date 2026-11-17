# Koschei Commerce — self-hosted single-store ordering system

**Status:** functional, tested initial implementation in the Koschei Lang repository. This is not yet a deployed public shop. Shipping, payment processing, marketplace/multi-seller support and customer accounts are **not implemented**. No fictitious goods or fake completed payments are shown.

## Real capabilities

- A responsive, interactive **storefront** showing merchant-managed products, stock and tax-inclusive TRY prices.
- A **cart** whose authoritative totals come from **Koschei Lang** source \`pricing.ks\`, invoked as a fixed source file with **input-only capability**. There is no hidden JavaScript or Python pricing fallback.
- Real guest **pickup order requests**, saved to a persistent SQLite database when \`COMMERCE_ACCEPT_ORDERS=1\`. Email and name are stored with the order; payment/card data is never collected.
- **Merchant sign-in** using a strong environment-supplied password; hashed session token database rows and \`Secure; HttpOnly; SameSite=Strict\` cookies.
- Merchant product creation, price/stock/availability updates, order lists, and order transitions:
  - \`pending -> accepted\`: stock is decremented atomically and only if available.
  - \`accepted -> fulfilled\`: the item is marked handed over.
  - \`pending/accepted -> cancelled\`: accepted items are restocked atomically.
- Guest retries require a unique **idempotency key**; the same request creates **only one** order.
- Strict HTTP origin checks for mutations, CSP nonces, typed/bounded JSON, rate limits, SQL parameters, a bounded process invocation and no public source-code execution.
- Product/sale amounts are **minor currency units (integer kuruş)** end-to-end.
- The original Koschei Lang site and disabled \`/play\` are separate and unchanged.

## Merchant catalog photos and categories (v1.1)

- Open the existing **/admin** merchant panel, create a product with SKU, name, category, tax-inclusive TRY price, stock and visibility.
- Select a phone photo (**JPEG, PNG or WebP**, maximum **2 MB**) in the product form and save. The backend validates and completely decodes the file, applies the EXIF orientation, resizes to a maximum of 960 px and re-encodes it as a JPEG with the original metadata removed.
- The photo is stored as a bounded BLOB in the **existing /data/commerce.db SQLite volume**. It does not require a paid object storage service, external image host or user-uploaded URL. Product display image URLs are generated internally; only an authenticated merchant can upload or remove photos.
- The storefront supports live product-name/description/SKU search, category selection, and price sorting. Missing photos show neutral placeholders rather than fabricated merchandise.
- Existing databases are **migrated in place** by adding a `category` field with `Genel` as default. Existing orders and product SKUs are preserved.
- Optional images still count toward Railway volume storage. Backup the SQLite database and check usage if many products are added. Image uploads are restricted to a merchant session and exact allowed origin.
- **Public order acceptance remains off by default** and no card information is processed.

## Merchant operations: CSV, audit history and SQLite backup

The existing merchant dashboard at \`/admin\` includes three additional operations:

1. **Bulk CSV product creation.** Download the blank UTF-8 template and fill its semicolon-separated columns:
   \`sku;name;category;description;price_try;stock;active\`.
   Example product data: \`stok-alarm;Stok Alarm;Yazılım;Stok kontrolü;2800.00;12;1\`.
   \`price_try\` is a **TRY amount**, with dot or comma decimals; \`active\` must be \`1\` (visible) or \`0\` (hidden).
   A file may contain **1–100 products** and must be **no larger than 64 KiB**.
   Select the CSV, click **Dosyayı kontrol et**, and only then explicitly confirm **Kontrol edilen ürünleri ekle**.
   Existing SKUs are **never overwritten**. The entire import rejects if any SKU already exists, any input row is invalid, or the 1,000-product catalog limit would be exceeded. Either every new item is committed or none is; preview does not modify stock.
   Photos are uploaded per product separately via the existing merchant editor.
2. **Stock movement timeline.** Manual edits, newly created products, CSV imports and accepted/cancelled orders are recorded in the same SQLite transaction as their stock changes. The merchant sees the last 200 changes with timestamp, SKU, delta, resulting stock and a referenced order ID (when applicable). An order failure rolls back its history entries too. Existing historical transactions are **not fabricated** on migration.
3. **Manual database backup.** Click **Veritabanını indir (.sqlite3)** to generate a consistent SQLite backup through the built-in \`sqlite3.backup\` API. It is downloaded over the authenticated, same-origin merchant session. Active merchant session rows are removed from **the downloaded copy only**, not from the live database. The downloaded database includes product images, stock history and any guest name/email/order notes already stored. Keep backups private and protected; this feature is **not automated cloud backup**. Files over 64 MiB are rejected to avoid exhausting Hobby memory; use managed volume backups when the store grows. The temporary server snapshot is written in \`/tmp\`, not to the limited Railway \`/data\` volume, and is removed after download.

**Restore:** There is intentionally no public or browser-upload "restore database" endpoint. Restoring a snapshot must be done in a maintenance window by an authorized administrator, with the service stopped, a new verified volume backup, and a test restore before replacing any live file. Never overwrite a live SQLite WAL database directly.

The storefront remains unchanged for guests. These operations require merchant authentication. They do not enable payment or guest order acceptance.

## Files

| File | Responsibility |
| --- | --- |
| \`pricing.ks\` | The trusted Koschei Lang pricing calculation |
| \`storage.py\` | SQLite schema, transactions, catalog, orders, stock, sessions |
| \`server.py\` | Strict HTTP API, admin session controls and static serving |
| \`storefront.html\` | Real mobile shopping + merchant operations interface |
| \`Dockerfile\` | Container build with installed Koschei interpreter and non-root service |
| \`tests/test_commerce_mvp_v1.py\` | Persistent HTTP, order and stock integrity tests |

The repository's \`examples/commerce_workspace\` contains the language's package-graph reference implementations for \`domain/catalog/orders\`. This product extends those concepts into a functioning web service; the existing workspace example itself is not a complete store.

## Run locally with a persistent SQLite volume

Build at the repository root:

\`\`\`sh
docker build -f products/commerce/Dockerfile -t koschei-commerce .
docker volume create koschei-commerce-data
docker run --rm -p 8080:8080 \
  -v koschei-commerce-data:/data \
  -e COMMERCE_PUBLIC_ORIGIN=http://127.0.0.1:8080 \
  -e COMMERCE_ADMIN_PASSWORD='replace-with-unique-strong-password-16-chars' \
  -e COMMERCE_STORE_NAME='My Store' \
  -e COMMERCE_ACCEPT_ORDERS=0 \
  koschei-commerce
\`\`\`

Visit \`http://127.0.0.1:8080/admin\`. Sign in to create products, then view the catalog at \`/\`. The browser requests are same-origin; **do not publish without HTTPS**. For an online shop set the public origin to the exact \`https://shop.example.com\` origin.

The production server **refuses to start** unless \`COMMERCE_DB_PATH\` is under \`/data\` and a /data directory exists. The deployment operator must ensure **/data is backed by a durable volume**; merely creating a writable directory in a container is not enough. A Railway ephemeral filesystem is not acceptable for real orders.

After configuring and testing merchant access, HTTPS, persistence, backups, privacy disclosure and abuse protection, set \`COMMERCE_ACCEPT_ORDERS=1\`. The default is **off**.

## Production requirements before collecting customer information

1. Provision a **persistent /data volume**, confirm restore from backup, and configure the SQLite file there.
2. Set a strong \`COMMERCE_ADMIN_PASSWORD\` (16+ characters), exact \`COMMERCE_PUBLIC_ORIGIN\`, and private merchant/store name. Never commit passwords or live customer details.
3. Enable HTTPS and verify secure admin cookies, CSRF origin checks and that only the merchant has panel access.
4. Run **one service replica**, since this initial version uses a local SQLite database and a per-process rate limiter. Put an edge rate limiter/captcha on public order submission for production.
5. Publish an appropriate privacy notice and retention/deletion policy; the database contains customer names, email addresses and their pickup note. Backup and access controls matter.
6. Only enable order requests once a real merchant is ready to receive and process them. The platform makes **no promise** of automatic shipping, billing, tax calculation or online payment.
7. For any public payment system, integrate a licensed payment provider separately, with verified webhook signatures and server-side reconciliation. Do not attempt to store card details in this app.

## API (single store; JSON over HTTPS)

| Route | Action |
| --- | --- |
| GET \`/api/config\` | Store name, pickup/payment availability |
| GET \`/api/products\` | Public active product catalog |
| POST \`/api/cart/quote\` | Real Koschei cart total for selected SKUs |
| POST \`/api/orders\` | Persist a pickup request (only when enabled) |
| POST \`/api/admin/login\` | Merchant sign-in; HttpOnly session cookie |
| POST \`/api/admin/logout\` | Revoke current session |
| GET \`/api/admin/session\` | Verify merchant session |
| GET / POST \`/api/admin/products\` | List/create merchant products |
| PATCH \`/api/admin/products/:sku\` | Update product and stock |
| GET \`/api/admin/orders\` | List order requests with contact details |
| PATCH \`/api/admin/orders/:id\` | \`accept\`, \`fulfill\`, \`cancel\` |
| GET \`/health\` | Application health probe |

## Verification

\`\`\`sh
python -m pip install -e . pytest "Pillow>=11.0,<13.0"
python -m pytest -q tests/test_commerce_mvp_v1.py tests/test_commerce_media_v1.py tests/test_commerce_merchant_ops_v1.py
ks check products/commerce/pricing.ks
ks caps products/commerce/pricing.ks
\`\`\`

See GitHub Actions workflow \`.github/workflows/commerce-core.yml\`.

**Important:** Completed tests do not prove PCI/GDPR/KVKK compliance, production payment readiness, horizontal scaling or real customer fulfillment. Treat this as a functional, self-hostable single-merchant order platform with explicitly limited scope.
