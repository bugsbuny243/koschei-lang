struct OrderLine {
    sku: String,
    quantity: Int,
}

fn valid_line(line: OrderLine) -> Bool {
    return line.quantity > 0
}

fn main() {
    let line = OrderLine { sku: "SKU-1", quantity: 2 }
    println("orders-ready:{valid_line(line)}")
}
