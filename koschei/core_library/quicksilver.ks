// Koschei Core Library — Marvel universe: quicksilver
//
// Velocity limits: at most `limit` units in any `window` epochs. A budget
// that counts only the size of each action still lets an attacker drain
// everything in many small, fast steps; a velocity limit bounds how much can
// leave per unit of time, so the damage done before anyone reacts is bounded
// too. The same rule with `amount` 1 is a supervisor's restart intensity
// (Erlang/OTP: at most N restarts in T, then stop and escalate).
//
// History is data: this module decides over it and confers no authority. No
// arithmetic here can overflow: epochs are non-negative, so `now - epoch`
// stays in range, and once the window holds more than `limit` the check stops
// adding.

struct Spend {
    epoch: Int,
    amount: Int,
}

struct VelocityVerdict {
    allowed: Bool,
    reason: String,
    // Units already spent in the window; `limit` once the window is over it
    // (the sum is not taken further).
    spent_in_window: Int,
    // Units left in the window before this request.
    remaining: Int,
}

// Whether `amount` more units at epoch `now` keep the spends in the window
// `(now - window, now]` within `limit`. A spend before epoch 0 or after
// `now`, or a negative amount, is an Error: the history is not trustworthy.
fn check(history: List<Spend>, now: Int, window: Int, limit: Int, amount: Int) -> Result<VelocityVerdict, Error> {
    if now < 0 || window < 1 || limit < 0 || amount < 0 {
        return Err(Error("quicksilver.check: now must be non-negative, window positive, limit and amount non-negative"))
    }
    let mut spent = 0
    let mut exceeded = false
    for spend in history {
        if spend.amount < 0 {
            return Err(Error("quicksilver.check: a spend cannot be negative"))
        }
        if spend.epoch < 0 || spend.epoch > now {
            return Err(Error("quicksilver.check: history holds a spend outside 0..now"))
        }
        // `now - spend.epoch` is non-negative here; comparing it with
        // `window` avoids computing `now - window`, which could overflow.
        if now - spend.epoch < window && !exceeded {
            if spend.amount > limit - spent {
                exceeded = true
                spent = limit
            } else {
                spent = spent + spend.amount
            }
        }
    }
    if exceeded {
        return Ok(VelocityVerdict { allowed: false, reason: "window already over its limit", spent_in_window: spent, remaining: 0 })
    }
    let remaining = limit - spent
    if amount > remaining {
        return Ok(VelocityVerdict { allowed: false, reason: "would exceed the window limit", spent_in_window: spent, remaining: remaining })
    }
    return Ok(VelocityVerdict { allowed: true, reason: "within the window limit", spent_in_window: spent, remaining: remaining })
}
