// Koschei Forms: HTML pages. Pure. Every value from a submitter or from the
// disk passes through http.escape_html before it reaches a page.

import http

fn layout(title: String, body: String) -> String {
    let style = ":root\{--bg:#f6f7f9;--card:#fff;--ink:#14161a;--muted:#6b7280;--line:#e5e7eb;--accent:#4f46e5;--accent-ink:#fff;--soft:#eef2ff;--code:#0f172a;--code-ink:#e2e8f0;--err:#b42318;--err-bg:#fef3f2\}@media (prefers-color-scheme:dark)\{:root\{--bg:#0b0d12;--card:#141821;--ink:#e6e8ee;--muted:#9aa3b2;--line:#252b36;--accent:#818cf8;--accent-ink:#0b0d12;--soft:#1e2340;--code:#05070b;--code-ink:#cbd5e1;--err:#fda29b;--err-bg:#2a1414\}\}*\{box-sizing:border-box\}body\{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,\"Segoe UI\",Roboto,sans-serif\}.top\{background:var(--card);border-bottom:1px solid var(--line)\}.top div\{max-width:980px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:16px\}.brand\{font-weight:700;letter-spacing:-.01em;color:var(--ink);text-decoration:none;display:flex;align-items:center;gap:8px\}.brand i\{width:22px;height:22px;border-radius:6px;background:var(--accent);display:inline-block\}nav\{margin-left:auto;display:flex;align-items:center;gap:12px\}nav a\{color:var(--muted);text-decoration:none;font-weight:500\}nav a:hover\{color:var(--ink)\}nav form\{display:inline;margin:0\}main\{max-width:980px;margin:0 auto;padding:28px 20px 48px\}h1\{font-size:26px;letter-spacing:-.02em;margin:0 0 6px\}h2\{font-size:17px;margin:0 0 14px\}p\{margin:0 0 14px\}.card\{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0\}table\{border-collapse:collapse;width:100%\}th\{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;text-align:left;padding:0 12px 10px\}td\{border-top:1px solid var(--line);padding:12px;text-align:left;vertical-align:top;font-size:14px\}td a\{color:var(--accent);font-weight:600;text-decoration:none\}td a:hover\{text-decoration:underline\}.forms td:nth-child(2),.subs td:first-child\{font-variant-numeric:tabular-nums;font-weight:600\}.subs td:nth-child(2)\{color:var(--muted);white-space:nowrap\}.subs b\{color:var(--muted);font-weight:600\}label\{display:block;font-size:13px;font-weight:600;color:var(--muted);margin:0 0 14px\}input\{display:block;width:100%;max-width:520px;margin-top:6px;padding:10px 12px;font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:10px\}input:focus\{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent\}button\{font:inherit;font-weight:600;padding:9px 16px;border-radius:10px;border:0;background:var(--accent);color:var(--accent-ink);cursor:pointer\}button:hover\{filter:brightness(1.08)\}nav button\{background:transparent;color:var(--muted);border:1px solid var(--line);padding:6px 12px\}pre\{background:var(--code);color:var(--code-ink);padding:16px;border-radius:12px;overflow-x:auto;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0 0 12px\}code\{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--soft);padding:1px 6px;border-radius:6px\}.muted\{color:var(--muted)\}.error\{color:var(--err);background:var(--err-bg);padding:10px 14px;border-radius:10px\}.center\{max-width:420px;margin:12vh auto 0\}.center .card\{padding:28px\}.lead\{color:var(--muted);font-size:16px\}"
    return "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><meta name=\"color-scheme\" content=\"light dark\"><title>" + http.escape_html(title) + "</title><style>" + style + "</style></head><body>" + body + "</body></html>"
}

// A page for visitors and for signing in: one centred card.
fn plain(title: String, inner: String) -> String {
    return layout(title, "<main class=\"center\"><div class=\"card\">" + inner + "</div></main>")
}

// A signed-in page: the top bar, then the content.
fn admin(title: String, inner: String) -> String {
    return layout(title, "<header class=\"top\"><div><a class=\"brand\" href=\"/admin\"><i></i>Koschei Forms</a>" + nav() + "</div></header><main>" + inner + "</main>")
}

fn home() -> String {
    return plain("Koschei Forms", "<h1>Koschei Forms</h1><p class=\"lead\">This server collects form submissions.</p><p class=\"muted\">The administrator signs in at <a href=\"/admin\">/admin</a>.</p>")
}

fn thanks() -> String {
    return plain("Thank you", "<h1>Thank you</h1><p class=\"lead\">Your message was received.</p>")
}

fn message(title: String, text: String) -> String {
    return plain(title, "<h1>" + http.escape_html(title) + "</h1><p class=\"lead\">" + http.escape_html(text) + "</p>")
}

