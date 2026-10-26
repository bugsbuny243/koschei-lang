// Koschei Core Library — Marvel universe: strange
//
// Bounded look-ahead over a declared path of authority transitions. Before any
// effect runs, `simulate` predicts whether the path would cross a forbidden
// effect, break the authority timeline or widen authority. It performs no
// effect and grants no authority: it only reads the steps it is given.
//
// Decisions, the index of the first violation and the reasons match the
// Python guardian `koschei/strange_future_paths_v1.py`. Authority sets are
// lists compared as sets. The path digest uses the domain-separated
// `secure.digest` encoding, so it differs from the Python byte layout.

import secure
import text

struct FutureStep {
    effect: String,
    target: String,
    authority_before: List<String>,
    authority_after: List<String>,
}

struct FutureVerdict {
    safe: Bool,
    // The index of the first violating step; `None` when the path is safe.
    first_violation: Option<Int>,
    reason: String,
    // Digest of every step examined, up to and including the first violation.
    path_digest: String,
}

// Builds the verdict of `simulate`; public only because Koschei v1 has no
// private functions.
fn verdict(safe: Bool, first_violation: Option<Int>, reason: String, parts: List<String>) -> Result<FutureVerdict, Error> {
    let digest = secure.digest("koschei.marvel.strange.path/v1", parts) or return Err(Error("strange.simulate: path is too large to digest"))
    return Ok(FutureVerdict {
        safe: safe,
        first_violation: first_violation,
        reason: reason,
        path_digest: digest,
    })
}

fn simulate(steps: List<FutureStep>, max_steps: Int, forbidden_effects: List<String>) -> Result<FutureVerdict, Error> {
    if steps.length() == 0 || steps.length() > max_steps || max_steps < 1 {
        return Err(Error("strange.simulate: path must be non-empty and bounded"))
    }
    let mut parts: List<String> = []
    let mut previous_after: List<String> = []
    let mut index = 0
    for step in steps {
        if step.effect.length() == 0 || step.target.length() == 0 {
            return verdict(false, Some(index), "implicit effect/target", parts)
        }
        // Each set is written as its size followed by its canonical members,
        // so the flat part list decodes in exactly one way.
        let before = text.unique_sorted(step.authority_before)
        let after = text.unique_sorted(step.authority_after)
        parts = parts.push("{index}").push(step.effect).push(step.target)
        parts = parts.push("{before.length()}")
        for name in before {
            parts = parts.push(name)
        }
        parts = parts.push("{after.length()}")
        for name in after {
            parts = parts.push(name)
        }
        if index > 0 && before != previous_after {
            return verdict(false, Some(index), "authority timeline discontinuity", parts)
        }
        if forbidden_effects.contains(step.effect) {
            return verdict(false, Some(index), "forbidden future effect", parts)
        }
        for name in after {
            if !before.contains(name) {
                return verdict(false, Some(index), "future authority expansion", parts)
            }
        }
        previous_after = after
        index = index + 1
    }
    return verdict(true, None(), "bounded path preserves authority", parts)
}
