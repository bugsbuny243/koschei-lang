// Koschei Forms: a self-hosted form backend.
//
// Static sites post their forms here; the administrator reads the
// submissions and exports them as CSV. `ks caps main.ks` lists everything
// this program can reach: one directory, one port, one environment
// variable, the clock and the random source. Nothing else. Built with
// `ks build`, it runs as a broker that holds that authority and a worker,
// confined by seccomp, that runs this code.

import csv
import http
import pages
import rules
import secure
import store
import text
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

// Where every file lives: the disk scope main() grants.
fn root() -> String {
    return "/data/koschei-forms"
}

fn at(name: String) -> String {
    return root() + "/" + name
}

fn no_fields() -> Map<String, String> {
    let fields: Map<String, String> = {}
    return fields
}

fn no_names() -> List<String> {
    let names: List<String> = []
    return names
}

fn serve(server: ServeCaps, disk: DiskCaps, clock: ClockCaps, random: RandomCaps, password: String, rounds: Int) -> Int {
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

        // Admin routes need a live session: a file named after the token's
        // digest whose expiry is still ahead.
        let cookie = request.header("Cookie") or ""
        let token = http.cookies(cookie).get("kf_session") or ""
        let token_hash = secure.hash(token) or ""
        let expiry_text = disk.read(at(store.session_name(token_hash))) or "0"
        let expiry = expiry_text.to_int() or 0
        let signed_in = admin_enabled && token.length() == 64 && expiry > now

        // The dashboard's rows: every form, its redirect and its count.
        // Capability tokens move into the functions they are passed to, so
        // the listing is read here rather than in a helper.
        let mut dash_slugs: List<String> = []
        let mut dash_redirects: List<String> = []
        let mut dash_totals: List<Int> = []
        if signed_in && (action.kind == "admin" || action.kind == "create") {
            let listed = disk.list(root()) or no_names()
            dash_slugs = store.form_slugs(listed)
            for form_slug in dash_slugs {
                dash_redirects = dash_redirects.push(disk.read(at(store.form_name(form_slug))) or "")
                dash_totals = dash_totals.push(store.submissions_of(listed, form_slug).length())
            }
        }

        let slug = action.slug
        if action.slug.length() > 0 && !rules.valid_slug(action.slug) {
            reply = page(404, pages.message("Unknown form", "This form does not exist."))
        } else if action.kind == "home" {
            reply = page(200, pages.home())
        } else if action.kind == "wrong_method" {
            reply = page(405, pages.message("Method not allowed", "This address does not accept that request."))
        } else if action.kind == "submit" {
            let target = disk.read(at(store.form_name(slug))) or {
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
                let nonce = random.hex(8) or ""
                let stored = disk.write(at(store.submission_name(slug, now, nonce)), store.submission_body(fields)) or {
                    reply = page(500, pages.message("Not saved", "The submission could not be saved. Please try again."))
                    let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                        continue
                    }
                    continue
                }
            }
            if target.length() > 0 {
                reply = redirect(target)
            } else {
                reply = page(200, pages.thanks())
            }
        } else if action.kind == "login" {
            let names = disk.list(root()) or no_names()
            let body = request.body() or ""
            let fields = http.params(body) or no_fields()
            let given = fields.get("password") or ""
            let given_hash = secure.hash(given) or "-"
            if !admin_enabled {
                reply = page(503, pages.login("Set KOSCHEI_FORMS_PASSWORD (12 characters or more) and restart the server."))
            } else if store.failures_since(names, now - 900000) >= 10 {
                reply = page(429, pages.login("Too many failed attempts. Wait 15 minutes."))
            } else if rules.same_digest(given_hash, password_hash) {
                let fresh = random.hex(32) or ""
                let fresh_hash = secure.hash(fresh) or ""
                let saved = disk.write(at(store.session_name(fresh_hash)), "{now + 43200000}") or {
                    reply = page(500, pages.login("Could not start a session."))
                    let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                        continue
                    }
                    continue
                }
                // Forget expired sessions and old failures.
                for name in names {
                    if text.starts_with(name, "fail_") && store.time_of(name, "fail_") <= now - 900000 {
                        let dropped = disk.delete(at(name)) or {
                            continue
                        }
                    } else if text.starts_with(name, "session_") {
                        let until_text = disk.read(at(name)) or "0"
                        let until = until_text.to_int() or 0
                        if until <= now {
                            let dropped = disk.delete(at(name)) or {
                                continue
                            }
                        }
                    }
                }
                if fresh.length() == 64 {
                    reply = redirect("/admin")
                    reply.headers = reply.headers.set("Set-Cookie", session_cookie(fresh, 43200))
                } else {
                    reply = page(500, pages.login("Could not start a session."))
                }
            } else {
                let nonce = random.hex(8) or ""
                let noted = disk.write(at(store.failure_name(now, nonce)), "1") or {
                    reply = page(500, pages.login("Wrong password."))
                    let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                        continue
                    }
                    continue
                }
                reply = page(401, pages.login("Wrong password."))
            }
        } else if action.kind == "logout" {
            if token.length() == 64 {
                let ended = disk.delete(at(store.session_name(token_hash))) or {
                    reply = redirect("/admin")
                    reply.headers = reply.headers.set("Set-Cookie", session_cookie("", 0))
                    let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                        continue
                    }
                    continue
                }
            }
            reply = redirect("/admin")
            reply.headers = reply.headers.set("Set-Cookie", session_cookie("", 0))
        } else if action.kind == "admin" {
            if !signed_in {
                reply = page(200, pages.login(""))
            } else {
                reply = page(200, pages.dashboard(dash_slugs, dash_redirects, dash_totals, origin_of(request), ""))
            }
        } else if action.kind == "create" {
            if !signed_in {
                reply = redirect("/admin")
            } else {
                let body = request.body() or ""
                let fields = http.params(body) or no_fields()
                let slug = fields.get("slug") or ""
                let target = fields.get("redirect_url") or ""
                if !rules.valid_slug(slug) {
                    reply = page(400, pages.dashboard(dash_slugs, dash_redirects, dash_totals, origin_of(request), "A form name is 1 to 40 lowercase letters, digits or '-'."))
                } else if !rules.valid_redirect(target) {
                    reply = page(400, pages.dashboard(dash_slugs, dash_redirects, dash_totals, origin_of(request), "The redirect must be an http(s) address without spaces or quotes."))
                } else {
                    let existing = disk.read(at(store.form_name(slug))) or "-missing-"
                    if existing != "-missing-" {
                        reply = page(409, pages.dashboard(dash_slugs, dash_redirects, dash_totals, origin_of(request), "A form with that name already exists."))
                    } else {
                        let added = disk.write(at(store.form_name(slug)), target) or {
                            reply = page(500, pages.dashboard(dash_slugs, dash_redirects, dash_totals, origin_of(request), "The form could not be saved."))
                            let sent = server.reply_with(reply.status, reply.headers, reply.body) or {
                                continue
                            }
                            continue
                        }
                        reply = redirect("/admin")
                    }
                }
            }
        } else if action.kind == "view" || action.kind == "export" {
            if !signed_in {
                reply = redirect("/admin")
            } else {
                let names = disk.list(root()) or no_names()
                let files = store.submissions_of(names, slug)
                let total = files.length()
                // The page shows the latest 200, newest first; the export
                // has every submission, oldest first.
                let mut start = 0
                if action.kind == "view" && total > 200 {
                    start = total - 200
                }
                let mut numbers: List<Int> = []
                let mut whens: List<String> = []
                let mut records: List<Map<String, String>> = []
                let mut i = total - 1
                if action.kind == "export" {
                    i = 0
                }
                while i >= start && i < total {
                    let name = files.get(i) or ""
                    let content = disk.read(at(name)) or ""
                    numbers = numbers.push(i + 1)
                    whens = whens.push(time.iso_utc(store.time_of(name, store.submission_prefix(slug))) or "")
                    records = records.push(http.params(content) or no_fields())
                    if action.kind == "export" {
                        i = i + 1
                    } else {
                        i = i - 1
                    }
                }
                if action.kind == "view" {
                    reply = page(200, pages.submissions(slug, numbers, whens, records, numbers.length(), total))
                } else {
                    let headers = security_headers("text/csv; charset=utf-8").set("Content-Disposition", "attachment; filename=\"" + slug + ".csv\"")
                    reply = Reply { status: 200, headers: headers, body: csv.export(whens, records) }
                }
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
        let disk = caps.disk.allow("/data/koschei-forms")
        let clock = caps.clock.allow(1)
        let random = caps.random.allow(262144)
        let password = caps.env.allow("KOSCHEI_FORMS_PASSWORD").get() or ""
        let served = serve(server, disk, clock, random, password, 4096)
    }
}
