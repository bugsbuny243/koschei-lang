fn main() {
    let words = "red blue red green blue red yellow".split(" ")
    let mut counts: Map<String, Int> = {}
    for word in words {
        counts = counts.set(word, (counts.get(word) or 0) + 1)
    }
    let mut first = ""
    let mut first_count = 0
    for word in counts.keys() {
        let count = counts.get(word) or 0
        if count > first_count { first = word first_count = count }
    }
    let mut second = ""
    let mut second_count = 0
    for word in counts.keys() {
        if word == first { continue }
        let count = counts.get(word) or 0
        if count > second_count { second = word second_count = count }
    }
    let mut third = ""
    let mut third_count = 0
    for word in counts.keys() {
        if word == first || word == second { continue }
        let count = counts.get(word) or 0
        if count > third_count { third = word third_count = count }
    }
    println("{first}:{first_count}")
    println("{second}:{second_count}")
    println("{third}:{third_count}")
}
