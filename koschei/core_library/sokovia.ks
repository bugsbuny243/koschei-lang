// Koschei Core Library — Marvel universe: sokovia
//
// Separation of privilege: an action runs only after `threshold` distinct
// approvers agreed to it (Saltzer and Schroeder; the two-person rule). An
// approval names the exact action digest, so an approval of one action never
// counts for another, however similar it looks ("what you approve is what
// runs"). The requester cannot approve their own action, an approver counts
// once however often they approve, and only the eligible approvers count.
//
// Approvals are data: this module decides over them and confers no authority.
// It cannot tell who wrote an approval; the application must authenticate each
// one (for example with `hmac_sha256` under a key only its approver's session
// holds) before passing it in.
import secure
import text

struct Approval {
    // The `action` digest the approver agreed to.
    action: String,
    approver: String,
}

struct QuorumVerdict {
    approved: Bool,
    reason: String,
    // The distinct eligible approvers counted, in ascending order.
    counted: List<String>,
    needed: Int,
}

// The digest that names one action: its kind and every field that changes
// what it does (amount, destination, account...). Approvals refer to it.
fn action(kind: String, fields: List<String>) -> Result<String, Error> {
    if kind.length() == 0 {
        return Err(Error("sokovia.action: action kind must be explicit"))
    }
    let mut parts = [kind]
    for field in fields {
        parts = parts.push(field)
    }
    let digest = secure.digest("koschei.marvel.sokovia.action/v1", parts) or return Err(Error("sokovia.action: action is too large to digest"))
    return Ok(digest)
}

// Whether `approvals` reach `threshold` distinct eligible approvers, other
// than `requester`, for exactly `action`. A threshold the eligible approvers
// other than the requester could never reach is an Error, not a denial.
fn decide(action: String, requester: String, eligible: List<String>, threshold: Int, approvals: List<Approval>) -> Result<QuorumVerdict, Error> {
    if !secure.is_digest(action) {
        return Err(Error("sokovia.decide: action must be a sha3-256 digest"))
    }
    if requester.length() == 0 {
        return Err(Error("sokovia.decide: requester must be explicit"))
    }
    let approvers = text.unique_sorted(eligible)
    if approvers.contains("") {
        return Err(Error("sokovia.decide: every eligible approver must be named"))
    }
    let mut possible = approvers.length()
    if approvers.contains(requester) {
        possible = possible - 1
    }
    if threshold < 1 || threshold > possible {
        return Err(Error("sokovia.decide: threshold must be between 1 and the eligible approvers other than the requester"))
    }
    let mut counted: List<String> = []
    for approval in approvals {
        if approval.action == action && approval.approver != requester && approvers.contains(approval.approver) {
            counted = counted.push(approval.approver)
        }
    }
    let distinct = text.unique_sorted(counted)
    if distinct.length() >= threshold {
        return Ok(QuorumVerdict { approved: true, reason: "approved", counted: distinct, needed: threshold })
    }
    return Ok(QuorumVerdict {
        approved: false,
        reason: "needs {threshold} distinct approvals, has {distinct.length()}",
        counted: distinct,
        needed: threshold,
    })
}
