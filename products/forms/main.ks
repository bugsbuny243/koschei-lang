// Koschei Forms: a self-hosted form backend.
//
// Static sites post their forms here; the administrator reads the
// submissions and exports them as CSV. `ks caps main.ks` lists everything
// this program can reach: one database file, one port, one environment
// variable, the clock and the random source. Nothing else.

import csv
import http
import json
import pages
import rules
import secure
import time

// What a request asks for: kind is one of home, submit, admin, login,
// logout, create, view, export, not_found, wrong_method.
struct Action {
    kind: String,
    slug: String,
}

struct Reply {
    status: Int,
    headers: Map<String, String>,
    body: String,
}

fn route(method: String, target: String) -> Action {
    let path = http.path_of(target)
    if path == "/" {
        return Action { kind: "home", slug: "" }
    }
    let submit = http.route("/f/:slug", target)
    match submit {
        Some(found) => {
            if method != "POST" {
                return Action { kind: "wrong_method", slug: "" }
            }
            return Action { kind: "submit", slug: found.get("slug") or "" }
        },
        None => {},
    }
    if path == "/admin" {
        return Action { kind: "admin", slug: "" }
    }
    if path == "/admin/login" || path == "/admin/logout" || path == "/admin/forms" {
        if method != "POST" {
            return Action { kind: "wrong_method", slug: "" }
        }
        if path == "/admin/login" {
            return Action { kind: "login", slug: "" }
        }
        if path == "/admin/logout" {
            return Action { kind: "logout", slug: "" }
        }
        return Action { kind: "create", slug: "" }
    }
    let export = http.route("/admin/f/:slug/csv", target)
    match export {
        Some(found) => {
            return Action { kind: "export", slug: found.get("slug") or "" }
        },
        None => {},
    }
    let view = http.route("/admin/f/:slug", target)
    match view {
        Some(found) => {
            return Action { kind: "view", slug: found.get("slug") or "" }
        },
        None => {},
    }
    return Action { kind: "not_found", slug: "" }
}

fn security_headers(content_type: String) -> Map<String, String> {
    return {
        "Content-Type": content_type,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
    }
}

fn page(status: Int, body: String) -> Reply {
    return Reply { status: status, headers: security_headers("text/html; charset=utf-8"), body: body }
}

fn redirect(location: String) -> Reply {
    let headers = security_headers("text/plain; charset=utf-8").set("Location", location)
    return Reply { status: 303, headers: headers, body: "" }
}

fn session_cookie(token: String, max_age: Int) -> String {
    return "kf_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={max_age}"
}

fn origin_of(request: HttpRequest) -> String {
    let host = request.header("Host") or "your-server"
    let scheme = request.header("X-Forwarded-Proto") or "http"
    if scheme == "https" {
        return "https://" + host
    }
    return "http://" + host
}

// An empty result. "[]" always parses; the fallback only satisfies the type.
fn no_rows() -> Data {
    let rows = parse_json("[]") or return no_rows()
    return rows
}

fn no_fields() -> Map<String, String> {
    let fields: Map<String, String> = {}
    return fields
}

fn count_of(rows: Data) -> Int {
    let first = json_at(rows, 0) or return 0
    let value = json_get(first, "n") or return 0
    return json_int(value) or 0
}

