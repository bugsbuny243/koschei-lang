// Koschei Core Library: time
//
// Written in Koschei. Pure calendar arithmetic on UTC timestamps in
// milliseconds since 1970-01-01T00:00:00Z, the unit `clock.now_ms()` returns.
// Nothing here reads the clock, so no capability is needed. Supported years
// are 1 through 9999; a timestamp or date outside them is an Error value,
// never a guessed date. There are no time zones and no leap seconds.

struct DateTime {
    year: Int,
    month: Int,
    day: Int,
    hour: Int,
    minute: Int,
    second: Int,
    millisecond: Int,
    // ISO weekday: 1 is Monday, 7 is Sunday.
    weekday: Int,
}

// 0001-01-01T00:00:00.000Z and 9999-12-31T23:59:59.999Z.
fn min_ms() -> Int {
    return -62135596800000
}

fn max_ms() -> Int {
    return 253402300799999
}

fn day_ms() -> Int {
    return 86400000
}

// Int division truncates toward zero; calendar math needs floor division.
fn floor_div(a: Int, b: Int) -> Int {
    let q = a / b
    if a % b != 0 && (a < 0) != (b < 0) {
        return q - 1
    }
    return q
}

fn floor_mod(a: Int, b: Int) -> Int {
    return a - floor_div(a, b) * b
}

fn is_leap_year(year: Int) -> Bool {
    if year % 400 == 0 {
        return true
    }
    if year % 100 == 0 {
        return false
    }
    return year % 4 == 0
}

fn days_in_month(year: Int, month: Int) -> Int or Error {
    if month < 1 || month > 12 {
        return Error("time.days_in_month: month must be 1 to 12")
    }
    if month == 2 {
        if is_leap_year(year) {
            return 29
        }
        return 28
    }
    if month == 4 || month == 6 || month == 9 || month == 11 {
        return 30
    }
    return 31
}

// Days since 1970-01-01 for a proleptic Gregorian date (H. Hinnant's algorithm).
fn days_from_civil(year: Int, month: Int, day: Int) -> Int {
    let mut y = year
    if month <= 2 {
        y = y - 1
    }
    let era = floor_div(y, 400)
    let yoe = y - era * 400
    let mut mp = month + 9
    if month > 2 {
        mp = month - 3
    }
    let doy = (153 * mp + 2) / 5 + day - 1
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
    return era * 146097 + doe - 719468
}

fn utc(ms: Int) -> DateTime or Error {
    if ms < min_ms() || ms > max_ms() {
        return Error("time.utc: the timestamp is outside years 1 to 9999")
    }
    let days = floor_div(ms, day_ms())
    let rest = ms - days * day_ms()
    let z = days + 719468
    let era = floor_div(z, 146097)
    let doe = z - era * 146097
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
    let mp = (5 * doy + 2) / 153
    let day = doy - (153 * mp + 2) / 5 + 1
    let mut month = mp - 9
    if mp < 10 {
        month = mp + 3
    }
    let mut year = yoe + era * 400
    if month <= 2 {
        year = year + 1
    }
    return DateTime {
        year: year,
        month: month,
        day: day,
        hour: rest / 3600000,
        minute: rest / 60000 % 60,
        second: rest / 1000 % 60,
        millisecond: rest % 1000,
        weekday: floor_mod(days + 3, 7) + 1,
    }
}

fn from_utc(year: Int, month: Int, day: Int, hour: Int, minute: Int, second: Int) -> Int or Error {
    if year < 1 || year > 9999 {
        return Error("time.from_utc: year must be 1 to 9999")
    }
    let length = days_in_month(year, month) or return Error("time.from_utc: month must be 1 to 12")
    if day < 1 || day > length {
        return Error("time.from_utc: day {day} is not in month {month} of {year}")
    }
    if hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59 {
        return Error("time.from_utc: time must be 00:00:00 to 23:59:59")
    }
    let days = days_from_civil(year, month, day)
    return days * day_ms() + hour * 3600000 + minute * 60000 + second * 1000
}

fn pad(value: Int, width: Int) -> String {
    let mut text = "{value}"
    while text.length() < width {
        text = "0" + text
    }
    return text
}

fn date_utc(ms: Int) -> String or Error {
    let t = utc(ms) or return Error("time.date_utc: the timestamp is outside years 1 to 9999")
    return "{pad(t.year, 4)}-{pad(t.month, 2)}-{pad(t.day, 2)}"
}

fn iso_utc(ms: Int) -> String or Error {
    let t = utc(ms) or return Error("time.iso_utc: the timestamp is outside years 1 to 9999")
    return "{pad(t.year, 4)}-{pad(t.month, 2)}-{pad(t.day, 2)}T{pad(t.hour, 2)}:{pad(t.minute, 2)}:{pad(t.second, 2)}Z"
}

fn iso_utc_ms(ms: Int) -> String or Error {
    let t = utc(ms) or return Error("time.iso_utc_ms: the timestamp is outside years 1 to 9999")
    return "{pad(t.year, 4)}-{pad(t.month, 2)}-{pad(t.day, 2)}T{pad(t.hour, 2)}:{pad(t.minute, 2)}:{pad(t.second, 2)}.{pad(t.millisecond, 3)}Z"
}

// Durations in milliseconds, for arithmetic on timestamps.
fn seconds(count: Int) -> Int or Error {
    let value = count * 1000 or return Error("time.seconds: the duration is outside Int")
    return value
}

fn minutes(count: Int) -> Int or Error {
    let value = count * 60000 or return Error("time.minutes: the duration is outside Int")
    return value
}

fn hours(count: Int) -> Int or Error {
    let value = count * 3600000 or return Error("time.hours: the duration is outside Int")
    return value
}

fn days(count: Int) -> Int or Error {
    let value = count * 86400000 or return Error("time.days: the duration is outside Int")
    return value
}
