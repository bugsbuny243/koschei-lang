fn square(value: Int) -> Int {
    return value * value
}

fn main() {
    let values = [1, 2, 3, 4, 5, 6, 7, 8]
    let first = parallel_map(values, square, 4) or return
    let second = parallel_map(values, square, 8) or return
    println(first)
    println(second)
    println(values)
}
