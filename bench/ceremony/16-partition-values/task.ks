fn negative(value: Int) -> Bool { return value < 0 }
fn main() {
    let values = [-3, 2, 0, 5, -1]
    for group in values.partition(negative) { println(group) }
}
