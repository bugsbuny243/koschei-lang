// Koschei Core Library — Marvel universe: captain_marvel
//
// Blast-radius containment for cross-reality propagation. An incident gets an
// explicit propagation budget: the destinations it may reach, and how many
// hops and effects it may spend. Evaluating a step can only consume that
// budget; it never adds a destination and never grants authority. A verdict is
// a plain value. In Koschei, authority only travels as capability tokens.
//
// Decisions and reasons match the Python guardian
// `koschei/captain_marvel_blast_radius_v1.py`. Digests use the domain-separated
// `secure.digest` encoding, so they differ from the Python byte layout.

import secure
import text

struct BlastRadiusBudget {
    origin_reality: String,
    // Canonical: distinct names in ascending order (`text.unique_sorted`).
    allowed_destinations: List<String>,
    max_hops: Int,
    max_effects: Int,
    budget_digest: String,
}

struct PropagationVerdict {
    allowed: Bool,
    reason: String,
    remaining_hops: Int,
    remaining_effects: Int,
    verdict_digest: String,
}

fn issue_budget(origin_reality: String, allowed_destinations: List<String>, max_hops: Int, max_effects: Int) -> Result<BlastRadiusBudget, Error> {
    if origin_reality.length() == 0 || max_hops < 0 || max_effects < 0 {
        return Err(Error("captain_marvel.issue_budget: invalid blast-radius budget"))
    }
    if allowed_destinations.contains(origin_reality) {
        return Err(Error("captain_marvel.issue_budget: origin cannot be a propagation destination"))
    }
    if allowed_destinations.contains("") {
        return Err(Error("captain_marvel.issue_budget: destination must be explicit"))
    }
    let destinations = text.unique_sorted(allowed_destinations)
    let mut parts = [origin_reality, "{max_hops}", "{max_effects}"]
    for destination in destinations {
        parts = parts.push(destination)
    }
    let digest = secure.digest("koschei.marvel.captain-marvel.budget/v1", parts) or return Err(Error("captain_marvel.issue_budget: budget is too large to digest"))
    return Ok(BlastRadiusBudget {
        origin_reality: origin_reality,
        allowed_destinations: destinations,
        max_hops: max_hops,
        max_effects: max_effects,
        budget_digest: digest,
    })
}

// True when `budget` is exactly what `issue_budget` returns for its fields:
// valid limits, canonical destinations and a matching digest. A digest is not
// a signature; this detects edited or hand-built budgets, not who issued them.
fn is_canonical_budget(budget: BlastRadiusBudget) -> Bool {
    let destinations = budget.allowed_destinations
    let issued = issue_budget(budget.origin_reality, destinations, budget.max_hops, budget.max_effects)
    return match issued {
        Ok(expected) => expected.allowed_destinations == destinations && expected.budget_digest == budget.budget_digest,
        Err(_) => false,
    }
}

fn evaluate(budget: BlastRadiusBudget, destination: String, hops_used: Int, effects_used: Int) -> Result<PropagationVerdict, Error> {
    if !is_canonical_budget(budget) {
        return Err(Error("captain_marvel.evaluate: canonical budget required"))
    }
    if hops_used < 0 || effects_used < 0 {
        return Err(Error("captain_marvel.evaluate: usage cannot be negative"))
    }
    let mut allowed = true
    let mut reason = "within-blast-radius"
    if !budget.allowed_destinations.contains(destination) {
        allowed = false
        reason = "destination-outside-blast-radius"
    } else if hops_used >= budget.max_hops {
        allowed = false
        reason = "hop-budget-exhausted"
    } else if effects_used >= budget.max_effects {
        allowed = false
        reason = "effect-budget-exhausted"
    }
    // An allowed step spends one hop and one effect. Both subtractions stay in
    // range: every operand is non-negative and the spend is only taken when
    // the usage is strictly below its limit.
    let mut spent = 0
    let mut flag = "0"
    if allowed {
        spent = 1
        flag = "1"
    }
    let mut remaining_hops = budget.max_hops - hops_used - spent
    if remaining_hops < 0 {
        remaining_hops = 0
    }
    let mut remaining_effects = budget.max_effects - effects_used - spent
    if remaining_effects < 0 {
        remaining_effects = 0
    }
    let parts = [budget.budget_digest, destination, "{hops_used}", "{effects_used}", reason, flag]
    let digest = secure.digest("koschei.marvel.captain-marvel.verdict/v1", parts) or return Err(Error("captain_marvel.evaluate: verdict is too large to digest"))
    return Ok(PropagationVerdict {
        allowed: allowed,
        reason: reason,
        remaining_hops: remaining_hops,
        remaining_effects: remaining_effects,
        verdict_digest: digest,
    })
}
