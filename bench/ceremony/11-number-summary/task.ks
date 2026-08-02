fn main() {
    let values = [4, 8, 15, 16, 23, 42]
    let mut total = 0
    let mut minimum = values.get(0) or 0
    let mut maximum = minimum
    for value in values {
        total = total + value
        if value < minimum { minimum = value }
        if value > maximum { maximum = value }
    }
    println("sum={total} min={minimum} max={maximum}")
}