fn serve(server: ServeCaps, db: DbCaps, clock: ClockCaps, random: RandomCaps, password: String, rounds: Int) -> Int {
    let made_forms = db.exec("CREATE TABLE IF NOT EXISTS forms (slug TEXT PRIMARY KEY, redirect_url TEXT NOT NULL DEFAULT '', created_ms INTEGER NOT NULL)", "[]") or 0
    let made_submissions = db.exec("CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL, received TEXT NOT NULL, fields TEXT NOT NULL)", "[]") or 0
    let made_index = db.exec("CREATE INDEX IF NOT EXISTS submissions_slug ON submissions (slug, id)", "[]") or 0
    let made_sessions = db.exec("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires_ms INTEGER NOT NULL)", "[]") or 0
    let made_failures = db.exec("CREATE TABLE IF NOT EXISTS login_failures (at_ms INTEGER NOT NULL)", "[]") or 0
    let password_hash = secure.hash(password) or ""
    let admin_enabled = password.length() >= 12

    let mut served = 0
    while served < rounds {
        served = served + 1
        let request = server.accept() or {
            continue
        }
        let now = clock.now_ms()
        let action = route(request.method(), request.path())
        let mut reply = page(404, pages.message("Not found", "There is nothing here."))

        // Admin routes need a live session.
        let cookie = request.header("Cookie") or ""
        let token = http.cookies(cookie).get("kf_session") or ""
        let token_hash = secure.hash(token) or ""
        let live = db.query("SELECT count(*) AS n FROM sessions WHERE token_hash = ? AND expires_ms > ?", json.array([json.string(token_hash), json.int(now)])) or no_rows()
        let signed_in = admin_enabled && token.length() == 64 && count_of(live) == 1

        let slug = action.slug
        if action.slug.length() > 0 && !rules.valid_slug(action.slug) {
            reply = page(404, pages.message("Unknown form", "This form does not exist."))
        } else if action.kind == "home" {
            reply = page(200, pages.home())
        } else if action.kind == "wrong_method" {
            reply = page(405, pages.message("Method not allowed", "This address does not accept that request."))
        } else if action.kind == "submit" {
            let known = db.query("SELECT redirect_url FROM forms WHERE slug = ?", json.array([json.string(slug)])) or no_rows()
            let form = json_at(known, 0) or {
                reply = page(404, pages.message("Unknown form", "This form does not exist."))
                let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                    continue
                }
                continue
            }
            let body = request.body() or ""
            let fields = http.params(body) or {
                reply = page(400, pages.message("Bad request", "The form data could not be read."))
                let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                    continue
                }
                continue
            }
            if !rules.is_spam(fields) {
                let received = time.iso_utc(now) or ""
                let stored = db.exec("INSERT INTO submissions (slug, received, fields) VALUES (?, ?, ?)", json.array([json.string(slug), json.string(received), json.string(rules.submission_json(fields))])) or -1
                if stored != 1 {
                    reply = page(500, pages.message("Not saved", "The submission could not be saved. Please try again."))
                    let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                        continue
                    }
                    continue
                }
            }
            let target_value = json_get(form, "redirect_url") or no_rows()
            let target = json_text(target_value) or ""
            if target.length() > 0 {
                reply = redirect(target)
            } else {
                reply = page(200, pages.thanks())
            }
        } else if action.kind == "login" {
            let failures = db.query("SELECT count(*) AS n FROM login_failures WHERE at_ms > ?", json.array([json.int(now - 900000)])) or no_rows()
            let body = request.body() or ""
            let fields = http.params(body) or no_fields()
            let given = fields.get("password") or ""
            let given_hash = secure.hash(given) or "-"
            if !admin_enabled {
                reply = page(503, pages.login("Set KOSCHEI_FORMS_PASSWORD (12 characters or more) and restart the server."))
            } else if count_of(failures) >= 10 {
                reply = page(429, pages.login("Too many failed attempts. Wait 15 minutes."))
            } else if rules.same_digest(given_hash, password_hash) {
                let fresh = random.hex(32) or ""
                let fresh_hash = secure.hash(fresh) or ""
                let saved = db.exec("INSERT INTO sessions (token_hash, expires_ms) VALUES (?, ?)", json.array([json.string(fresh_hash), json.int(now + 43200000)])) or 0
                let cleaned = db.exec("DELETE FROM sessions WHERE expires_ms < ?", json.array([json.int(now)])) or 0
                if fresh.length() == 64 && saved == 1 {
                    reply = redirect("/admin")
                    reply.headers = reply.headers.set("Set-Cookie", session_cookie(fresh, 43200))
                } else {
                    reply = page(500, pages.login("Could not start a session."))
                }
            } else {
                let noted = db.exec("INSERT INTO login_failures (at_ms) VALUES (?)", json.array([json.int(now)])) or 0
                reply = page(401, pages.login("Wrong password."))
            }
        } else if action.kind == "logout" {
            let ended = db.exec("DELETE FROM sessions WHERE token_hash = ?", json.array([json.string(token_hash)])) or 0
            reply = redirect("/admin")
            reply.headers = reply.headers.set("Set-Cookie", session_cookie("", 0))
        } else if action.kind == "admin" {
            if !signed_in {
                reply = page(200, pages.login(""))
            } else {
                let forms = db.query("SELECT f.slug AS slug, f.redirect_url AS redirect_url, (SELECT count(*) FROM submissions s WHERE s.slug = f.slug) AS total FROM forms f ORDER BY f.slug", "[]") or no_rows()
                reply = page(200, pages.dashboard(forms, origin_of(request), ""))
            }
        } else if action.kind == "create" {
            if !signed_in {
                reply = redirect("/admin")
            } else {
                let body = request.body() or ""
                let fields = http.params(body) or no_fields()
                let slug = fields.get("slug") or ""
                let target = fields.get("redirect_url") or ""
                let forms = db.query("SELECT f.slug AS slug, f.redirect_url AS redirect_url, (SELECT count(*) FROM submissions s WHERE s.slug = f.slug) AS total FROM forms f ORDER BY f.slug", "[]") or no_rows()
                if !rules.valid_slug(slug) {
                    reply = page(400, pages.dashboard(forms, origin_of(request), "A form name is 1 to 40 lowercase letters, digits or '-'."))
                } else if !rules.valid_redirect(target) {
                    reply = page(400, pages.dashboard(forms, origin_of(request), "The redirect must be an http(s) address without spaces or quotes."))
                } else {
                    let added = db.exec("INSERT OR IGNORE INTO forms (slug, redirect_url, created_ms) VALUES (?, ?, ?)", json.array([json.string(slug), json.string(target), json.int(now)])) or 0
                    if added == 1 {
                        reply = redirect("/admin")
                    } else {
                        reply = page(409, pages.dashboard(forms, origin_of(request), "A form with that name already exists."))
                    }
                }
            }
        } else if action.kind == "view" {
            if !signed_in {
                reply = redirect("/admin")
            } else {
                let rows = db.query("SELECT id, received, fields FROM submissions WHERE slug = ? ORDER BY id DESC LIMIT 200", json.array([json.string(slug)])) or no_rows()
                let totals = db.query("SELECT count(*) AS n FROM submissions WHERE slug = ?", json.array([json.string(slug)])) or no_rows()
                let shown = json_length(rows) or 0
                reply = page(200, pages.submissions(slug, rows, shown, count_of(totals)))
            }
        } else if action.kind == "export" {
            if !signed_in {
                reply = redirect("/admin")
            } else {
                let rows = db.query("SELECT id, received, fields FROM submissions WHERE slug = ? ORDER BY id", json.array([json.string(slug)])) or no_rows()
                let text = csv.export(rows) or ""
                let headers = security_headers("text/csv; charset=utf-8").set("Content-Disposition", "attachment; filename=\"" + slug + ".csv\"")
                reply = Reply { status: 200, headers: headers, body: text }
            }
        }
        let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
            continue
        }
    }
    return served
}

fn main(caps: SystemCaps) {
    while true {
        let server = caps.serve.allow("0.0.0.0:8080", 4096, 65536, 4194304, 10000)
        let db = caps.db.allow("/data/koschei-forms.db", 100000, 1073741824, 5000)
        let clock = caps.clock.allow(1)
        let random = caps.random.allow(262144)
        let password = caps.env.allow("KOSCHEI_FORMS_PASSWORD").get() or ""
        let served = serve(server, db, clock, random, password, 4096)
    }
}
