fn add(total: Int, value: Int) -> Int { return total + value }
fn main() {
    let values = [5, 3, 2, 7]
    println(values.scan(0, add))
}
