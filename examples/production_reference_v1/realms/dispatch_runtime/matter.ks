fn square(value: Int) -> Int {
    return value * value
}

fn parallel_square(values: List<Int>) -> List<Int> or Error {
    let result = parallel_map(values, square, 4) or return Error("parallel dispatch failed")
    return result
}

fn main() {}
