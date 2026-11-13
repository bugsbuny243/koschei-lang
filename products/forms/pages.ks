// Koschei Forms: HTML pages. Pure. Every value from a submitter or from the
// database passes through http.escape_html before it reaches a page.

import http

fn layout(title: String, body: String) -> String {
    let style = "body\{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 16px;color:#1d1d1f\}h1\{font-size:22px\}table\{border-collapse:collapse;width:100%\}td,th\{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;font-size:14px\}input\{padding:8px;margin:4px 0;font-size:14px\}button\{padding:8px 14px;font-size:14px\}code,pre\{background:#f4f4f5;padding:2px 4px\}pre\{padding:12px;overflow-x:auto\}.muted\{color:#666\}.error\{color:#b00020\}nav form\{display:inline\}"
    return "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>" + http.escape_html(title) + "</title><style>" + style + "</style></head><body>" + body + "</body></html>"
}

fn home() -> String {
    return layout("Koschei Forms", "<h1>Koschei Forms</h1><p>This server collects form submissions. The administrator signs in at <a href=\"/admin\">/admin</a>.</p>")
}

fn thanks() -> String {
    return layout("Thank you", "<h1>Thank you</h1><p>Your message was received.</p>")
}

fn message(title: String, text: String) -> String {
    return layout(title, "<h1>" + http.escape_html(title) + "</h1><p>" + http.escape_html(text) + "</p>")
}

fn login(error: String) -> String {
    let mut note = ""
    if error.length() > 0 {
        note = "<p class=\"error\">" + http.escape_html(error) + "</p>"
    }
    return layout("Sign in", "<h1>Koschei Forms</h1>" + note + "<form method=\"POST\" action=\"/admin/login\"><label>Password<br><input type=\"password\" name=\"password\" autofocus required></label><br><button type=\"submit\">Sign in</button></form>")
}

fn nav() -> String {
    return "<nav><a href=\"/admin\">Forms</a> · <form method=\"POST\" action=\"/admin/logout\"><button type=\"submit\">Sign out</button></form></nav>"
}

// forms: [{slug, redirect_url, total}], origin: how visitors reach this server.
fn dashboard(forms: Data, origin: String, error: String) -> String {
    let items = json_items(forms) or []
    let mut rows = ""
    for item in items {
        let slug_value = json_get(item, "slug") or {
            continue
        }
        let slug = json_text(slug_value) or ""
        let total_value = json_get(item, "total") or {
            continue
        }
        let total = json_int(total_value) or 0
        let redirect_value = json_get(item, "redirect_url") or {
            continue
        }
        let redirect = json_text(redirect_value) or ""
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
    let body = "<h1>Forms</h1>" + nav() + note + "<table><tr><th>Form</th><th>Submissions</th><th>After sending</th><th>Export</th></tr>" + rows + "</table><h2>New form</h2><form method=\"POST\" action=\"/admin/forms\"><label>Name (a-z, 0-9, -)<br><input name=\"slug\" pattern=\"[a-z0-9-]\{1,40\}\" required></label><br><label>Redirect after sending (optional, https://...)<br><input name=\"redirect_url\" size=\"60\"></label><br><button type=\"submit\">Create</button></form><h2>Put it on your site</h2><pre>" + example + "</pre><p class=\"muted\">The hidden _gotcha field catches spam bots. Fields whose names start with _ are not stored.</p>"
    return layout("Forms", body)
}

// rows: [{id, received, fields}] where fields is the stored JSON text.
fn submissions(slug: String, rows: Data, shown: Int, total: Int) -> String {
    let items = json_items(rows) or []
    let mut out = ""
    for item in items {
        let id_value = json_get(item, "id") or {
            continue
        }
        let id = json_int(id_value) or 0
        let when_value = json_get(item, "received") or {
            continue
        }
        let when = json_text(when_value) or ""
        let fields_value = json_get(item, "fields") or {
            continue
        }
        let raw = json_text(fields_value) or ""
        let fields = parse_json(raw) or {
            continue
        }
        let keys = json_keys(fields) or []
        let mut cells = ""
        for key in keys {
            let value = json_get(fields, key) or {
                continue
            }
            let text = json_text(value) or ""
            cells = cells + "<b>" + http.escape_html(key) + "</b>: " + http.escape_html(text) + "<br>"
        }
        out = out + "<tr><td>{id}</td><td>" + http.escape_html(when) + "</td><td>" + cells + "</td></tr>"
    }
    if out.length() == 0 {
        out = "<tr><td colspan=\"3\" class=\"muted\">No submissions yet.</td></tr>"
    }
    let safe = http.escape_html(slug)
    let body = "<h1>" + safe + "</h1>" + nav() + "<p>Showing the latest {shown} of {total}. <a href=\"/admin/f/" + safe + "/csv\">Download all as CSV</a></p><table><tr><th>#</th><th>Received (UTC)</th><th>Fields</th></tr>" + out + "</table>"
    return layout(slug, body)
}
