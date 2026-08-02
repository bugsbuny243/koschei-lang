fn main() {
    let values = [5, 3, 2, 7]
    let mut total = 0
    let mut running: List<Int> = []
    for value in values {
        total = total + value
        running = running.push(total)
    }
    println(running)
}
