fn is_even(value: Int) -> Bool { return value % 2 == 0 }
fn main() {
    let found = [1, 3, 6, 8].find(is_even)
    match found {
        Some(value) => println("{value}"),
        None => println("none"),
    }
}
