fn main() {
    let mut found: Option<Int> = None()
    for value in [1, 3, 6, 8] {
        if value % 2 != 0 { continue }
        found = Some(value)
        break
    }
    match found {
        Some(value) => println("{value}"),
        None => println("none"),
    }
}
