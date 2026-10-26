// Koschei Core Library — Marvel universe: xandar
//
// Nova Corps keeps the record: a known-vulnerable artifact is not admitted.
// An advisory names what it affects by content digest ("sha3-256:" + hex),
// never by version label. A label can claim a fix that is not there, or hide
// a fix a distribution backported without changing it; a digest cannot.
//
// An advisory is evidence. It can only refuse admission, never grant it, and
// a feed whose meaning is uncertain refuses everything: an advisory without
// an id, a duplicate id, or an affected entry that is not a digest makes the
// whole feed malformed. Every verdict carries the digest of the exact feed
// it was decided against.
//
// Xandar alone is not a defense: PHP2Shell was exploited before its advisory
// existed. Capability confinement, which needs no advisory, stays first.

import secure
import text

struct SecurityAdvisory {
    id: String,
    // Content digests of the affected artifacts.
    affected: List<String>,
}

struct AdvisoryVerdict {
    admitted: Bool,
    reason: String,
    // Ids of the matching advisories, distinct and in ascending order.
    advisories: List<String>,
    feed_digest: String,
    verdict_digest: String,
}

// Digest of a feed in canonical form: advisories by ascending id, each with
// its distinct affected digests in ascending order. Input order never
// changes the digest.
fn feed_digest(advisories: List<SecurityAdvisory>) -> Result<String, Error> {
    let mut ids: List<String> = []
    for advisory in advisories {
        ids = ids.push(advisory.id)
    }
    let mut parts: List<String> = ["{advisories.length()}"]
    for id in text.unique_sorted(ids) {
        for advisory in advisories {
            if advisory.id == id {
                let affected = text.unique_sorted(advisory.affected)
                parts = parts.push(id).push("{affected.length()}")
                for digest in affected {
                    parts = parts.push(digest)
                }
            }
        }
    }
    let value = secure.digest("koschei.marvel.xandar.feed/v1", parts) or return Err(Error("xandar.feed_digest: feed is too large to digest"))
    return Ok(value)
}

// True when every advisory has an id, ids are distinct, and every advisory
// names at least one affected digest.
fn is_well_formed(advisories: List<SecurityAdvisory>) -> Bool {
    let mut ids: List<String> = []
    for advisory in advisories {
        if advisory.id.length() == 0 || advisory.affected.length() == 0 {
            return false
        }
        for digest in advisory.affected {
            if !secure.is_digest(digest) {
                return false
            }
        }
        ids = ids.push(advisory.id)
    }
    return text.unique_sorted(ids).length() == ids.length()
}

// Builds the verdict of `check`; public only because Koschei v1 has no
// private functions.
fn verdict(admitted: Bool, reason: String, matched: List<String>, identity: String, feed: String) -> Result<AdvisoryVerdict, Error> {
    let mut flag = "0"
    if admitted {
        flag = "1"
    }
    let mut parts = [identity, feed, reason, flag]
    for id in matched {
        parts = parts.push(id)
    }
    let digest = secure.digest("koschei.marvel.xandar.verdict/v1", parts) or return Err(Error("xandar.check: verdict is too large to digest"))
    return Ok(AdvisoryVerdict {
        admitted: admitted,
        reason: reason,
        advisories: matched,
        feed_digest: feed,
        verdict_digest: digest,
    })
}

fn check(identity: String, advisories: List<SecurityAdvisory>) -> Result<AdvisoryVerdict, Error> {
    let feed = feed_digest(advisories) or return Err(Error("xandar.check: feed is too large to digest"))
    let none: List<String> = []
    if !secure.is_digest(identity) {
        return verdict(false, "identity-is-not-a-digest", none, identity, feed)
    }
    if !is_well_formed(advisories) {
        return verdict(false, "advisory-feed-is-malformed", none, identity, feed)
    }
    let mut matched: List<String> = []
    for advisory in advisories {
        if advisory.affected.contains(identity) {
            matched = matched.push(advisory.id)
        }
    }
    if matched.length() > 0 {
        return verdict(false, "known-vulnerable", text.unique_sorted(matched), identity, feed)
    }
    return verdict(true, "no-known-advisory", none, identity, feed)
}