fn login(error: String) -> String {
    let mut note = ""
    if error.length() > 0 {
        note = "<p class=\"error\">" + http.escape_html(error) + "</p>"
    }
    return plain("Sign in", "<h1>Koschei Forms</h1><p class=\"muted\">Sign in to read your submissions.</p>" + note + "<form method=\"POST\" action=\"/admin/login\"><label>Password<input type=\"password\" name=\"password\" autofocus required></label><button type=\"submit\">Sign in</button></form>")
}

fn nav() -> String {
    return "<nav><a href=\"/admin\">Forms</a><form method=\"POST\" action=\"/admin/logout\"><button type=\"submit\">Sign out</button></form></nav>"
}

// One row per form: slugs[i] receives totals[i] submissions and sends its
// visitor to redirects[i] ("" for the built-in thank-you page). origin is
// how visitors reach this server.
fn dashboard(slugs: List<String>, redirects: List<String>, totals: List<Int>, origin: String, error: String) -> String {
    let mut rows = ""
    let mut i = 0
    while i < slugs.length() {
        let slug = slugs.get(i) or ""
        let redirect = redirects.get(i) or ""
        let total = totals.get(i) or 0
        i = i + 1
        let mut target = "<span class=\"muted\">built-in thank-you page</span>"
        if redirect.length() > 0 {
            target = http.escape_html(redirect)
        }
        let safe = http.escape_html(slug)
        rows = rows + "<tr><td><a href=\"/admin/f/" + safe + "\">" + safe + "</a></td><td>{total}</td><td>" + target + "</td><td><a href=\"/admin/f/" + safe + "/csv\">CSV</a></td></tr>"
    }
    if rows.length() == 0 {
        rows = "<tr><td colspan=\"4\" class=\"muted\">No forms yet. Create one below.</td></tr>"
    }
    let mut note = ""
    if error.length() > 0 {
        note = "<p class=\"error\">" + http.escape_html(error) + "</p>"
    }
    let example = http.escape_html("<form action=\"" + origin + "/f/contact\" method=\"POST\">\n  <input name=\"email\" type=\"email\" required>\n  <textarea name=\"message\"></textarea>\n  <input name=\"_gotcha\" style=\"display:none\">\n  <button type=\"submit\">Send</button>\n</form>")
    let body = "<h1>Forms</h1><p class=\"muted\">Every form, its submissions and where visitors go after sending.</p>" + note + "<div class=\"card\"><table class=\"forms\"><tr><th>Form</th><th>Submissions</th><th>After sending</th><th>Export</th></tr>" + rows + "</table></div><div class=\"card\"><h2>New form</h2><form method=\"POST\" action=\"/admin/forms\"><label>Name (a-z, 0-9, -)<input name=\"slug\" pattern=\"[a-z0-9-]\{1,40\}\" placeholder=\"contact\" required></label><label>Redirect after sending (optional, https://...)<input name=\"redirect_url\" placeholder=\"https://example.com/thanks\"></label><button type=\"submit\">Create</button></form></div><div class=\"card\"><h2>Put it on your site</h2><pre>" + example + "</pre><p class=\"muted\">The hidden <code>_gotcha</code> field catches spam bots. Fields whose names start with <code>_</code> are not stored.</p></div>"
    return admin("Forms", body)
}

// Submission numbers[i] arrived at whens[i] (UTC) with records[i].
fn submissions(slug: String, numbers: List<Int>, whens: List<String>, records: List<Map<String, String>>, shown: Int, total: Int) -> String {
    let mut out = ""
    let mut i = 0
    while i < numbers.length() {
        let number = numbers.get(i) or 0
        let when = whens.get(i) or ""
        let fields: Map<String, String> = records.get(i) or {
            i = i + 1
            continue
        }
        i = i + 1
        let mut cells = ""
        for key in fields.keys() {
            let value = fields.get(key) or ""
            cells = cells + "<b>" + http.escape_html(key) + "</b>: " + http.escape_html(value) + "<br>"
        }
        out = out + "<tr><td>{number}</td><td>" + http.escape_html(when) + "</td><td>" + cells + "</td></tr>"
    }
    if out.length() == 0 {
        out = "<tr><td colspan=\"3\" class=\"muted\">No submissions yet.</td></tr>"
    }
    let safe = http.escape_html(slug)
    let body = "<h1>" + safe + "</h1><p class=\"muted\">Showing the latest {shown} of {total}. <a href=\"/admin/f/" + safe + "/csv\">Download all as CSV</a></p><div class=\"card\"><table class=\"subs\"><tr><th>#</th><th>Received (UTC)</th><th>Fields</th></tr>" + out + "</table></div>"
    return admin(slug, body)
}
