fn main() {
    let words = "red blue red green blue red yellow".split(" ")
    let mut counts: Map<String, Int> = {}
    for word in words { counts = counts.set(word, (counts.get(word) or 0) + 1) }
    for word in counts.keys_sorted_by_value(true).take(3) {
        println("{word}:{counts.get(word) or 0}")
    }
}
