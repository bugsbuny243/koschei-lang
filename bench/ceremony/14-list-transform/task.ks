fn main() {
    let values = [1, 2, 3, 4]
    let mut squares: List<Int> = []
    for value in values {
        squares = squares.push(value * value)
    }
    println(squares)
}
