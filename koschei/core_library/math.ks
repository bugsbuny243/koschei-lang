// Koschei Core Library: math
//
// Written in Koschei. Int is signed 64-bit and never wraps: a result that
// would leave that range is an Error value, never a silently wrong number.
// Functions that cannot overflow return a plain Int or Float.

fn min(a: Int, b: Int) -> Int {
    if a < b {
        return a
    }
    return b
}

fn max(a: Int, b: Int) -> Int {
    if a > b {
        return a
    }
    return b
}

// The bounds must be in order: low > high is an Error value, not a guess.
fn clamp(value: Int, low: Int, high: Int) -> Int or Error {
    if low > high {
        return Error("math.clamp: low is greater than high")
    }
    if value < low {
        return low
    }
    if value > high {
        return high
    }
    return value
}

fn sign(value: Int) -> Int {
    if value < 0 {
        return -1
    }
    if value > 0 {
        return 1
    }
    return 0
}

// The smallest Int has no positive counterpart within 64 bits.
fn abs(value: Int) -> Int or Error {
    if value >= 0 {
        return value
    }
    if value == -9223372036854775807 - 1 {
        return Error("math.abs: the smallest Int has no absolute value within Int")
    }
    return 0 - value
}

fn is_even(value: Int) -> Bool {
    return value % 2 == 0
}

// base raised to a non-negative exponent, by repeated squaring.
fn pow(base: Int, exponent: Int) -> Int or Error {
    if exponent < 0 {
        return Error("math.pow: the exponent must not be negative")
    }
    let mut result = 1
    let mut factor = base
    let mut rest = exponent
    while rest > 0 {
        if rest % 2 == 1 {
            result = result * factor or return Error("math.pow: the result is outside Int")
        }
        rest = rest / 2
        if rest > 0 {
            factor = factor * factor or return Error("math.pow: the result is outside Int")
        }
    }
    return result
}

// Greatest common divisor; gcd(0, 0) is 0.
fn gcd(a: Int, b: Int) -> Int or Error {
    let mut x = abs(a) or return Error("math.gcd: the smallest Int is out of range")
    let mut y = abs(b) or return Error("math.gcd: the smallest Int is out of range")
    while y != 0 {
        let rest = x % y
        x = y
        y = rest
    }
    return x
}

fn min_float(a: Float, b: Float) -> Float {
    if a < b {
        return a
    }
    return b
}

fn max_float(a: Float, b: Float) -> Float {
    if a > b {
        return a
    }
    return b
}

fn abs_float(value: Float) -> Float {
    if value < 0.0 {
        return 0.0 - value
    }
    return value
}

fn clamp_float(value: Float, low: Float, high: Float) -> Float or Error {
    if low > high {
        return Error("math.clamp_float: low is greater than high")
    }
    if value < low {
        return low
    }
    if value > high {
        return high
    }
    return value
}
