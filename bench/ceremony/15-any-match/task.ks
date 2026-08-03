fn above_ten(value: Int) -> Bool { return value > 10 }
fn main() {
    let values = [3, 7, 12, 5]
    if values.any(above_ten) { println("found") } else { println("missing") }
}
