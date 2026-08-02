fn main() {
    let values = ["a", "b", "a", "c", "b"]
    let mut unique: List<String> = []
    for value in values {
        if unique.contains(value) { continue }
        unique = unique.push(value)
    }
    println(unique.join(","))
}
