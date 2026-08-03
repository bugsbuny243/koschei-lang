fn main() {
    let values = [1, 2, 3, 4, 5, 6, 7]
    let batches = values.chunks(3) or []
    for batch in batches { println(batch) }
}
