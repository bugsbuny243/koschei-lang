// release_gate: admit or refuse build artifacts before they ship.
//
//   ks run main.ks < gate.txt          # decide for today (UTC)
//   ks run main.ks 20800 < gate.txt    # decide for day 20800 (replayable)
//
// Every artifact is named by its content digest, never by a version label.
// Standard input holds one statement per line:
//
//   advisory ID DIGEST...         a known vulnerability affecting DIGESTs
//   support DIGEST MAINTAINER DAY  supported until DAY (days since 1970-01-01)
//   backport DIGEST MAINTAINER DAY patched by MAINTAINER until DAY
//   check DIGEST                   decide this artifact
//
// An artifact ships only when Xandar finds no advisory for it and Morag finds
// it inside a support window or a named maintainer's backport.

import morag
import xandar

struct Gate {
    advisories: List<SecurityAdvisory>,
    windows: List<SupportWindow>,
    backports: List<MaintainerBackport>,
    checks: List<String>,
    malformed: Int,
}

fn day_from(text: String) -> Int {
    let day = text.to_int() or return -1
    return day
}

fn parse(body: String) -> Gate {
    let mut gate = Gate { advisories: [], windows: [], backports: [], checks: [], malformed: 0 }
    let none: List<String> = []
    let lines = body.split("\n") or none
    for line in lines {
        let fields = line.trim().split(" ") or none
        let kind = fields.get(0) or ""
        let first = fields.get(1) or ""
        let second = fields.get(2) or ""
        let third = fields.get(3) or ""
        if kind == "advisory" && fields.length() >= 3 {
            let mut affected: List<String> = []
            let mut index = 2
            while index < fields.length() {
                let digest = fields.get(index) or ""
                affected = affected.push(digest)
                index = index + 1
            }
            gate.advisories = gate.advisories.push(SecurityAdvisory { id: first, affected: affected })
        } else if kind == "support" && fields.length() == 4 && day_from(third) >= 0 {
            gate.windows = gate.windows.push(SupportWindow { identity: first, maintainer: second, until_day: day_from(third) })
        } else if kind == "backport" && fields.length() == 4 && day_from(third) >= 0 {
            gate.backports = gate.backports.push(MaintainerBackport { identity: first, maintainer: second, until_day: day_from(third) })
        } else if kind == "check" && fields.length() == 2 {
            gate.checks = gate.checks.push(first)
        } else if kind != "" {
            gate.malformed = gate.malformed + 1
        }
    }
    return gate
}

fn decide(gate: Gate, today: Int) -> Int or Error {
    let mut shipped = 0
    for identity in gate.checks {
        let known = xandar.check(identity, gate.advisories) or return Error("advisory feed could not be digested")
        let support = morag.check(identity, today, gate.windows, gate.backports) or return Error("support decision failed")
        let mut decision = "REFUSE"
        if known.admitted && support.admitted {
            decision = "SHIP"
            shipped = shipped + 1
        }
        println("{decision} {identity} xandar={known.reason} morag={support.reason}")
    }
    println("day {today}: {shipped} of {gate.checks.length()} ship, {gate.malformed} malformed lines")
    return shipped
}

fn main(caps: SystemCaps) {
    let input = caps.input.allow(1048576)
    let clock = caps.clock.allow(1000)
    let none: List<String> = []
    let args = input.args() or none
    let today_text = args.get(0) or ""
    let mut today = clock.now_ms() / 86400000
    if today_text != "" {
        today = day_from(today_text)
    }
    let body = input.read_text() or ""
    if today < 0 {
        println("release_gate: DAY must be a day number")
    } else {
        let shipped = decide(parse(body), today) or -1
        if shipped < 0 {
            println("release_gate: the statements could not be decided")
        }
    }
}
