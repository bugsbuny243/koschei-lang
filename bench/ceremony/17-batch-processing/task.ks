fn main() {
    let values = [1, 2, 3, 4, 5, 6, 7]
    let mut index = 0
    while index < values.length() {
        let mut batch: List<Int> = []
        let mut offset = 0
        while offset < 3 && index + offset < values.length() {
            batch = batch.push(values.get(index + offset) or 0)
            offset = offset + 1
        }
        println(batch)
        index = index + 3
    }
}
