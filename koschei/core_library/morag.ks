// Koschei Core Library — Marvel universe: morag
//
// An abandoned artifact expires. Every admitted artifact has a support
// window: who maintains it and until which day. After the window ends it is
// not admitted unless a named maintainer has published a dated backport
// statement for exactly that artifact. Without a known window it is not
// admitted at all: unknown support is treated as no support.
//
// Identities are content digests ("sha3-256:" + hex), never version labels,
// so a backported build is a different identity with its own window. Days
// count from 1970-01-01 (UTC) and are supplied by the caller: a decision is
// the same wherever and whenever it is replayed.
//
// The PHP2Shell figures behind this planet: 23 million of the 41.9 million
// version-disclosing PHP services ran on branches that no longer receive
// fixes.

import secure

struct SupportWindow {
    identity: String,
    maintainer: String,
    // Last supported day, counted from 1970-01-01 (UTC).
    until_day: Int,
}

struct MaintainerBackport {
    identity: String,
    // Who keeps the expired artifact patched; never empty.
    maintainer: String,
    until_day: Int,
}

struct SupportVerdict {
    admitted: Bool,
    reason: String,
    // Who vouches for the artifact on `today`; empty when nobody does.
    maintainer: String,
    // The day the vouching ends; -1 when nobody vouches.
    until_day: Int,
    verdict_digest: String,
}

// Builds the verdict of `check`; public only because Koschei v1 has no
// private functions.
fn verdict(admitted: Bool, reason: String, identity: String, today: Int, maintainer: String, until_day: Int) -> Result<SupportVerdict, Error> {
    let mut flag = "0"
    if admitted {
        flag = "1"
    }
    let parts = [identity, "{today}", reason, flag, maintainer, "{until_day}"]
    let digest = secure.digest("koschei.marvel.morag.verdict/v1", parts) or return Err(Error("morag.check: verdict is too large to digest"))
    return Ok(SupportVerdict {
        admitted: admitted,
        reason: reason,
        maintainer: maintainer,
        until_day: until_day,
        verdict_digest: digest,
    })
}

fn check(identity: String, today: Int, windows: List<SupportWindow>, backports: List<MaintainerBackport>) -> Result<SupportVerdict, Error> {
    if today < 0 {
        return Err(Error("morag.check: today must be a day counted from 1970-01-01"))
    }
    if !secure.is_digest(identity) {
        return verdict(false, "identity-is-not-a-digest", identity, today, "", -1)
    }
    // Only well-formed windows for this identity count; anything else grants
    // nothing.
    let mut found: List<SupportWindow> = []
    for window in windows {
        if window.identity == identity && window.maintainer.length() > 0 && window.until_day >= 0 {
            if !found.contains(window) {
                found = found.push(window)
            }
        }
    }
    if found.length() == 0 {
        return verdict(false, "support-unknown", identity, today, "", -1)
    }
    if found.length() > 1 {
        // Two different statements about the same artifact: refuse rather
        // than pick one.
        return verdict(false, "conflicting-support-windows", identity, today, "", -1)
    }
    let window = found.get(0) or return Err(Error("morag.check: support window vanished"))
    if today <= window.until_day {
        return verdict(true, "within-support", identity, today, window.maintainer, window.until_day)
    }
    // Expired: a named maintainer's backport for exactly this artifact keeps
    // it admitted until the backport's own last day. The latest one wins;
    // ties go to the maintainer name that sorts first.
    let mut best_maintainer = ""
    let mut best_until = -1
    for backport in backports {
        if backport.identity == identity && backport.maintainer.length() > 0 && today <= backport.until_day {
            if backport.until_day > best_until || (backport.until_day == best_until && backport.maintainer < best_maintainer) {
                best_maintainer = backport.maintainer
                best_until = backport.until_day
            }
        }
    }
    if best_until >= 0 {
        return verdict(true, "maintainer-backport", identity, today, best_maintainer, best_until)
    }
    return verdict(false, "support-expired", identity, today, window.maintainer, window.until_day)
}
