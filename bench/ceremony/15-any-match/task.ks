fn main() {
    let values = [3, 7, 12, 5]
    let mut found = false
    for value in values {
        if value > 10 { found = true break }
    }
    if found { println("found") } else { println("missing") }
}
