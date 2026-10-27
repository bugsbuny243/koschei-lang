// wordfreq: count the words read from standard input.
//
//   printf 'the cat saw the dog\n' | ks run main.ks
//   ks build main.ks -o wordfreq && ./wordfreq 2 < book.txt
//
// The optional argument is the minimum count to report (default 1). Words
// are reported in sorted order with their counts.

import text

fn minimum(args: List<String>) -> Int or Error {
    let raw = args.get(0) or return 1
    let value = raw.to_int() or return Error("minimum count must be a number: {raw}")
    if value < 1 {
        return Error("minimum count must be at least 1: {value}")
    }
    return value
}

fn occurrences(words: List<String>, word: String) -> Int {
    let mut count = 0
    for item in words {
        if item == word {
            count = count + 1
        }
    }
    return count
}

fn report(input: InputCaps) -> Int or Error {
    let args = input.args() or return Error("arguments are not UTF-8 text")
    let least = minimum(args) or return Error("usage: wordfreq [MINIMUM]")
    let body = input.read_text() or return Error("standard input is unreadable or over 1 MiB")
    let words = text.words(body) or return Error("standard input has more words than one List may hold")
    let mut reported = 0
    for word in text.unique_sorted(words) {
        let count = occurrences(words, word)
        if count >= least {
            println("{count} {word}")
            reported = reported + 1
        }
    }
    println("{words.length()} words, {reported} reported")
    return reported
}

fn main(caps: SystemCaps) {
    let reported = report(caps.input.allow(1048576)) or -1
    if reported < 0 {
        println("wordfreq: usage: wordfreq [MINIMUM] < text")
    }
}
